"""记忆系统的 prompt 模板。"""

from __future__ import annotations

import json
from typing import Any

# --------------------------------------------------------------------------
# 提取 prompt（用户画像 + 重要事件，单次 JSON mode 调用）
# --------------------------------------------------------------------------

EXTRACTION_SYSTEM = """你是一个记忆管理助手。分析对话内容，提取用户画像更新和重要事件。

输出严格的 JSON，格式如下（不得输出其他任何内容）：
{
  "profile_updates": [
    {"category": "preference|personality|personal_info|habit|interest", "key": "...", "value": "...", "confidence": 0.0-1.0}
  ],
  "events": [
    {"content": "事件描述", "category": "milestone|emotion|decision|plan|fact|general", "importance": 1-10}
  ]
}

规则：
- 没有新信息时返回空数组，不要捏造
- 只记录真正重要的事件，日常寒暄不记
- 用户纠正旧信息时，输出相同 category+key 以覆盖旧值
- confidence 反映信息的可靠程度（0.5=推测，0.9=用户明确说明）
- importance: 1-3=低, 4-6=中, 7-9=高, 10=关键"""


def extraction_user_prompt(
    existing_profile: list[dict[str, Any]],
    user_text: str,
    assistant_text: str,
) -> str:
    profile_str = json.dumps(existing_profile, ensure_ascii=False, indent=2) if existing_profile else "（暂无）"
    return f"""## 当前用户画像
{profile_str}

## 本轮对话
用户: {user_text}
助手: {assistant_text}

请提取用户画像更新和重要事件，以 JSON 格式输出。"""


# --------------------------------------------------------------------------
# 压缩 prompt（旧对话 → 摘要）
# --------------------------------------------------------------------------

COMPRESSION_SYSTEM = "你是一个对话摘要助手。将提供的对话历史压缩为简洁摘要，保留关键信息。只输出摘要文本，不加任何前缀。"


def compression_user_prompt(
    messages: list[dict[str, str]],
    previous_summary: str | None = None,
) -> str:
    parts: list[str] = []
    if previous_summary:
        parts.append(f"## 已有摘要（需合并）\n{previous_summary}\n")

    parts.append("## 需要压缩的对话")
    for msg in messages:
        role = "用户" if msg["role"] == "user" else "助手"
        parts.append(f"{role}: {msg['content']}")

    parts.append(
        "\n请输出一段连贯摘要（≤300字），重点保留：讨论的话题、做出的决定、用户表达的感受或需求、待办事项。"
    )
    return "\n".join(parts)


# --------------------------------------------------------------------------
# 召回格式化（注入 LLM context 的文本块）
# --------------------------------------------------------------------------

def format_recalled_memory(
    profile: list[dict[str, Any]],
    events: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> str:
    parts: list[str] = ["[记忆模块]"]

    if profile:
        lines = [f"- [{r['category']}] {r['key']}: {r['value']}" for r in profile]
        parts.append("## 用户画像\n" + "\n".join(lines))

    if events:
        lines = [f"- (重要度{r['importance']}) {r['content']}" for r in events]
        parts.append("## 重要事件\n" + "\n".join(lines))

    if summaries:
        lines = [r["summary"] for r in summaries]
        parts.append("## 历史对话摘要\n" + "\n\n".join(lines))

    return "\n\n".join(parts)
