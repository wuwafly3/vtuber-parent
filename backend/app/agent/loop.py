"""Agent loop: LLM function calling 编排。

串行模式: 中间轮次(工具调用)不推 token/audio, 只发 agent_status;
最终轮次(LLM 直接文本回复)由调用方走正常流式推送。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from app.agent.base import ToolResult
from app.agent.registry import ToolRegistry
from app.llm.service import ChunkType, LLMChunk, LLMService
from app.ws.protocol import AgentStatusEvent

logger = logging.getLogger("pet")

MAX_ITERATIONS = 5


@dataclass
class AgentResult:
    """agent loop 执行结果。"""

    text: str  # 最终文本回复
    images: list[str] = field(default_factory=list)  # 工具产生的 base64 data URL


async def send_event(ws: WebSocket, event: Any) -> None:
    await ws.send_text(event.model_dump_json())


async def run_agent_loop(
    llm: LLMService,
    registry: ToolRegistry,
    messages: list[dict[str, Any]],
    ws: WebSocket,
    max_iterations: int = MAX_ITERATIONS,
) -> AgentResult:
    """运行 agent loop。

    返回最终文本回复和工具产生的图片列表。
    中间轮次不推 token 给前端(串行模式), 只发 agent_status 事件。
    """
    tools_schema = registry.get_tools_schema() or None
    all_images: list[str] = []

    for iteration in range(max_iterations):
        # 收集本轮 LLM 流式输出
        text_parts: list[str] = []
        tc_map: dict[int, dict[str, Any]] = {}  # index -> accumulated tool_call

        async for chunk in llm.stream_chat(messages, tools=tools_schema):
            if chunk.type is ChunkType.TEXT:
                text_parts.append(chunk.text)
            elif chunk.type is ChunkType.TOOL_CALL:
                for tc_delta in chunk.tool_calls:
                    idx = tc_delta.get("index", 0)
                    if idx not in tc_map:
                        tc_map[idx] = {
                            "id": tc_delta.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc_delta.get("function", {}).get("name", ""),
                                "arguments": tc_delta.get("function", {}).get("arguments", ""),
                            },
                        }
                    else:
                        tc = tc_map[idx]
                        if tc_delta.get("id"):
                            tc["id"] = tc_delta["id"]
                        if tc_delta.get("function", {}).get("name"):
                            tc["function"]["name"] += tc_delta["function"]["name"]
                        if tc_delta.get("function", {}).get("arguments"):
                            tc["function"]["arguments"] += tc_delta["function"]["arguments"]
            elif chunk.type is ChunkType.FINISH:
                break

        # ── 没有 tool call → 文本回复, 返回给调用方做流式推送 ──
        if not tc_map:
            return AgentResult(text="".join(text_parts), images=all_images)

        # ── 有 tool call: 依次执行 ──
        full_text = "".join(text_parts)

        # 构造 assistant tool_calls message
        assistant_tool_calls = []
        for idx in sorted(tc_map):
            tc = tc_map[idx]
            assistant_tool_calls.append({
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                },
            })

        assistant_content: Any = full_text if full_text else None
        messages.append({
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": assistant_tool_calls,
        })

        # 逐个执行工具
        for tc in assistant_tool_calls:
            tool_name = tc["function"]["name"]
            tool_call_id = tc["id"]

            try:
                args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
            except json.JSONDecodeError:
                args = {}

            # 通知前端: 工具执行中
            await send_event(
                ws, AgentStatusEvent(tool=tool_name, status="running", detail="")
            )

            result = await registry.dispatch(tool_name, args)

            # 通知前端: 工具完成
            await send_event(
                ws,
                AgentStatusEvent(
                    tool=tool_name,
                    status="done",
                    detail=result.text[:100],
                ),
            )

            if result.image:
                all_images.append(result.image)

            # tool result message
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result.text,
            })

            # 如果有图片, 追加一条带图片的 user message 让 LLM "看到"
            if result.image:
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": result.text},
                        {
                            "type": "image_url",
                            "image_url": {"url": result.image},
                        },
                    ],
                })

    # 达到最大迭代, 返回兜底文本
    return AgentResult(text="[emotion:thinking] 我想太久了, 让我换个方式回答你吧~")
