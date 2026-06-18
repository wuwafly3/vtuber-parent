"""进程内会话历史管理。

阶段 5 接记忆时,get_messages 会改为 [system + 召回记忆 + 近期历史],
但对 LLMService 暴露的形态不变(返回一个 messages 列表)。
"""

from __future__ import annotations

from typing import Any

from app.llm.prompts import SYSTEM_PROMPT


class SessionManager:
    def __init__(self, max_turns: int = 20) -> None:
        # session_id -> 不含 system 的消息列表
        self._sessions: dict[str, list[dict[str, Any]]] = {}
        self._max_turns = max_turns
        # session_id -> 已格式化的记忆注入文本（每轮 recall 后更新）
        self._memory_context: dict[str, str] = {}

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        history = self._sessions.get(session_id, [])
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        memory_text = self._memory_context.get(session_id, "")
        if memory_text:
            messages.append({"role": "system", "content": memory_text})
        messages.extend(history)
        return messages

    def set_memory_context(self, session_id: str, text: str) -> None:
        self._memory_context[session_id] = text

    def add_user(self, session_id: str, text: str, image: str | None = None) -> None:
        """添加用户消息。image 为 data URL 时构造多模态内容。"""
        if image:
            content: Any = [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": image}},
            ]
        else:
            content = text
        self._sessions.setdefault(session_id, []).append(
            {"role": "user", "content": content}
        )

    def add_assistant(self, session_id: str, text: str) -> None:
        history = self._sessions.setdefault(session_id, [])
        history.append({"role": "assistant", "content": text})
        # 截断:保留最近 max_turns 轮 (user+assistant 成对)
        if len(history) > self._max_turns * 2:
            self._sessions[session_id] = history[-self._max_turns * 2 :]

    def add_tool_messages(
        self,
        session_id: str,
        assistant_content: Any | None,
        tool_calls: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
    ) -> None:
        """追加 agent loop 的 tool_call + tool_result 消息到历史。

        assistant_content: LLM 在 tool_call 前可能输出的文本。
        tool_calls: assistant message 的 tool_calls 字段。
        tool_results: [{"id", "name", "content"}, ...]
        """
        history = self._sessions.setdefault(session_id, [])
        history.append({
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": tool_calls,
        })
        for tr in tool_results:
            history.append({
                "role": "tool",
                "tool_call_id": tr["id"],
                "content": tr["content"],
            })

    def pop_oldest_messages(self, session_id: str, count: int) -> list[dict[str, Any]]:
        """取走并返回最旧的 count 条消息，供压缩器使用。"""
        history = self._sessions.get(session_id, [])
        if not history or count <= 0:
            return []
        actual = min(count, len(history))
        removed = history[:actual]
        self._sessions[session_id] = history[actual:]
        return removed
