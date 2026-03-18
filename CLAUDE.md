# CLAUDE.md

## 项目概览

My Whisper 是一个 macOS 本地实时语音转文字工具，使用 mlx_whisper（Apple Silicon 优化）+ PyObjC + WKWebView 构建。

## 架构

- `main.py` — 入口，日志配置，启动 NSApplication
- `config.py` — 常量（音频参数、模型列表、语言、快捷键掩码）
- `app_delegate.py` — UI 层（窗口、WebView、快捷键、菜单栏、录音控制）
- `transcriber.py` — 音频处理 + MLX Whisper 转录
- `hotkey.py` — Carbon 全局快捷键（ctypes 调用 RegisterEventHotKey）
- `settings.py` — 用户设置持久化（NSUserDefaults）
- `ui.html` — Web UI（嵌入 WKWebView），所有可见 UI 元素

## 通信桥

- Python → JS: `evaluateJavaScript`
- JS → Python: `WKScriptMessageHandler`（`_BridgeHandler` 类）

## 构建分发包

始终使用以下流程构建 DMG：

```bash
# 1. 清理旧构建
rm -rf build dist

# 2. py2app 构建
venv/bin/python setup.py py2app

# 3. 复制 mlx（namespace package，py2app 无法自动扫描）
cp -r venv/lib/python3.14/site-packages/mlx \
      dist/My\ Whisper.app/Contents/Resources/lib/python3.14/mlx

# 4. 内嵌默认模型（用户开箱即用）
MODEL_SNAP=$(ls -d ~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo/snapshots/*/ | head -1)
mkdir -p "dist/My Whisper.app/Contents/Resources/models/whisper-large-v3-turbo"
cp -rL "$MODEL_SNAP"/* "dist/My Whisper.app/Contents/Resources/models/whisper-large-v3-turbo/"

# 5. 打包 DMG
hdiutil create -volname "My Whisper" \
  -srcfolder "dist/My Whisper.app" \
  -ov -format UDZO My.Whisper.dmg
```

### 构建注意事项

- mlx 是 namespace package，py2app 无法自动扫描，必须手动复制
- `_sounddevice_data` 必须在 setup.py 的 packages 中（不能在 includes），否则 dylib 被打进 zip 无法加载
- `ui.html` 必须在 setup.py 的 resources 列表中
- setup.py 中 `sys.setrecursionlimit(10000)` 解决 Python 3.14 + modulegraph 递归溢出
- `LSUIElement: True` 在 plist 中确保 App 不出现在 Dock，仅显示菜单栏图标
