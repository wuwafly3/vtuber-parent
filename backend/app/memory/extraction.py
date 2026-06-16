"""LLM 驱动的记忆提取（用户画像 + 重要事件）。"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.memory.models import MemoryExtractionResult
from app.memory.prompts import EXTRACTION_SYSTEM, extraction_user_prompt

logger = logging.getLogger("pet.memory.extraction")


class MemoryExtractor:
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def extract(
        self,
        user_text: str,
        assistant_text: str,
        existing_profile: list[dict[str, Any]],
    ) -> MemoryExtractionResult:
        user_prompt = extraction_user_prompt(existing_profile, user_text, assistant_text)
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
            return MemoryExtractionResult.model_validate(data)
        except Exception:
            logger.exception("memory extraction failed, skipping turn")
            return MemoryExtractionResult()
