"""FastAPI 入口 + WebSocket 路由。

阶段 1:接入真实 LLM 流式对话 + 情绪标签解析 + 句子切分(为阶段 2 TTS 铺路)。
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI

from app.config import settings
from app.llm.service import ChunkType, LLMService
from app.llm.session import SessionManager
from app.llm.streaming import EmotionParser, SentenceSplitter
from app.memory import MemoryManager
from app.tts.dashscope_tts import DashScopeTTS
from app.ws.protocol import (
    AudioChunkEvent,
    AudioDoneEvent,
    ClientEventType,
    ErrorEvent,
    ExpressionEvent,
    MessageDoneEvent,
    PongEvent,
    TokenEvent,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pet")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if memory_manager is not None:
        await memory_manager.initialize()
        logger.info("memory manager initialized")
    yield
    if memory_manager is not None:
        await memory_manager.close()


app = FastAPI(title="Desktop Pet Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 服务单例
llm = LLMService(
    base_url=settings.llm_base_url,
    api_key=settings.llm_api_key,
    model=settings.llm_model,
)
sessions = SessionManager()

tts = (
    DashScopeTTS(
        api_key=settings.dashscope_api_key,
        model=settings.tts_model,
        voice=settings.tts_voice,
    )
    if settings.tts_enabled and settings.dashscope_api_key
    else None
)

# 记忆管理器（未配置 API key 或 disabled 时为 None）
memory_manager: MemoryManager | None = None
if settings.memory_extraction_enabled and settings.llm_api_key:
    _memory_model = settings.memory_llm_model or settings.llm_model
    _memory_client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)
    memory_manager = MemoryManager(
        db_path=settings.memory_db_path,
        llm_client=_memory_client,
        extraction_model=_memory_model,
        compression_model=_memory_model,
        compression_threshold=settings.memory_compression_threshold,
        compression_batch=settings.memory_compression_batch,
        max_events=settings.memory_recall_max_events,
        token_budget=settings.memory_recall_token_budget,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.llm_model}


async def send_event(ws: WebSocket, event) -> None:
    await ws.send_text(event.model_dump_json())


async def _speak(ws: WebSocket, text: str) -> None:
    """合成一句并把音频块流式推给前端。"""
    if tts is None:
        return
    try:
        async for chunk in tts.synthesize(text):
            b64 = base64.b64encode(chunk).decode("ascii")
            await send_event(ws, AudioChunkEvent(data=b64, format=tts.audio_format))
    except Exception as exc:  # noqa: BLE001
        logger.exception("tts error")
        await send_event(ws, ErrorEvent(message=f"TTS 合成失败: {exc}"))


async def _process_memory(session_id: str, user_text: str, assistant_text: str) -> None:
    """后台 fire-and-forget：提取记忆并在必要时压缩历史。"""
    if memory_manager is None:
        return
    await memory_manager.process_turn(
        session_id,
        user_text,
        assistant_text,
        pop_messages_fn=sessions.pop_oldest_messages,
    )


async def handle_user_message(ws: WebSocket, session_id: str, text: str) -> None:
    """调 LLM 流式回复,推 token / expression / 逐句音频,结束推 message_done。

    句子切分出的整句串行送 TTS,保证音频顺序;TTS 在独立队列消费,不阻塞 token 流。
    """
    # 注入记忆上下文（仅 DB 读，亚毫秒）
    if memory_manager is not None:
        memory_text = await memory_manager.get_context_memories(session_id)
        sessions.set_memory_context(session_id, memory_text)

    sessions.add_user(session_id, text)
    messages = sessions.get_messages(session_id)

    emotion_parser = EmotionParser()
    splitter = SentenceSplitter()
    full_reply = ""

    # 串行 TTS 队列:整句入队,后台任务按序合成,保证音频顺序
    tts_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def tts_worker() -> None:
        while True:
            sentence = await tts_queue.get()
            if sentence is None:
                break
            await _speak(ws, sentence)

    tts_task = asyncio.create_task(tts_worker()) if tts else None

    def enqueue(sentence: str) -> None:
        if tts_task:
            tts_queue.put_nowait(sentence)

    try:
        async for chunk in llm.stream_chat(messages):
            if chunk.type is ChunkType.TEXT:
                emotion, clean = emotion_parser.feed(chunk.text)
                if emotion:
                    await send_event(ws, ExpressionEvent(name=emotion))
                if clean:
                    full_reply += clean
                    await send_event(ws, TokenEvent(text=clean))
                    for sentence in splitter.feed(clean):
                        enqueue(sentence)
            elif chunk.type is ChunkType.FINISH:
                break

        # 收尾:emotion_parser 残留 + 最后未切出的尾句
        tail = emotion_parser.flush()
        if tail:
            full_reply += tail
            await send_event(ws, TokenEvent(text=tail))
            for sentence in splitter.feed(tail):
                enqueue(sentence)
        last = splitter.flush()
        if last:
            enqueue(last)
    finally:
        # 等音频队列排空再收尾
        if tts_task:
            tts_queue.put_nowait(None)
            await tts_task
            await send_event(ws, AudioDoneEvent())

    sessions.add_assistant(session_id, full_reply)

    # 后台提取记忆，不阻塞用户响应
    asyncio.create_task(_process_memory(session_id, text, full_reply))

    await send_event(ws, MessageDoneEvent(text=full_reply))


async def handle_client_event(ws: WebSocket, raw: str) -> None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        await send_event(ws, ErrorEvent(message="invalid json"))
        return

    event_type = data.get("type")

    if event_type == ClientEventType.PING.value:
        await send_event(ws, PongEvent())
        return

    if event_type == ClientEventType.USER_MESSAGE.value:
        text = data.get("text", "")
        session_id = data.get("session_id", "default")
        try:
            await handle_user_message(ws, session_id, text)
        except Exception as exc:  # noqa: BLE001 — 把后端异常透传给前端展示
            logger.exception("llm error")
            await send_event(ws, ErrorEvent(message=f"LLM 调用失败: {exc}"))
        return

    await send_event(ws, ErrorEvent(message=f"unknown event type: {event_type}"))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    logger.info("client connected")
    try:
        while True:
            raw = await ws.receive_text()
            await handle_client_event(ws, raw)
    except WebSocketDisconnect:
        logger.info("client disconnected")


def main() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)


if __name__ == "__main__":
    main()
