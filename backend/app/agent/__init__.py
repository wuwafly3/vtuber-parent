"""Agent 模块：工具注册、agent loop、工具基类。"""

from app.agent.registry import ToolRegistry
from app.agent.tools import ALL_TOOLS

# 全局 registry 单例，启动时自动注册所有工具
registry = ToolRegistry()
for _tool in ALL_TOOLS:
    registry.register(_tool)

__all__ = ["registry", "ToolRegistry"]
