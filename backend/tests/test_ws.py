import json
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main_module
from app.llm.service import ChunkType, LLMChunk
from app.main import app


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ws_ping_pong():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "ping"}))
        assert ws.receive_json()["type"] == "pong"


async def _fake_stream(*_args, **_kwargs):
    # 模拟带情绪标签的逐字流
    for ch in "[emotion:happy] 你好呀!":
        yield LLMChunk(type=ChunkType.TEXT, text=ch)
    yield LLMChunk(type=ChunkType.FINISH, finish_reason="stop")


def test_ws_user_message_llm_flow():
    with patch.object(main_module.llm, "stream_chat", _fake_stream):
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "user_message", "text": "hi"}))
            tokens = []
            expression = None
            while True:
                data = ws.receive_json()
                if data["type"] == "expression":
                    expression = data["name"]
                elif data["type"] == "token":
                    tokens.append(data["text"])
                elif data["type"] == "message_done":
                    assert data["text"] == "你好呀!"
                    break
            assert expression == "happy"
            assert "".join(tokens) == "你好呀!"


def test_ws_unknown_event():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "nonsense"}))
        assert ws.receive_json()["type"] == "error"
