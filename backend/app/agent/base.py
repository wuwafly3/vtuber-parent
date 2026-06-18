"""Agent 工具抽象基类与执行结果。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """工具执行结果。

    text: 作为 tool role message 回传给 LLM 的文本。
    image: 可选的 base64 data URL，会额外追加一条带图片的 user message。
    """

    text: str
    image: str | None = None


class BaseTool(ABC):
    """所有 agent 工具的基类。"""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema (OpenAI function calling 格式)

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具并返回结果。"""
        ...

    def to_openai_schema(self) -> dict[str, Any]:
        """生成 OpenAI tools 参数中的单条 function 定义。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
