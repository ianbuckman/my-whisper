#!/bin/bash
# build_app.sh - 构建 My Whisper.app
set -e

APP_NAME="My Whisper"
APP_DIR="${APP_NAME}.app"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"

echo "=== 构建 ${APP_NAME}.app ==="

# 清理旧构建
rm -rf "$APP_DIR"

# 创建 .app 目录结构
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# ── Info.plist ──────────────────────────────────────────────────────────────
cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>My Whisper</string>
    <key>CFBundleDisplayName</key>
    <string>My Whisper</string>
    <key>CFBundleIdentifier</key>
    <string>com.nqt.my-whisper</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSMicrophoneUsageDescription</key>
    <string>My Whisper 需要访问麦克风来录制语音并转写为文字。</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

# ── 原生启动器（现场编译）────────────────────────────────────────────────────
echo "编译 launcher..."
clang -framework Cocoa -Wall \
      -o "$APP_DIR/Contents/MacOS/launcher" \
      "$PROJECT_DIR/launcher.m"
chmod +x "$APP_DIR/Contents/MacOS/launcher"

# ── 复制脚本和 HTML ──────────────────────────────────────────────────────────
cp "$PROJECT_DIR/main.py"  "$APP_DIR/Contents/Resources/main.py"
cp "$PROJECT_DIR/ui.html"  "$APP_DIR/Contents/Resources/ui.html"

# ── 复制 venv（-L 解引用符号链接，避免 bundle 内悬空链接）──────────────────
echo "复制 venv（请稍候）..."
cp -rL "$PROJECT_DIR/venv" "$APP_DIR/Contents/Resources/venv"

# ── 生成应用图标 ─────────────────────────────────────────────────────────────
echo "生成应用图标..."
ICNS_PATH="$APP_DIR/Contents/Resources/AppIcon.icns"
BUNDLE_PYTHON="$APP_DIR/Contents/Resources/venv/bin/python"
"$BUNDLE_PYTHON" - "$ICNS_PATH" << 'ICON_SCRIPT'
import subprocess, os, sys, tempfile, shutil
import objc
from AppKit import (
    NSImage, NSBitmapImageRep, NSColor, NSFont,
    NSMakeRect, NSPNGFileType, NSString,
    NSForegroundColorAttributeName, NSFontAttributeName,
    NSBezierPath,
)
from Foundation import NSSize, NSPoint, NSDictionary

ICNS_OUTPUT = sys.argv[1]

def render_icon(size, output_path):
    img = NSImage.alloc().initWithSize_(NSSize(size, size))
    img.lockFocus()

    rect = NSMakeRect(0, 0, size, size)
    radius = size * 0.2

    # 深色背景
    NSColor.colorWithCalibratedRed_green_blue_alpha_(0.08, 0.08, 0.12, 1.0).set()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius).fill()

    # 蓝色叠加
    NSColor.colorWithCalibratedRed_green_blue_alpha_(0.15, 0.35, 0.85, 0.25).set()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius).fill()

    # 麦克风 emoji
    emoji_font = NSFont.systemFontOfSize_(size * 0.5)
    emoji_attrs = NSDictionary.dictionaryWithObjectsAndKeys_(
        emoji_font, NSFontAttributeName,
        None,
    )
    emoji = NSString.stringWithString_("\U0001f399")
    es = emoji.sizeWithAttributes_(emoji_attrs)
    emoji.drawAtPoint_withAttributes_(
        NSPoint((size - es.width) / 2, (size - es.height) / 2 + size * 0.05),
        emoji_attrs,
    )

    # 底部 "W" 标记
    w_font = NSFont.boldSystemFontOfSize_(size * 0.16)
    w_attrs = NSDictionary.dictionaryWithObjectsAndKeys_(
        w_font, NSFontAttributeName,
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.4, 0.7, 1.0, 0.85),
        NSForegroundColorAttributeName,
        None,
    )
    w = NSString.stringWithString_("W")
    ws = w.sizeWithAttributes_(w_attrs)
    w.drawAtPoint_withAttributes_(
        NSPoint((size - ws.width) / 2, size * 0.1),
        w_attrs,
    )

    img.unlockFocus()

    tiff = img.TIFFRepresentation()
    rep = NSBitmapImageRep.imageRepWithData_(tiff)
    png = rep.representationUsingType_properties_(NSPNGFileType, None)
    png.writeToFile_atomically_(output_path, True)


# iconutil 要求的文件名格式
iconset = tempfile.mkdtemp(suffix=".iconset")
entries = [
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
]

for size, name in entries:
    render_icon(size, os.path.join(iconset, name))

subprocess.run(["iconutil", "-c", "icns", iconset, "-o", ICNS_OUTPUT], check=True)
shutil.rmtree(iconset)
print(f"图标已生成: {ICNS_OUTPUT}")
ICON_SCRIPT

echo ""
echo "=== 构建完成 ==="
echo ""
echo "  应用位置: $(pwd)/$APP_DIR"
echo ""
echo "  使用方式:"
echo "    1. 在 Finder 中双击 '$APP_DIR' 启动"
echo "    2. 拖到 Dock 栏固定"
echo "    3. 拖到 /Applications 文件夹"
echo ""
echo "  首次启动需要在 系统设置 → 隐私与安全 中授权:"
echo "    - 辅助功能（全局快捷键）"
echo "    - 麦克风（录音）"
