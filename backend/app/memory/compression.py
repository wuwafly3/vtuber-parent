"""LLM 驱动的对话上下文压缩。"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.memory.prompts import COMPRESSION_SYSTEM, compression_user_prompt

logger = logging.getLogger("pet.memory.compression")


class ContextCompressor:
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def compress(
        self,
        messages: list[dict[str, str]],
        previous_summary: str | None = None,
    ) -> str | None:
        if not messages:
            return None
        user_prompt = compression_user_prompt(messages, previous_summary)
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": COMPRESSION_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            return (resp.choices[0].message.content or "").strip() or None
        except Exception:
            logger.exception("context compression failed, skipping")
            return None
