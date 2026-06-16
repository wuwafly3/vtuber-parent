"""前后端 WebSocket 事件协议。

所有消息都是带 `type` 字段的 JSON。前端按 type 分发到聊天框 / 音频播放器 /
角色驱动 / agent 状态面板。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── 客户端 → 服务端 ──────────────────────────────────────────────
class ClientEventType(str, Enum):
    USER_MESSAGE = "user_message"        # 用户发了一条聊天消息
    CONFIRM_ACTION = "confirm_action"    # 用户确认/拒绝一个 computer use 操作
    PING = "ping"


class UserMessage(BaseModel):
    type: Literal[ClientEventType.USER_MESSAGE] = ClientEventType.USER_MESSAGE
    text: str
    session_id: str = "default"


class ConfirmAction(BaseModel):
    type: Literal[ClientEventType.CONFIRM_ACTION] = ClientEventType.CONFIRM_ACTION
    action_id: str
    approved: bool


# ── 服务端 → 客户端 ──────────────────────────────────────────────
class ServerEventType(str, Enum):
    TOKEN = "token"                  # LLM 流式 token
    MESSAGE_DONE = "message_done"    # 一条回复结束
    AUDIO_CHUNK = "audio_chunk"      # TTS 音频块 (base64)
    AUDIO_DONE = "audio_done"        # 音频流结束
    EXPRESSION = "expression"        # 角色表情/情绪指令
    MOTION = "motion"                # 角色动作指令
    AGENT_STATUS = "agent_status"    # agent 工具调用状态
    ACTION_REQUEST = "action_request"  # 请求用户确认一个操作
    ERROR = "error"
    PONG = "pong"


class TokenEvent(BaseModel):
    type: Literal[ServerEventType.TOKEN] = ServerEventType.TOKEN
    text: str


class MessageDoneEvent(BaseModel):
    type: Literal[ServerEventType.MESSAGE_DONE] = ServerEventType.MESSAGE_DONE
    text: str


class AudioChunkEvent(BaseModel):
    type: Literal[ServerEventType.AUDIO_CHUNK] = ServerEventType.AUDIO_CHUNK
    data: str          # base64 编码的音频字节
    format: str = "mp3"


class AudioDoneEvent(BaseModel):
    type: Literal[ServerEventType.AUDIO_DONE] = ServerEventType.AUDIO_DONE


class ExpressionEvent(BaseModel):
    type: Literal[ServerEventType.EXPRESSION] = ServerEventType.EXPRESSION
    name: str          # 如 "happy" / "sad" / "neutral"


class MotionEvent(BaseModel):
    type: Literal[ServerEventType.MOTION] = ServerEventType.MOTION
    name: str


class AgentStatusEvent(BaseModel):
    type: Literal[ServerEventType.AGENT_STATUS] = ServerEventType.AGENT_STATUS
    tool: str
    status: str        # "running" / "done" / "error"
    detail: str = ""


class ActionRequestEvent(BaseModel):
    type: Literal[ServerEventType.ACTION_REQUEST] = ServerEventType.ACTION_REQUEST
    action_id: str
    description: str   # 人类可读的待确认操作描述
    payload: dict[str, Any] = Field(default_factory=dict)


class ErrorEvent(BaseModel):
    type: Literal[ServerEventType.ERROR] = ServerEventType.ERROR
    message: str


class PongEvent(BaseModel):
    type: Literal[ServerEventType.PONG] = ServerEventType.PONG
