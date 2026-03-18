"""My Whisper 配置常量与工具函数"""

import sys
import os
import logging

log = logging.getLogger("mywhisper")

# ─── 音频参数 ─────────────────────────────────────────────────────────────────

SAMPLE_RATE = 16000
BLOCK_DURATION = 0.1
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_DURATION)

SPEECH_THRESHOLD = 0.015
SILENCE_DURATION = 0.8
MAX_SEGMENT_SECS = 15
MIN_SEGMENT_SECS = 0.5
NO_SPEECH_PROB_THRESHOLD = 0.6
NO_TRANSCRIPT_TIMEOUT = 45  # 秒，无新转录则自动停止录音

# ─── 模型与语言 ───────────────────────────────────────────────────────────────

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_LANGUAGE = "zh"

MODELS = [
    ("mlx-community/whisper-tiny", "Tiny (39M)"),
    ("mlx-community/whisper-base", "Base (74M)"),
    ("mlx-community/whisper-small", "Small (244M)"),
    ("mlx-community/whisper-medium", "Medium (769M)"),
    ("mlx-community/whisper-large-v3-turbo", "Large V3 Turbo (809M)"),
]

LANGUAGES = [
    ("zh", "中文"),
    ("en", "English"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    (None, "自动检测"),
]

# ─── 快捷键掩码 ───────────────────────────────────────────────────────────────

NSEventMaskKeyDown = 1 << 10
NSEventModifierFlagCommand = 1 << 20
NSEventModifierFlagShift = 1 << 17
NSEventModifierFlagOption = 1 << 19
NSEventModifierFlagControl = 1 << 18

# ─── 幻觉标记 ─────────────────────────────────────────────────────────────────

HALLUCINATION_MARKERS = [
    "谢谢观看", "字幕由", "请不吝点赞", "Amara",
    "Subscribe", "Thank you for watching",
    "Copyright", "copyright",
    "感谢收看",
]

# ─── 工具函数 ─────────────────────────────────────────────────────────────────


def get_resource_path(filename):
    """获取资源文件路径（兼容 py2app / PyInstaller / 开发环境）"""
    res = os.environ.get("RESOURCEPATH")
    if res:
        return os.path.join(res, filename)
    if getattr(sys, '_MEIPASS', None):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


def get_bundled_model_path(model_repo):
    """如果 bundle 内嵌了模型，返回本地路径；否则返回原始 repo 名"""
    model_name = model_repo.split("/")[-1]
    candidates = []
    res = os.environ.get("RESOURCEPATH")
    if res:
        candidates.append(os.path.join(res, "models", model_name))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", model_name))
    for bundled in candidates:
        if os.path.isdir(bundled) and os.path.exists(os.path.join(bundled, "config.json")):
            log.info("使用内嵌模型: %s", bundled)
            return bundled
    log.info("未找到内嵌模型 %s，候选路径: %s", model_name, candidates)
    return model_repo
