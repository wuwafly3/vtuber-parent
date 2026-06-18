"""截屏工具：截取主显示器全屏并返回 base64 图片。"""

from __future__ import annotations

import base64
from typing import Any

from app.agent.base import BaseTool, ToolResult


class ScreenshotTool(BaseTool):
    name = "take_screenshot"
    description = "截取用户当前主显示器的全屏截图。当你需要了解用户屏幕上的内容时使用此工具。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import mss
        import mss.tools

        with mss.mss() as sct:
            # monitors[0] 是虚拟合并屏, [1] 是主显示器
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            sct_img = sct.grab(monitor)

            # mss 内置 PNG 编码，无需 PIL
            png_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
            b64 = base64.b64encode(png_bytes).decode("ascii")
            data_url = f"data:image/png;base64,{b64}"

        return ToolResult(
            text="已截取当前主显示器屏幕。请根据截图描述你看到的内容。",
            image=data_url,
        )
