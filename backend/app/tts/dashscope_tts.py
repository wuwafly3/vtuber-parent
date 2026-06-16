"""DashScope 百炼 TTS (cosyvoice-v2)。

SDK 是回调式流式:回调在 SDK 内部线程触发,这里用 asyncio.Queue +
loop.call_soon_threadsafe 桥接成 async generator,音频块一到就 yield。
阶段 2 用预置音色;声音克隆 (VoiceEnrollmentService) 后续接入。
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

import dashscope
from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

from app.tts.base import TTSProvider

logger = logging.getLogger("pet.tts")

# 队列结束哨兵
_DONE = object()


class DashScopeTTS(TTSProvider):
    audio_format = "mp3"

    def __init__(
        self,
        api_key: str,
        model: str = "cosyvoice-v2",
        voice: str = "longxiaochun_v2",
    ) -> None:
        dashscope.api_key = api_key
        self.model = model
        self.voice = voice
        self._format = AudioFormat.MP3_24000HZ_MONO_256KBPS

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        text = text.strip()
        if not text:
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def push(item) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, item)

        class _Callback(ResultCallback):
            def on_data(self, data: bytes) -> None:
                push(data)

            def on_complete(self) -> None:
                push(_DONE)

            def on_error(self, message) -> None:  # noqa: ANN001
                push(RuntimeError(f"dashscope tts error: {message}"))

        synthesizer = SpeechSynthesizer(
            model=self.model,
            voice=self.voice,
            format=self._format,
            callback=_Callback(),
        )

        # call() 设了回调时通过回调返回音频,本身阻塞 → 丢进线程池,
        # 同时在主协程里 drain 队列实现"边合成边推"。
        synth_future = loop.run_in_executor(None, synthesizer.call, text)

        try:
            while True:
                item = await queue.get()
                if item is _DONE:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            # 确保后台线程结束,避免泄漏
            await synth_future
