"""ContextCompressor 单元测试（mock LLM）。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.memory.compression import ContextCompressor


def _make_compressor(response_text: str) -> ContextCompressor:
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = response_text
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    return ContextCompressor(mock_client, model="test-model")


async def test_compress_returns_summary():
    compressor = _make_compressor("用户讨论了编程爱好，提到喜欢 Python。")
    messages = [
        {"role": "user", "content": "我喜欢 Python"},
        {"role": "assistant", "content": "Python 很棒！"},
    ]
    result = await compressor.compress(messages)
    assert result == "用户讨论了编程爱好，提到喜欢 Python。"


async def test_compress_with_prior_summary():
    compressor = _make_compressor("合并摘要：用户喜欢 Python，还提到喜欢猫。")
    messages = [
        {"role": "user", "content": "我还养了一只猫"},
        {"role": "assistant", "content": "猫咪很可爱！"},
    ]
    result = await compressor.compress(messages, previous_summary="用户喜欢 Python。")
    assert "合并摘要" in result


async def test_compress_empty_messages_returns_none():
    compressor = _make_compressor("不应该被调用")
    result = await compressor.compress([])
    assert result is None


async def test_compress_handles_llm_error():
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("API error"))
    compressor = ContextCompressor(mock_client, model="test-model")
    result = await compressor.compress([{"role": "user", "content": "hi"}])
    assert result is None


async def test_compress_handles_empty_response():
    compressor = _make_compressor("")
    result = await compressor.compress([{"role": "user", "content": "hi"}])
    assert result is None
