#!/usr/bin/env python3
"""My Whisper - macOS 本地实时语音转文字工具

快捷键 ⌘⇧Space 开始/停止录音，实时转写显示在文本窗口中。
"""

import json
import re
import sys
import os
import logging
import threading
import queue
import argparse
import time

# 文件日志（写到 ~/Library/Logs/）
_LOG_DIR = os.path.join(os.path.expanduser("~"), "Library", "Logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_PATH = os.path.join(_LOG_DIR, "my-whisper.log")
logging.basicConfig(
    filename=_LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("mywhisper")
log.info("=== main.py 开始加载 ===")

try:
    import numpy as np
    log.info("import numpy OK")
except Exception as e:
    log.error("import numpy FAILED: %s", e)
    sys.exit(1)

try:
    import sounddevice as sd
    log.info("import sounddevice OK")
except Exception as e:
    log.error("import sounddevice FAILED: %s", e)
    sys.exit(1)

try:
    import mlx_whisper
    log.info("import mlx_whisper OK")
except Exception as e:
    log.error("import mlx_whisper FAILED: %s", e)
    sys.exit(1)

try:
    import objc
    import AppKit
    import WebKit
    log.info("import objc/AppKit/WebKit OK")
except Exception as e:
    log.error("import objc/AppKit/WebKit FAILED: %s", e)
    sys.exit(1)

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSMenu,
    NSMenuItem,
    NSWindow,
    NSMakeRect,
    NSMakeSize,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskMiniaturizable,
    NSBackingStoreBuffered,
    NSViewWidthSizable,
    NSViewHeightSizable,
    NSSound,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject, NSLog, NSURL
from PyObjCTools import AppHelper
from WebKit import WKWebView, WKWebViewConfiguration, WKUserContentController


# ─── 配置 ────────────────────────────────────────────────────────────────────

SAMPLE_RATE = 16000
BLOCK_DURATION = 0.1
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_DURATION)

SILENCE_THRESHOLD = 0.01
SPEECH_THRESHOLD = 0.015
SILENCE_DURATION = 0.8
MAX_SEGMENT_SECS = 15
MIN_SEGMENT_SECS = 0.5
NO_SPEECH_PROB_THRESHOLD = 0.6
NO_TRANSCRIPT_TIMEOUT = 15  # 秒，无新转录则自动停止录音

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_LANGUAGE = "zh"

NSEventMaskKeyDown = 1 << 10
NSEventModifierFlagCommand = 1 << 20
NSEventModifierFlagShift = 1 << 17

MODELS = [
    ("mlx-community/whisper-tiny", "Tiny (39M)"),
    ("mlx-community/whisper-base", "Base (74M)"),
    ("mlx-community/whisper-small", "Small (244M)"),
    ("mlx-community/whisper-medium", "Medium (769M)"),
    ("mlx-community/whisper-large-v3-turbo", "Large V3 Turbo (809M)"),
]

LANGUAGES = [
    ("zh", "中文"),
    ("en", "English"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    (None, "自动检测"),
]

HALLUCINATION_MARKERS = [
    "谢谢观看", "字幕由", "请不吝点赞", "Amara",
    "Subscribe", "Thank you for watching",
    "construction", "Copyright", "copyright",
    "字幕", "小鑫", "感谢收看",
]


# ─── 资源路径 ────────────────────────────────────────────────────────────────

def _get_resource_path(filename):
    """获取资源文件路径（兼容 PyInstaller 打包和开发环境）"""
    if getattr(sys, '_MEIPASS', None):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


def _get_bundled_model_path(model_repo):
    """如果 bundle 内嵌了模型，返回本地路径；否则返回原始 repo 名"""
    model_name = model_repo.split("/")[-1]
    candidates = []
    # py2app 设置的 RESOURCEPATH 环境变量
    res = os.environ.get("RESOURCEPATH")
    if res:
        candidates.append(os.path.join(res, "models", model_name))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", model_name))
    for bundled in candidates:
        if os.path.isdir(bundled) and os.path.exists(os.path.join(bundled, "config.json")):
            log.info("使用内嵌模型: %s", bundled)
            return bundled
    log.info("未找到内嵌模型 %s，候选路径: %s", model_name, candidates)
    return model_repo


# ─── WKScriptMessageHandler ──────────────────────────────────────────────────

class _BridgeHandler(NSObject):
    """独立的 WKScriptMessageHandler，转发消息给 AppDelegate"""

    def initWithDelegate_(self, delegate):
        self = objc.super(_BridgeHandler, self).init()
        if self is None:
            return None
        self.delegate = delegate
        return self

    def userContentController_didReceiveScriptMessage_(self, controller, message):
        self.delegate.handleBridgeMessage_(message.body())


# ─── App Delegate ────────────────────────────────────────────────────────────

class AppDelegate(NSObject):

    def applicationDidFinishLaunching_(self, notification):
        log.info("applicationDidFinishLaunching_ 开始")
        self.is_recording = False
        self.model_loaded = False
        self.audio_queue = queue.Queue()
        self.stream = None
        self.model = self._args.model
        self.language = self._args.language if self._args.language != "auto" else None
        self._web_loaded = False
        self._pending_js = []

        try:
            self._setup_main_menu()
            log.info("_setup_main_menu 完成")
            self._setup_window()
            log.info("_setup_window 完成")
            self._setup_hotkey()
            log.info("_setup_hotkey 完成")
            self._setup_status_bar()
            log.info("_setup_status_bar 完成")
        except Exception as e:
            log.error("初始化失败: %s", e, exc_info=True)
            return

        # 启动时显示窗口
        self.window.makeKeyAndOrderFront_(None)

        self._load_model()
        log.info("初始化完成")

    # ── JS 桥接 ────────────────────────────────────────────────────────────

    def _eval_js(self, js):
        """执行 JavaScript，如果页面未加载完则排队"""
        if not self._web_loaded:
            self._pending_js.append(js)
            return
        self.webview.evaluateJavaScript_completionHandler_(js, None)

    def _init_web_ui(self):
        """页面加载完成后初始化 UI 数据"""
        models_json = json.dumps(MODELS)
        model_val = json.dumps(self.model)
        langs_json = json.dumps(LANGUAGES)
        lang_val = json.dumps(self.language)
        self._eval_js(f"initModels({models_json}, {model_val})")
        self._eval_js(f"initLanguages({langs_json}, {lang_val})")
        if self.model_loaded:
            self._eval_js("updateStatus('就绪')")
            self._eval_js("setModelLoaded(true)")
        else:
            self._eval_js("updateStatus('加载模型中...')")

    # ── WKNavigationDelegate ──────────────────────────────────────────────

    def webView_didFinishNavigation_(self, webview, navigation):
        log.info("WebView 加载完成")
        self._web_loaded = True
        self._init_web_ui()
        for js in self._pending_js:
            self.webview.evaluateJavaScript_completionHandler_(js, None)
        self._pending_js = []

    # ── JS → Python 消息处理 ────────────────────────────────────────────

    def handleBridgeMessage_(self, body):
        action = body.get("action", "")
        log.info("JS bridge: %s", action)

        if action == "startRecording":
            self._start_recording()
        elif action == "stopRecording":
            self._stop_recording()
        elif action == "changeModel":
            self._change_model(body.get("model", ""))
        elif action == "changeLanguage":
            lang = body.get("language", "")
            self.language = lang if lang else None
            log.info("语言切换为: %s", self.language)
        elif action == "copyAll":
            text = body.get("text", "")
            pb = AppKit.NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
            self._eval_js("showToast('已复制到剪贴板')")
        elif action == "clearText":
            log.info("文本已清空")
        elif action == "quit":
            self.quitApp_(None)

    # ── 主菜单（让 Cmd+C/V/A 等标准快捷键生效）─────────────────────────────

    def _setup_main_menu(self):
        main_menu = NSMenu.alloc().init()

        # App 菜单
        app_item = NSMenuItem.alloc().init()
        app_menu = NSMenu.alloc().initWithTitle_("My Whisper")
        app_menu.addItemWithTitle_action_keyEquivalent_("关于 My Whisper", "orderFrontStandardAboutPanel:", "")
        app_menu.addItem_(NSMenuItem.separatorItem())
        app_menu.addItemWithTitle_action_keyEquivalent_("退出 My Whisper", "quitApp:", "q")
        app_item.setSubmenu_(app_menu)
        main_menu.addItem_(app_item)

        # Edit 菜单
        edit_item = NSMenuItem.alloc().init()
        edit_menu = NSMenu.alloc().initWithTitle_("Edit")
        edit_menu.addItemWithTitle_action_keyEquivalent_("撤销", "undo:", "z")
        edit_menu.addItemWithTitle_action_keyEquivalent_("重做", "redo:", "Z")
        edit_menu.addItem_(NSMenuItem.separatorItem())
        edit_menu.addItemWithTitle_action_keyEquivalent_("剪切", "cut:", "x")
        edit_menu.addItemWithTitle_action_keyEquivalent_("复制", "copy:", "c")
        edit_menu.addItemWithTitle_action_keyEquivalent_("粘贴", "paste:", "v")
        edit_menu.addItemWithTitle_action_keyEquivalent_("全选", "selectAll:", "a")
        edit_item.setSubmenu_(edit_menu)
        main_menu.addItem_(edit_item)

        NSApplication.sharedApplication().setMainMenu_(main_menu)

    # ── 窗口（WKWebView）─────────────────────────────────────────────────

    def _setup_window(self):
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskMiniaturizable
        )

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(200, 200, 700, 500), style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("My Whisper")
        self.window.setMinSize_(NSMakeSize(400, 300))
        self.window.setReleasedWhenClosed_(False)
        self.window.setFrameAutosaveName_("MyWhisperMainWindow")

        # 创建 WKWebView
        config = WKWebViewConfiguration.alloc().init()
        controller = config.userContentController()
        self._bridge_handler = _BridgeHandler.alloc().initWithDelegate_(self)
        controller.addScriptMessageHandler_name_(self._bridge_handler, "bridge")

        content = self.window.contentView()
        self.webview = WKWebView.alloc().initWithFrame_configuration_(
            content.bounds(), config
        )
        self.webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.webview.setNavigationDelegate_(self)
        content.addSubview_(self.webview)

        # 加载 HTML
        html_path = _get_resource_path("ui.html")
        html_url = NSURL.fileURLWithPath_(html_path)
        self.webview.loadFileURL_allowingReadAccessToURL_(
            html_url, html_url.URLByDeletingLastPathComponent()
        )

    # ── 全局快捷键 ──────────────────────────────────────────────────────────

    def _setup_hotkey(self):
        required_flags = NSEventModifierFlagCommand | NSEventModifierFlagShift

        def check_hotkey(event):
            flags = event.modifierFlags()
            return (flags & required_flags) == required_flags and event.keyCode() == 49

        AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown,
            lambda event: (
                self.performSelectorOnMainThread_withObject_waitUntilDone_(
                    "toggleRecording:", None, False
                )
                if check_hotkey(event) else None
            ),
        )

        AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown,
            lambda event: None if check_hotkey(event) and (
                self.performSelectorOnMainThread_withObject_waitUntilDone_(
                    "toggleRecording:", None, False
                ) or True
            ) else event,
        )

    # ── 菜单栏图标 ─────────────────────────────────────────────────────────

    def _setup_status_bar(self):
        sb = NSStatusBar.systemStatusBar()
        log.info("statusBar: %s", sb)
        self._status_item = sb.statusItemWithLength_(NSVariableStatusItemLength)
        log.info("status_item: %s", self._status_item)
        btn = self._status_item.button()
        log.info("status_item.button: %s", btn)
        btn.setTitle_("🎙")
        log.info("button title set, visible: %s", btn.isHidden())

        menu = NSMenu.alloc().init()
        self._record_menu_item = menu.addItemWithTitle_action_keyEquivalent_(
            "开始转录", "toggleRecording:", ""
        )
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItemWithTitle_action_keyEquivalent_("显示主窗口", "showMainWindow:", "")
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItemWithTitle_action_keyEquivalent_("退出", "quitApp:", "")
        self._status_item.setMenu_(menu)
        log.info("activationPolicy: %s", NSApplication.sharedApplication().activationPolicy())
        log.info("status_item.isVisible: %s", self._status_item.isVisible())

    def _update_status_bar(self):
        if not hasattr(self, '_status_item'):
            return
        self._record_menu_item.setTitle_(
            "停止转录" if self.is_recording else "开始转录"
        )
        self._status_item.button().setTitle_(
            "🔴" if self.is_recording else "🎙"
        )

    @objc.IBAction
    def showMainWindow_(self, sender):
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    # ── 模型加载 ────────────────────────────────────────────────────────────

    def _load_model(self):
        def load():
            try:
                log.info("开始加载模型: %s", self.model)
                dummy = np.zeros(SAMPLE_RATE, dtype=np.float32)
                mlx_whisper.transcribe(dummy, path_or_hf_repo=_get_bundled_model_path(self.model), fp16=True)
                self.model_loaded = True
                self.performSelectorOnMainThread_withObject_waitUntilDone_(
                    "onModelLoaded:", None, False
                )
            except Exception as e:
                log.error("模型加载失败: %s", e)
                self.performSelectorOnMainThread_withObject_waitUntilDone_(
                    "onModelError:", str(e), False
                )

        threading.Thread(target=load, daemon=True).start()

    def onModelLoaded_(self, _):
        self._eval_js("updateStatus('就绪')")
        self._eval_js("setModelLoaded(true)")
        self.window.setTitle_("My Whisper")
        log.info("模型加载完成")

    def onModelError_(self, error_msg):
        escaped = json.dumps(f"模型加载失败: {error_msg}")
        self._eval_js(f"updateStatus({escaped})")

    def _change_model(self, model_repo):
        """切换 Whisper 模型"""
        if model_repo == self.model:
            return
        if self.is_recording:
            self._stop_recording()
        self.model = model_repo
        self.model_loaded = False
        self._eval_js("setModelLoaded(false)")
        self._eval_js("updateStatus('加载模型中...')")
        self.window.setTitle_("My Whisper — 加载模型中...")
        log.info("切换模型: %s", model_repo)
        self._load_model()

    # ── 录音控制 ────────────────────────────────────────────────────────────

    @objc.IBAction
    def toggleRecording_(self, sender):
        if not self.model_loaded:
            return
        if self.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        if not self.model_loaded:
            return
        self.is_recording = True
        self._last_transcript_time = time.time()
        self._eval_js("setRecording(true)")
        self._eval_js("updateStatus('录音中...')")
        self.window.setTitle_("My Whisper — 录音中...")

        # 播放提示音
        sound = NSSound.soundNamed_("Tink")
        if sound:
            sound.play()

        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

        self.audio_queue = queue.Queue()
        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype=np.float32,
                blocksize=BLOCK_SIZE,
                callback=self._audio_callback,
            )
            self.stream.start()
        except Exception as e:
            log.error("麦克风启动失败: %s", e)
            escaped = json.dumps(f"麦克风错误: {e}")
            self._eval_js(f"updateStatus({escaped})")
            self._stop_recording()
            return

        self._update_status_bar()
        threading.Thread(target=self._transcribe_loop, daemon=True).start()

    def _stop_recording(self):
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self._eval_js("setRecording(false)")
        self.window.setTitle_("My Whisper")
        self._update_status_bar()

        # 播放提示音
        sound = NSSound.soundNamed_("Pop")
        if sound:
            sound.play()

    def stopRecordingFromTimeout(self):
        if self.is_recording:
            self._eval_js("updateStatus('无新转录，自动停止')")
            self._stop_recording()

    def _audio_callback(self, indata, frames, time, status):
        self.audio_queue.put(indata.copy().flatten())

    # ── 转写逻辑 ────────────────────────────────────────────────────────────

    def _transcribe_loop(self):
        buf = []
        silence_n = 0
        has_speech = False
        sil_threshold = int(SILENCE_DURATION / BLOCK_DURATION)
        max_chunks = int(MAX_SEGMENT_SECS / BLOCK_DURATION)
        min_chunks = int(MIN_SEGMENT_SECS / BLOCK_DURATION)

        while self.is_recording:
            if time.time() - self._last_transcript_time >= NO_TRANSCRIPT_TIMEOUT:
                log.info("无新转录超时 %ds，自动停止录音", NO_TRANSCRIPT_TIMEOUT)
                self.performSelectorOnMainThread_withObject_waitUntilDone_(
                    "stopRecordingFromTimeout", None, False
                )
                break
            try:
                chunk = self.audio_queue.get(timeout=0.15)
            except queue.Empty:
                continue

            buf.append(chunk)
            rms = np.sqrt(np.mean(chunk ** 2))
            if rms >= SPEECH_THRESHOLD:
                has_speech = True
            silence_n = silence_n + 1 if rms < SILENCE_THRESHOLD else 0

            if len(buf) >= min_chunks and (silence_n >= sil_threshold or len(buf) >= max_chunks):
                if has_speech:
                    self._do_transcribe(buf)
                buf, silence_n, has_speech = [], 0, False

        if len(buf) >= min_chunks and has_speech:
            self._do_transcribe(buf)

        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "onTranscribeFinished:", None, False
        )

    def _do_transcribe(self, buf):
        audio = np.concatenate(buf)
        if np.sqrt(np.mean(audio ** 2)) < SPEECH_THRESHOLD:
            return

        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "onTranscribeStatus:", "转写中...", False
        )

        try:
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=_get_bundled_model_path(self.model),
                language=self.language,
                fp16=True,
                condition_on_previous_text=False,
                initial_prompt="以下是普通话的句子，使用简体中文。",
            )
        except Exception as e:
            log.error("转写出错: %s", e)
            return

        segments = result.get("segments", [])
        valid_texts = []
        for seg in segments:
            if seg.get("no_speech_prob", 0) < NO_SPEECH_PROB_THRESHOLD:
                t = seg.get("text", "").strip()
                if t:
                    valid_texts.append(t)

        text = "".join(valid_texts).strip()
        if text and not self._is_hallucination(text):
            self._last_transcript_time = time.time()
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "appendText:", text, False
            )

        if self.is_recording:
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "onTranscribeStatus:", "录音中...", False
            )

    def _is_hallucination(self, text):
        lower = text.lower()
        for marker in HALLUCINATION_MARKERS:
            if marker.lower() in lower:
                return True

        for length in range(1, max(2, len(text) // 3 + 1)):
            pattern = text[:length]
            if len(pattern.strip()) == 0:
                continue
            repetitions = text.count(pattern)
            if repetitions >= 3 and len(pattern) * repetitions >= len(text) * 0.7:
                return True

        words = text.split()
        if len(words) >= 3 and len(set(words)) == 1:
            return True

        return False

    # ── UI 更新（主线程） ───────────────────────────────────────────────────

    def appendText_(self, text):
        escaped = json.dumps(text)
        self._eval_js(f"appendText({escaped})")

    def onTranscribeStatus_(self, status):
        if self.is_recording:
            escaped = json.dumps(status)
            self._eval_js(f"updateStatus({escaped})")
            self.window.setTitle_(f"My Whisper — {status}")

    def onTranscribeFinished_(self, _):
        self._eval_js("updateStatus('就绪')")
        self.window.setTitle_("My Whisper")

    # ── 菜单操作 ────────────────────────────────────────────────────────────

    @objc.IBAction
    def quitApp_(self, sender):
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        NSApplication.sharedApplication().terminate_(None)

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return False

    def applicationShouldHandleReopen_hasVisibleWindows_(self, app, hasVisibleWindows):
        if not hasVisibleWindows:
            self.window.makeKeyAndOrderFront_(None)
        return True


# ─── 入口 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="My Whisper - 本地实时语音转文字")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    args = parser.parse_args()

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = AppDelegate.alloc().init()
    delegate._args = args
    app.setDelegate_(delegate)

    log.info("启动 runEventLoop")
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
