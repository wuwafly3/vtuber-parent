"""记忆系统 Pydantic 数据模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProfileFact(BaseModel):
    category: Literal["preference", "personality", "personal_info", "habit", "interest"]
    key: str
    value: str
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class ExtractedEvent(BaseModel):
    content: str
    category: Literal["milestone", "emotion", "decision", "plan", "fact", "general"] = "general"
    importance: int = Field(default=5, ge=1, le=10)


class MemoryExtractionResult(BaseModel):
    """记忆提取 LLM 调用的结构化输出。"""

    profile_updates: list[ProfileFact] = []
    events: list[ExtractedEvent] = []
