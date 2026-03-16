#!/bin/bash
# My Whisper - 一键安装脚本
set -e

echo "=== My Whisper 安装 ==="
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 Python3"
    echo "请先安装: brew install python"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python 版本: $PY_VERSION"

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate

# 安装依赖
echo "安装依赖（首次可能需要几分钟）..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo ""
echo "=== 安装完成 ==="
echo ""
echo "运行方式:"
echo "  source venv/bin/activate"
echo "  python main.py"
echo ""
echo "可选参数:"
echo "  --model MODEL     指定模型 (默认: mlx-community/whisper-large-v3-turbo)"
echo "  --language LANG   语言: zh/en/ja/ko/auto (默认: zh)"
echo ""
echo "注意事项:"
echo "  1. 首次运行会下载模型（约 3GB），请耐心等待"
echo "  2. 需要在 系统设置 → 隐私与安全 → 辅助功能 中允许终端访问（用于全局快捷键）"
echo "  3. 需要在 系统设置 → 隐私与安全 → 麦克风 中允许终端访问"
echo "  4. 快捷键: ⌘⇧Space 开始/停止录音"
