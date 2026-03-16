# My Whisper

macOS 本地实时语音转文字工具。基于 [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) 在 Apple Silicon 上高效运行，所有数据完全在本地处理，不上传任何内容。

![demo](demo.png)

## 下载安装

点击仓库右侧栏的 **Releases** 下载最新版本：

![release](release.png)

1. 前往 [Releases](../../releases) 页面，下载最新的 `My.Whisper.dmg`
2. 双击打开 DMG，将 **My Whisper** 拖入 Applications 文件夹
3. 首次打开前，在终端执行以下命令移除系统隔离标记：
   ```bash
   xattr -cr /Applications/My\ Whisper.app
   ```
4. 双击打开 My Whisper 即可使用

> 应用已内嵌 whisper-large-v3-turbo 模型，无需联网下载，开箱即用。

## 系统要求

- macOS 14.0+
- Apple Silicon（M1 / M2 / M3 / M4）

## 使用方法

### 录音转写

按下 `⌘⇧Space`（或点击窗口中的"开始录音"按钮）开始录音，再次按下停止。App 会自动检测语音停顿并分段转写，结果实时显示在窗口中。15 秒无新转录会自动停止录音。

### 模型 & 语言切换

在窗口顶部的下拉菜单中可以切换模型和语言。内嵌的 Large V3 Turbo 开箱即用，切换到其他模型时会自动从 Hugging Face 下载。

支持语言：中文（默认）、English、日本語、한국어、自动检测。

### 复制 / 编辑

- 点击「复制全部」一键复制全部转写文本
- 点击任意文本段可直接编辑修正
- `⌘A` 全选、`⌘C` 复制

## 权限设置

首次使用需要在 **系统设置 → 隐私与安全性** 中授权：

| 权限 | 用途 |
|------|------|
| **辅助功能** | 全局快捷键 `⌘⇧Space` 监听 |
| **麦克风** | 语音录制 |

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `⌘⇧Space` | 开始 / 停止录音 |
| `⌘Q` | 退出 |

## 日志

运行日志位于 `~/Library/Logs/my-whisper.log`，遇到问题时可查看排查。

## License

MIT
