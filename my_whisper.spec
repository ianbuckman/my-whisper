# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

# 收集 mlx 相关包
mlx_datas, mlx_binaries, mlx_hiddenimports = collect_all('mlx')
mlxw_datas, mlxw_binaries, mlxw_hiddenimports = collect_all('mlx_whisper')
sd_datas, sd_binaries, sd_hiddenimports = collect_all('sounddevice')
sd_data_datas, sd_data_binaries, sd_data_hiddenimports = collect_all('_sounddevice_data')
# scipy 只被 mlx_whisper/timing.py 用到 (我们不需要该功能)，用 runtime hook mock 掉

all_datas = mlx_datas + mlxw_datas + sd_datas + sd_data_datas
all_binaries = mlx_binaries + mlxw_binaries + sd_binaries + sd_data_binaries
all_hiddenimports = (
    mlx_hiddenimports + mlxw_hiddenimports + sd_hiddenimports + sd_data_hiddenimports
    + collect_submodules('huggingface_hub')
    + collect_submodules('safetensors')
    + collect_submodules('tokenizers')
    + collect_submodules('numpy')
    + [
        'objc', 'AppKit', 'Foundation', 'PyObjCTools', 'PyObjCTools.AppHelper',
        'Cocoa', 'CoreFoundation',
    ]
)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_scipy.py'],
    excludes=['tkinter', 'matplotlib', 'PIL', 'scipy', 'pandas', 'pytest', 'torch', 'sympy', 'numba', 'llvmlite'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='My Whisper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch='arm64',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='My Whisper',
)

app = BUNDLE(
    coll,
    name='My Whisper.app',
    icon='AppIcon.icns',
    bundle_identifier='com.nqt.my-whisper',
    info_plist={
        'CFBundleName': 'My Whisper',
        'CFBundleDisplayName': 'My Whisper',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0',
        'LSMinimumSystemVersion': '14.0',
        'NSMicrophoneUsageDescription': 'My Whisper 需要访问麦克风来录制语音并转写为文字。',
        'NSHighResolutionCapable': True,
    },
)
