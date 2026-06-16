"""MemoryExtractor 单元测试（mock LLM）。"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.memory.extraction import MemoryExtractor
from app.memory.models import MemoryExtractionResult


def _make_extractor(json_response: str) -> MemoryExtractor:
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json_response
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    return MemoryExtractor(mock_client, model="test-model")


async def test_extraction_parses_profile_updates():
    payload = {
        "profile_updates": [{"category": "preference", "key": "pet", "value": "cats", "confidence": 0.9}],
        "events": [],
    }
    extractor = _make_extractor(json.dumps(payload))
    result = await extractor.extract("我喜欢猫", "好的，猫真可爱！", [])
    assert len(result.profile_updates) == 1
    assert result.profile_updates[0].key == "pet"
    assert result.profile_updates[0].value == "cats"


async def test_extraction_parses_events():
    payload = {
        "profile_updates": [],
        "events": [{"content": "用户提到养了一只猫", "category": "fact", "importance": 7}],
    }
    extractor = _make_extractor(json.dumps(payload))
    result = await extractor.extract("我养了一只猫叫咪咪", "咪咪真可爱！", [])
    assert len(result.events) == 1
    assert result.events[0].importance == 7


async def test_extraction_empty_when_no_new_info():
    payload = {"profile_updates": [], "events": []}
    extractor = _make_extractor(json.dumps(payload))
    result = await extractor.extract("今天天气怎么样", "今天晴天！", [])
    assert result.profile_updates == []
    assert result.events == []


async def test_extraction_handles_malformed_json():
    extractor = _make_extractor("not-json-at-all")
    # Should not raise, return empty result
    result = await extractor.extract("hi", "hello", [])
    assert isinstance(result, MemoryExtractionResult)
    assert result.profile_updates == []
    assert result.events == []


async def test_extraction_handles_llm_error():
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("API down"))
    extractor = MemoryExtractor(mock_client, model="test-model")
    result = await extractor.extract("hi", "hello", [])
    assert isinstance(result, MemoryExtractionResult)
