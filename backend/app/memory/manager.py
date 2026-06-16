"""MemoryManager — 记忆系统的统一门面。"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.memory.compression import ContextCompressor
from app.memory.db import MemoryDB
from app.memory.extraction import MemoryExtractor
from app.memory.recall import MemoryRecaller

logger = logging.getLogger("pet.memory.manager")


class MemoryManager:
    def __init__(
        self,
        db_path: str,
        llm_client: AsyncOpenAI,
        extraction_model: str,
        compression_model: str,
        compression_threshold: int = 10,
        compression_batch: int = 6,
        max_events: int = 10,
        token_budget: int = 1000,
    ) -> None:
        self._db = MemoryDB(db_path)
        self._extractor = MemoryExtractor(llm_client, extraction_model)
        self._compressor = ContextCompressor(llm_client, compression_model)
        self._recaller = MemoryRecaller(self._db, max_events=max_events, token_budget=token_budget)
        self._compression_threshold = compression_threshold
        self._compression_batch = compression_batch

    async def initialize(self) -> None:
        await self._db.init()

    async def close(self) -> None:
        await self._db.close()

    # ------------------------------------------------------------------
    # 召回（同步路径，在 LLM 调用前执行）
    # ------------------------------------------------------------------

    async def get_context_memories(self, session_id: str) -> str:
        return await self._recaller.recall(session_id)

    # ------------------------------------------------------------------
    # 提取 + 压缩（异步后台，在助手回复后 fire-and-forget）
    # ------------------------------------------------------------------

    async def process_turn(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        pop_messages_fn,  # callable: (session_id, count) -> list[dict]
    ) -> None:
        try:
            # 1. 记录本轮
            turn_number = await self._db.get_turn_count(session_id) + 1
            await self._db.add_turn(session_id, turn_number, user_text, assistant_text)

            # 2. 提取画像 + 事件
            existing_profile = await self._db.get_profile(session_id)
            result = await self._extractor.extract(user_text, assistant_text, existing_profile)

            for fact in result.profile_updates:
                await self._db.upsert_profile_fact(session_id, fact, turn_number)

            for event in result.events:
                await self._db.add_event(session_id, event, turn_number)

            if result.profile_updates:
                logger.info("profile updated: %d facts", len(result.profile_updates))
            if result.events:
                logger.info("events extracted: %d", len(result.events))

            # 3. 检查是否需要压缩
            if turn_number >= self._compression_threshold and turn_number % (self._compression_threshold // 2) == 0:
                await self._maybe_compress(session_id, turn_number, pop_messages_fn)

        except Exception:
            logger.exception("process_turn failed (non-blocking)")

    async def _maybe_compress(
        self, session_id: str, current_turn: int, pop_messages_fn
    ) -> None:
        # 取走最旧的 batch*2 条消息（user+assistant 成对）
        old_messages: list[dict] = pop_messages_fn(session_id, self._compression_batch * 2)
        if not old_messages:
            return

        existing_summaries = await self._db.get_summaries(session_id)
        previous_summary = existing_summaries[-1]["summary"] if existing_summaries else None

        summary = await self._compressor.compress(old_messages, previous_summary)
        if not summary:
            return

        turn_start = current_turn - self._compression_batch
        await self._db.add_summary(
            session_id,
            summary,
            turn_start=max(1, turn_start),
            turn_end=current_turn - 1,
            msg_count=len(old_messages),
        )
        logger.info("compressed %d messages into summary (turns %d-%d)", len(old_messages), turn_start, current_turn - 1)
