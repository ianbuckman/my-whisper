#!/usr/bin/env python3
"""My Whisper - macOS 本地实时语音转文字工具

快捷键 ⌘⇧Space 开始/停止录音，实时转写显示在文本窗口中。
"""

import re
import sys
import os
import logging
import threading
import queue
import argparse

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
    log.info("import objc/AppKit OK")
except Exception as e:
    log.error("import objc/AppKit FAILED: %s", e)
    sys.exit(1)

from AppKit import (
    NSApplication,
    NSMenu,
    NSMenuItem,
    NSWindow,
    NSTextView,
    NSScrollView,
    NSButton,
    NSFont,
    NSColor,
    NSMakeRect,
    NSMakeSize,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskMiniaturizable,
    NSBackingStoreBuffered,
    NSViewWidthSizable,
    NSViewHeightSizable,
    NSViewMaxYMargin,
    NSOnState,
    NSOffState,
    NSBezelStyleToolbar,
    NSControlSizeRegular,
)
from Foundation import NSObject, NSLog
from PyObjCTools import AppHelper


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

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_LANGUAGE = "zh"

NSEventMaskKeyDown = 1 << 10
NSEventModifierFlagCommand = 1 << 20
NSEventModifierFlagShift = 1 << 17

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

        self._setup_main_menu()
        self._setup_window()
        self._setup_hotkey()

        # 启动时显示窗口
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

        self._load_model()
        log.info("初始化完成")

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

        # 语言菜单
        lang_item = NSMenuItem.alloc().init()
        self.lang_menu = NSMenu.alloc().initWithTitle_("语言")
        for code, name in LANGUAGES:
            li = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                name, "setLanguage:", ""
            )
            li.setRepresentedObject_(code)
            if code == self.language:
                li.setState_(NSOnState)
            self.lang_menu.addItem_(li)
        lang_item.setSubmenu_(self.lang_menu)
        main_menu.addItem_(lang_item)

        NSApplication.sharedApplication().setMainMenu_(main_menu)

    # ── 窗口（带工具栏按钮）───────────────────────────────────────────────

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

        content = self.window.contentView()
        content_frame = content.frame()
        w = content_frame.size.width
        h = content_frame.size.height

        # ── 工具栏区域（顶部 40px）──
        toolbar_h = 40
        toolbar_y = h - toolbar_h

        # 录音按钮
        self.record_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(10, toolbar_y + 6, 180, 28)
        )
        self.record_btn.setTitle_("开始录音 ⌘⇧Space")
        self.record_btn.setBezelStyle_(NSBezelStyleToolbar)
        self.record_btn.setTarget_(self)
        self.record_btn.setAction_("toggleRecording:")
        self.record_btn.setAutoresizingMask_(NSViewMaxYMargin)
        content.addSubview_(self.record_btn)

        # 复制按钮
        copy_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(w - 130, toolbar_y + 6, 55, 28)
        )
        copy_btn.setTitle_("复制")
        copy_btn.setBezelStyle_(NSBezelStyleToolbar)
        copy_btn.setTarget_(self)
        copy_btn.setAction_("copyAll:")
        copy_btn.setAutoresizingMask_(NSViewMaxYMargin)
        content.addSubview_(copy_btn)

        # 清空按钮
        clear_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(w - 65, toolbar_y + 6, 55, 28)
        )
        clear_btn.setTitle_("清空")
        clear_btn.setBezelStyle_(NSBezelStyleToolbar)
        clear_btn.setTarget_(self)
        clear_btn.setAction_("clearText:")
        clear_btn.setAutoresizingMask_(NSViewMaxYMargin)
        content.addSubview_(clear_btn)

        # 状态标签
        self.status_label = AppKit.NSTextField.labelWithString_("加载模型中...")
        self.status_label.setFrame_(NSMakeRect(200, toolbar_y + 10, 300, 20))
        self.status_label.setFont_(NSFont.systemFontOfSize_(12))
        self.status_label.setTextColor_(NSColor.secondaryLabelColor())
        self.status_label.setAutoresizingMask_(NSViewMaxYMargin)
        content.addSubview_(self.status_label)

        # ── 文本区域 ──
        text_frame = NSMakeRect(0, 0, w, toolbar_y)
        scroll = NSScrollView.alloc().initWithFrame_(text_frame)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)

        text_size = scroll.contentSize()
        self.text_view = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, text_size.width, text_size.height)
        )
        self.text_view.setMinSize_(NSMakeSize(0, text_size.height))
        self.text_view.setMaxSize_(NSMakeSize(1e7, 1e7))
        self.text_view.setVerticallyResizable_(True)
        self.text_view.setHorizontallyResizable_(False)
        self.text_view.setAutoresizingMask_(NSViewWidthSizable)
        self.text_view.textContainer().setWidthTracksTextView_(True)

        font = NSFont.fontWithName_size_("PingFang SC", 16)
        if not font:
            font = NSFont.systemFontOfSize_(16)
        self.text_view.setFont_(font)
        self.text_view.setEditable_(True)
        self.text_view.setSelectable_(True)
        self.text_view.setRichText_(False)
        self.text_view.setTextContainerInset_(NSMakeSize(10, 10))
        self.text_view.setAllowsUndo_(True)

        scroll.setDocumentView_(self.text_view)
        content.addSubview_(scroll)
        self.window.setInitialFirstResponder_(self.text_view)

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

    # ── 模型加载 ────────────────────────────────────────────────────────────

    def _load_model(self):
        def load():
            try:
                log.info("开始加载模型: %s", self.model)
                dummy = np.zeros(SAMPLE_RATE, dtype=np.float32)
                mlx_whisper.transcribe(dummy, path_or_hf_repo=self.model, fp16=True)
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
        self.status_label.setStringValue_("就绪")
        self.window.setTitle_("My Whisper")
        log.info("模型加载完成")

    def onModelError_(self, error_msg):
        self.status_label.setStringValue_(f"模型加载失败: {error_msg}")

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
        self.is_recording = True
        self.record_btn.setTitle_("停止录音 ⌘⇧Space")
        self.status_label.setStringValue_("录音中...")
        self.window.setTitle_("My Whisper — 录音中...")

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
            self.status_label.setStringValue_(f"麦克风错误: {e}")
            self._stop_recording()
            return

        threading.Thread(target=self._transcribe_loop, daemon=True).start()

    def _stop_recording(self):
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.record_btn.setTitle_("开始录音 ⌘⇧Space")
        self.window.setTitle_("My Whisper")

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
                path_or_hf_repo=self.model,
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
        storage = self.text_view.textStorage()
        current = storage.string()
        if current and len(current) > 0:
            storage.mutableString().appendString_(text)
        else:
            storage.mutableString().appendString_(text)
        end = storage.length()
        self.text_view.scrollRangeToVisible_((end, 0))

    def onTranscribeStatus_(self, status):
        if self.is_recording:
            self.status_label.setStringValue_(status)
            self.window.setTitle_(f"My Whisper — {status}")

    def onTranscribeFinished_(self, _):
        self.status_label.setStringValue_("就绪")
        self.window.setTitle_("My Whisper")

    # ── 菜单操作 ────────────────────────────────────────────────────────────

    @objc.IBAction
    def clearText_(self, sender):
        self.text_view.textStorage().mutableString().setString_("")

    @objc.IBAction
    def copyAll_(self, sender):
        text = self.text_view.textStorage().string()
        pb = AppKit.NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
        self.status_label.setStringValue_("已复制到剪贴板")

    @objc.IBAction
    def setLanguage_(self, sender):
        self.language = sender.representedObject()
        for i in range(self.lang_menu.numberOfItems()):
            self.lang_menu.itemAtIndex_(i).setState_(NSOffState)
        sender.setState_(NSOnState)
        log.info("语言切换为: %s", sender.title())

    @objc.IBAction
    def quitApp_(self, sender):
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        NSApplication.sharedApplication().terminate_(None)

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return True


# ─── 入口 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="My Whisper - 本地实时语音转文字")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    args = parser.parse_args()

    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    delegate._args = args
    app.setDelegate_(delegate)

    log.info("启动 runEventLoop")
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
