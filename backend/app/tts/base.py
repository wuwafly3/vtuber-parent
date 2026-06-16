"""TTS provider 抽象接口。

阶段 2 只实现 DashScope 预置音色;声音克隆与本地引擎后续接入,
对 WS handler 暴露的形态保持不变(给文本、异步吐音频块)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class TTSProvider(ABC):
    """文本→音频流。实现类把文本合成为音频字节块,异步逐块吐出。"""

    #: 输出音频容器格式 (前端 MediaSource 需要),如 "mp3"
    audio_format: str = "mp3"

    @abstractmethod
    def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """把一段文本合成为音频,异步逐块 yield 原始音频字节。"""
        raise NotImplementedError
