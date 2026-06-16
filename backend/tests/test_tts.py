import json
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main_module
from app.llm.service import ChunkType, LLMChunk


async def _fake_stream(*_args, **_kwargs):
    for ch in "你好。再见!":
        yield LLMChunk(type=ChunkType.TEXT, text=ch)
    yield LLMChunk(type=ChunkType.FINISH, finish_reason="stop")


class _FakeTTS:
    audio_format = "mp3"

    async def synthesize(self, text):
        # 每句吐两块假音频
        yield b"\x00\x01"
        yield b"\x02\x03"


def test_ws_tts_audio_flow():
    with (
        patch.object(main_module.llm, "stream_chat", _fake_stream),
        patch.object(main_module, "tts", _FakeTTS()),
    ):
        client = TestClient(main_module.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "user_message", "text": "hi"}))
            audio_chunks = 0
            audio_done = False
            while True:
                data = ws.receive_json()
                if data["type"] == "audio_chunk":
                    audio_chunks += 1
                    assert data["format"] == "mp3"
                    assert isinstance(data["data"], str)  # base64
                elif data["type"] == "audio_done":
                    audio_done = True
                elif data["type"] == "message_done":
                    break
            # 两句 × 每句两块 = 4
            assert audio_chunks == 4
            assert audio_done


def test_ws_tts_disabled_no_audio():
    with (
        patch.object(main_module.llm, "stream_chat", _fake_stream),
        patch.object(main_module, "tts", None),
    ):
        client = TestClient(main_module.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "user_message", "text": "hi"}))
            saw_audio = False
            while True:
                data = ws.receive_json()
                if data["type"] in ("audio_chunk", "audio_done"):
                    saw_audio = True
                elif data["type"] == "message_done":
                    break
            assert not saw_audio
