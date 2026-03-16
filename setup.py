"""
py2app 构建配置
用法: python setup.py py2app
"""
import sys
sys.setrecursionlimit(10000)

from setuptools import setup

APP = ["main.py"]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "AppIcon.icns",
    "plist": {
        "CFBundleName": "My Whisper",
        "CFBundleDisplayName": "My Whisper",
        "CFBundleIdentifier": "com.nqt.my-whisper",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0",
        "LSMinimumSystemVersion": "14.0",
        "NSMicrophoneUsageDescription": "My Whisper 需要访问麦克风来录制语音并转写为文字。",
        "NSHighResolutionCapable": True,
        "LSUIElement": True,
    },
    "packages": [
        "mlx_whisper",
        "_sounddevice_data",
        "numpy",
        "sounddevice",
        "huggingface_hub",
        "tqdm",
        "regex",
        "requests",
        "certifi",
        "charset_normalizer",
        "idna",
        "urllib3",
        "filelock",
        "fsspec",
        "yaml",
        "packaging",
    ],
    "includes": [
        "objc",
        "AppKit",
        "Foundation",
        "WebKit",
        "PyObjCTools",
        "PyObjCTools.AppHelper",
    ],
    "frameworks": [],
    "resources": ["ui.html"],
    "excludes": [
        "PyInstaller", "mlx", "mlx.core", "mlx.nn", "mlx.optimizers",
        "torch", "torchgen", "sympy",
    ],
}

setup(
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
