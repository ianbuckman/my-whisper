"""
py2app 构建配置
用法: python setup.py py2app
"""
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
    },
    "packages": [
        "mlx_whisper",
        "mlx",
        "numpy",
        "sounddevice",
        "huggingface_hub",
        "safetensors",
        "tokenizers",
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
        "PyObjCTools",
        "PyObjCTools.AppHelper",
        "_sounddevice_data",
    ],
    "frameworks": [],
    "resources": [],
    "strip": True,
    "optimize": 2,
}

setup(
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
