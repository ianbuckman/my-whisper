"""My Whisper 转写引擎 — 纯 Python，不依赖 PyObjC"""

import logging
import queue
import threading
import time

import numpy as np
import mlx_whisper

from config import (
    SAMPLE_RATE,
    BLOCK_DURATION,
    SPEECH_THRESHOLD,
    SILENCE_DURATION,
    MAX_SEGMENT_SECS,
    MIN_SEGMENT_SECS,
    NO_SPEECH_PROB_THRESHOLD,
    NO_TRANSCRIPT_TIMEOUT,
    HALLUCINATION_MARKERS,
    get_bundled_model_path,
)

log = logging.getLogger("mywhisper")


class Transcriber:
    """管理模型加载、音频分段和语音转写。

    通过回调与 UI 层解耦：
    - on_text(text)       有效转录文本
    - on_status(status)   状态变化（如"转写中..."）
    - on_finished()       转写循环结束
    - on_timeout()        无新转录超时
    - on_model_loaded()   模型加载成功
    - on_model_error(msg) 模型加载失败
    """

    def __init__(self, model, language, *,
                 on_text, on_status, on_finished, on_timeout,
                 on_model_loaded, on_model_error):
        self.model = model
        self.language = language
        self.model_loaded = False
        self.is_running = False
        self._last_transcript_time = 0
        self._audio_queue = None

        self._on_text = on_text
        self._on_status = on_status
        self._on_finished = on_finished
        self._on_timeout = on_timeout
        self._on_model_loaded = on_model_loaded
        self._on_model_error = on_model_error

    # ── 模型加载 ──────────────────────────────────────────────────────────

    def load_model(self):
        """在后台线程加载（预热）模型"""
        def _load():
            try:
                log.info("开始加载模型: %s", self.model)
                dummy = np.zeros(SAMPLE_RATE, dtype=np.float32)
                mlx_whisper.transcribe(
                    dummy,
                    path_or_hf_repo=get_bundled_model_path(self.model),
                    fp16=True,
                )
                self.model_loaded = True
                self._on_model_loaded()
            except Exception as e:
                log.error("模型加载失败: %s", e)
                self._on_model_error(str(e))

        threading.Thread(target=_load, daemon=True).start()

    def change_model(self, model_repo):
        """切换 Whisper 模型"""
        if model_repo == self.model:
            return
        self.model = model_repo
        self.model_loaded = False
        self.load_model()

    # ── 转写循环 ──────────────────────────────────────────────────────────

    def start(self, audio_queue):
        """启动转写循环（在新线程中）"""
        self._audio_queue = audio_queue
        self.is_running = True
        self._last_transcript_time = time.time()
        threading.Thread(target=self._transcribe_loop, daemon=True).start()

    def stop(self):
        """停止转写循环"""
        self.is_running = False

    def _transcribe_loop(self):
        buf = []
        silence_n = 0
        has_speech = False
        sil_threshold = int(SILENCE_DURATION / BLOCK_DURATION)
        max_chunks = int(MAX_SEGMENT_SECS / BLOCK_DURATION)
        min_chunks = int(MIN_SEGMENT_SECS / BLOCK_DURATION)

        while self.is_running:
            if time.time() - self._last_transcript_time >= NO_TRANSCRIPT_TIMEOUT:
                log.info("无新转录超时 %ds，自动停止录音", NO_TRANSCRIPT_TIMEOUT)
                self._on_timeout()
                break
            try:
                chunk = self._audio_queue.get(timeout=0.15)
            except queue.Empty:
                continue

            buf.append(chunk)
            rms = np.sqrt(np.mean(chunk ** 2))
            if rms >= SPEECH_THRESHOLD:
                has_speech = True
            silence_n = silence_n + 1 if rms < SPEECH_THRESHOLD else 0

            if len(buf) >= min_chunks and (silence_n >= sil_threshold or len(buf) >= max_chunks):
                if has_speech:
                    self._do_transcribe(buf)
                else:
                    log.debug("丢弃无语音段落: %d chunks, max_rms=%.4f", len(buf),
                              max(np.sqrt(np.mean(c ** 2)) for c in buf))
                buf, silence_n, has_speech = [], 0, False

        if len(buf) >= min_chunks and has_speech:
            self._do_transcribe(buf)

        self._on_finished()

    def _do_transcribe(self, buf):
        # 裁掉尾部静默，保留最多 2 个静默块作为自然结尾
        tail_silence = 0
        for chunk in reversed(buf):
            if np.sqrt(np.mean(chunk ** 2)) < SPEECH_THRESHOLD:
                tail_silence += 1
            else:
                break
        trim = max(0, tail_silence - 2)
        if trim > 0:
            buf = buf[:-trim]
        audio = np.concatenate(buf)

        self._on_status("转写中...")

        try:
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=get_bundled_model_path(self.model),
                language=self.language,
                fp16=True,
                condition_on_previous_text=False,
                initial_prompt="以下是普通话的句子，使用简体中文。",
            )
        except Exception as e:
            log.error("转写出错: %s", e)
            return

        segments = result.get("segments", [])
        valid_texts = []
        for seg in segments:
            if seg.get("no_speech_prob", 0) < NO_SPEECH_PROB_THRESHOLD:
                t = seg.get("text", "").strip()
                if t:
                    valid_texts.append(t)

        if segments and not valid_texts:
            log.debug("所有 segment 被 no_speech_prob 过滤: %s",
                      [(s.get("text", "").strip(), f'{s.get("no_speech_prob", 0):.2f}') for s in segments])

        text = "".join(valid_texts).strip()
        if text and not self._is_hallucination(text):
            self._last_transcript_time = time.time()
            self._on_text(text)

        if self.is_running:
            self._on_status("录音中...")

    # ── 幻觉检测 ──────────────────────────────────────────────────────────

    @staticmethod
    def _is_hallucination(text):
        lower = text.lower()
        for marker in HALLUCINATION_MARKERS:
            if marker.lower() in lower:
                return True

        for length in range(2, max(3, len(text) // 3 + 1)):
            pattern = text[:length]
            if len(pattern.strip()) == 0:
                continue
            repetitions = text.count(pattern)
            if repetitions >= 3 and len(pattern) * repetitions >= len(text) * 0.7:
                return True

        words = text.split()
        if len(words) >= 3 and len(set(words)) == 1:
            return True

        return False
