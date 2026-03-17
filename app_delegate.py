"""My Whisper AppDelegate — PyObjC UI 层"""

import json
import logging
import queue

import numpy as np
import sounddevice as sd
import objc
import AppKit
import WebKit
from AppKit import (
    NSApplication,
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
from Foundation import NSObject, NSURL
from WebKit import WKWebView, WKWebViewConfiguration

from config import (
    SAMPLE_RATE,
    BLOCK_SIZE,
    MODELS,
    LANGUAGES,
    NSEventMaskKeyDown,
    NSEventModifierFlagCommand,
    NSEventModifierFlagShift,
    get_resource_path,
)
from transcriber import Transcriber

log = logging.getLogger("mywhisper")


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
        self.audio_queue = queue.Queue()
        self.stream = None
        self._web_loaded = False
        self._pending_js = []

        language = self._args.language if self._args.language != "auto" else None

        # 创建 Transcriber，通过回调接线到主线程
        self.transcriber = Transcriber(
            model=self._args.model,
            language=language,
            on_text=lambda t: self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "appendText:", t, False),
            on_status=lambda s: self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "onTranscribeStatus:", s, False),
            on_finished=lambda: self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "onTranscribeFinished:", None, False),
            on_timeout=lambda: self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "stopRecordingFromTimeout", None, False),
            on_model_loaded=lambda: self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "onModelLoaded:", None, False),
            on_model_error=lambda msg: self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "onModelError:", msg, False),
        )

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

        self.window.makeKeyAndOrderFront_(None)
        self.transcriber.load_model()
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
        model_val = json.dumps(self.transcriber.model)
        langs_json = json.dumps(LANGUAGES)
        lang_val = json.dumps(self.transcriber.language)
        self._eval_js(f"initModels({models_json}, {model_val})")
        self._eval_js(f"initLanguages({langs_json}, {lang_val})")
        if self.transcriber.model_loaded:
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
            self.transcriber.language = lang if lang else None
            log.info("语言切换为: %s", self.transcriber.language)
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

    # ── 主菜单 ────────────────────────────────────────────────────────────

    def _setup_main_menu(self):
        main_menu = NSMenu.alloc().init()

        app_item = NSMenuItem.alloc().init()
        app_menu = NSMenu.alloc().initWithTitle_("My Whisper")
        app_menu.addItemWithTitle_action_keyEquivalent_("关于 My Whisper", "orderFrontStandardAboutPanel:", "")
        app_menu.addItem_(NSMenuItem.separatorItem())
        app_menu.addItemWithTitle_action_keyEquivalent_("退出 My Whisper", "quitApp:", "q")
        app_item.setSubmenu_(app_menu)
        main_menu.addItem_(app_item)

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

        html_path = get_resource_path("ui.html")
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

    # ── 模型回调（主线程）────────────────────────────────────────────────────

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
        if model_repo == self.transcriber.model:
            return
        if self.is_recording:
            self._stop_recording()
        self._eval_js("setModelLoaded(false)")
        self._eval_js("updateStatus('加载模型中...')")
        self.window.setTitle_("My Whisper — 加载模型中...")
        log.info("切换模型: %s", model_repo)
        self.transcriber.change_model(model_repo)

    # ── 录音控制 ────────────────────────────────────────────────────────────

    @objc.IBAction
    def toggleRecording_(self, sender):
        if not self.transcriber.model_loaded:
            return
        if self.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        if not self.transcriber.model_loaded:
            return
        self.is_recording = True
        self._eval_js("setRecording(true)")
        self._eval_js("updateStatus('录音中...')")
        self.window.setTitle_("My Whisper — 录音中...")

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
        self.transcriber.start(self.audio_queue)

    def _stop_recording(self):
        self.is_recording = False
        self.transcriber.stop()
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self._eval_js("setRecording(false)")
        self.window.setTitle_("My Whisper")
        self._update_status_bar()

        sound = NSSound.soundNamed_("Pop")
        if sound:
            sound.play()

    def stopRecordingFromTimeout(self):
        if self.is_recording:
            self._eval_js("updateStatus('无新转录，自动停止')")
            self._stop_recording()

    def _audio_callback(self, indata, frames, time, status):
        self.audio_queue.put(indata.copy().flatten())

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
        self.transcriber.stop()
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
