"""从数据库召回记忆并格式化为 LLM context 注入文本。"""

from __future__ import annotations

import logging

from app.memory.db import MemoryDB
from app.memory.prompts import format_recalled_memory

logger = logging.getLogger("pet.memory.recall")

# 粗估：中文平均 1.5 token/字，英文 0.25 token/字，保守用 2 char/token
_CHARS_PER_TOKEN = 2


class MemoryRecaller:
    def __init__(self, db: MemoryDB, max_events: int = 10, token_budget: int = 1000) -> None:
        self._db = db
        self._max_events = max_events
        self._char_budget = token_budget * _CHARS_PER_TOKEN

    async def recall(self, session_id: str) -> str:
        try:
            profile = await self._db.get_profile(session_id)
            events = await self._db.get_top_events(session_id, limit=self._max_events)
            summaries = await self._db.get_summaries(session_id)
        except Exception:
            logger.exception("memory recall db error, returning empty")
            return ""

        if not profile and not events and not summaries:
            return ""

        text = format_recalled_memory(profile, events, summaries)

        # 超出 budget 时逐步裁剪低重要度事件
        while len(text) > self._char_budget and events:
            events.pop()
            text = format_recalled_memory(profile, events, summaries)

        return text
