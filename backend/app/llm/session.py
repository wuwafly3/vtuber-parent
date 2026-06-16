"""进程内会话历史管理。

阶段 5 接记忆时,get_messages 会改为 [system + 召回记忆 + 近期历史],
但对 LLMService 暴露的形态不变(返回一个 messages 列表)。
"""

from __future__ import annotations

from app.llm.prompts import SYSTEM_PROMPT


class SessionManager:
    def __init__(self, max_turns: int = 20) -> None:
        # session_id -> 不含 system 的消息列表
        self._sessions: dict[str, list[dict[str, str]]] = {}
        self._max_turns = max_turns
        # session_id -> 已格式化的记忆注入文本（每轮 recall 后更新）
        self._memory_context: dict[str, str] = {}

    def get_messages(self, session_id: str) -> list[dict[str, str]]:
        history = self._sessions.get(session_id, [])
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        memory_text = self._memory_context.get(session_id, "")
        if memory_text:
            messages.append({"role": "system", "content": memory_text})
        messages.extend(history)
        return messages

    def set_memory_context(self, session_id: str, text: str) -> None:
        self._memory_context[session_id] = text

    def add_user(self, session_id: str, text: str) -> None:
        self._sessions.setdefault(session_id, []).append(
            {"role": "user", "content": text}
        )

    def add_assistant(self, session_id: str, text: str) -> None:
        history = self._sessions.setdefault(session_id, [])
        history.append({"role": "assistant", "content": text})
        # 截断:保留最近 max_turns 轮 (user+assistant 成对)
        if len(history) > self._max_turns * 2:
            self._sessions[session_id] = history[-self._max_turns * 2 :]

    def pop_oldest_messages(self, session_id: str, count: int) -> list[dict[str, str]]:
        """取走并返回最旧的 count 条消息，供压缩器使用。"""
        history = self._sessions.get(session_id, [])
        if not history or count <= 0:
            return []
        actual = min(count, len(history))
        removed = history[:actual]
        self._sessions[session_id] = history[actual:]
        return removed
