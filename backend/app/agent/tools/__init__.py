"""Agent 工具注册。导入即注册。"""

from app.agent.tools.screenshot import ScreenshotTool

# 新增工具只需在此处 import 并实例化
ALL_TOOLS = [
    ScreenshotTool(),
]
