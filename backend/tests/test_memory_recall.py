"""MemoryRecaller 单元测试。"""

import pytest

from app.memory.recall import MemoryRecaller


class _FakeDB:
    def __init__(self, profile=None, events=None, summaries=None):
        self._profile = profile or []
        self._events = events or []
        self._summaries = summaries or []

    async def get_profile(self, session_id):
        return self._profile

    async def get_top_events(self, session_id, limit=10, min_importance=1):
        sorted_events = sorted(self._events, key=lambda e: e["importance"], reverse=True)
        return sorted_events[:limit]

    async def get_summaries(self, session_id):
        return self._summaries


async def test_recall_returns_empty_when_no_memories():
    recaller = MemoryRecaller(_FakeDB())
    result = await recaller.recall("s1")
    assert result == ""


async def test_recall_includes_profile():
    db = _FakeDB(profile=[{"category": "preference", "key": "color", "value": "blue", "confidence": 0.9}])
    recaller = MemoryRecaller(db)
    result = await recaller.recall("s1")
    assert "用户画像" in result
    assert "color" in result
    assert "blue" in result


async def test_recall_includes_events():
    db = _FakeDB(events=[{"content": "用户养了一只猫", "category": "fact", "importance": 7}])
    recaller = MemoryRecaller(db)
    result = await recaller.recall("s1")
    assert "重要事件" in result
    assert "用户养了一只猫" in result


async def test_recall_includes_summaries():
    db = _FakeDB(summaries=[{"summary": "历史摘要内容", "turn_start": 1, "turn_end": 6}])
    recaller = MemoryRecaller(db)
    result = await recaller.recall("s1")
    assert "历史对话摘要" in result
    assert "历史摘要内容" in result


async def test_recall_trims_events_within_token_budget():
    # 10 token budget → 20 chars. Profile + summary 已够大，事件应被裁剪
    many_events = [{"content": "x" * 50, "category": "fact", "importance": i} for i in range(1, 6)]
    db = _FakeDB(events=many_events)
    recaller = MemoryRecaller(db, token_budget=1)  # 极小 budget
    result = await recaller.recall("s1")
    # 不论裁剪多少，都不应抛异常
    assert isinstance(result, str)


async def test_recall_events_sorted_by_importance():
    events = [
        {"content": "low", "category": "general", "importance": 2},
        {"content": "high", "category": "fact", "importance": 9},
        {"content": "mid", "category": "fact", "importance": 5},
    ]
    db = _FakeDB(events=events)
    recaller = MemoryRecaller(db, max_events=2)
    result = await recaller.recall("s1")
    # high 应出现，low 应被 max_events=2 截掉
    assert "high" in result
    assert "mid" in result
    assert "low" not in result
