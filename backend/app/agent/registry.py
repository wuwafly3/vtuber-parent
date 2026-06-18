"""工具注册中心：管理所有 agent 工具并提供统一调度。"""

from __future__ import annotations

import logging
from typing import Any, Awaitable

from app.agent.base import BaseTool, ToolResult

logger = logging.getLogger("pet")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册一个工具。同名会覆盖并警告。"""
        if tool.name in self._tools:
            logger.warning("tool %s already registered, overwriting", tool.name)
        self._tools[tool.name] = tool
        logger.info("registered tool: %s", tool.name)

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """生成 OpenAI chat completion 的 tools 参数。"""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """按名称调度执行工具。"""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(text=f"未知工具: {name}")
        try:
            return await tool.execute(**arguments)
        except Exception as exc:
            logger.exception("tool %s execution failed", name)
            return ToolResult(text=f"工具 {name} 执行失败: {exc}")

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
