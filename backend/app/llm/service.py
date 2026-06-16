"""LLM 流式封装 (provider 无关,openai-compatible)。

输出统一成内部 LLMChunk:阶段 1 只用 text/finish,tool_call 为阶段 4 agent 预留。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

from openai import AsyncOpenAI


class ChunkType(str, Enum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    FINISH = "finish"


@dataclass
class LLMChunk:
    type: ChunkType
    text: str = ""
    # 阶段 4 用:增量 tool call 信息
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None


class LLMService:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """逐 chunk 流式输出。

        messages: openai 格式的对话历史 (含 system)。
        tools: 阶段 4 传入 function 定义;阶段 1 为 None。
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        stream = await self.client.chat.completions.create(**kwargs)

        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if delta and delta.content:
                yield LLMChunk(type=ChunkType.TEXT, text=delta.content)

            if delta and getattr(delta, "tool_calls", None):
                yield LLMChunk(
                    type=ChunkType.TOOL_CALL,
                    tool_calls=[tc.model_dump() for tc in delta.tool_calls],
                )

            if choice.finish_reason:
                yield LLMChunk(
                    type=ChunkType.FINISH,
                    finish_reason=choice.finish_reason,
                )
