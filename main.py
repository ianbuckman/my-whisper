#!/usr/bin/env python3
"""My Whisper - macOS 本地实时语音转文字工具

快捷键 ⌘⇧Space 开始/停止录音，实时转写显示在文本窗口中。
"""

import sys
import os
import logging
import argparse

# 文件日志（写到 ~/Library/Logs/）— 必须在其他模块 import 前配置
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

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
from PyObjCTools import AppHelper

from config import DEFAULT_MODEL, DEFAULT_LANGUAGE
from app_delegate import AppDelegate


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
