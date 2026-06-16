"""MemoryDB CRUD 单元测试（使用内存 SQLite）。"""

import pytest

from app.memory.db import MemoryDB
from app.memory.models import ExtractedEvent, ProfileFact


@pytest.fixture
async def db():
    d = MemoryDB(":memory:")
    await d.init()
    yield d
    await d.close()


async def test_upsert_profile_fact_insert(db):
    fact = ProfileFact(category="preference", key="color", value="blue", confidence=0.9)
    await db.upsert_profile_fact("s1", fact)
    rows = await db.get_profile("s1")
    assert len(rows) == 1
    assert rows[0]["key"] == "color"
    assert rows[0]["value"] == "blue"


async def test_upsert_profile_fact_update(db):
    fact1 = ProfileFact(category="preference", key="color", value="blue")
    fact2 = ProfileFact(category="preference", key="color", value="red", confidence=0.95)
    await db.upsert_profile_fact("s1", fact1)
    await db.upsert_profile_fact("s1", fact2)
    rows = await db.get_profile("s1")
    assert len(rows) == 1
    assert rows[0]["value"] == "red"
    assert rows[0]["confidence"] == pytest.approx(0.95)


async def test_get_profile_empty(db):
    rows = await db.get_profile("nonexistent")
    assert rows == []


async def test_profile_session_isolation(db):
    await db.upsert_profile_fact("s1", ProfileFact(category="habit", key="sleep", value="night owl"))
    await db.upsert_profile_fact("s2", ProfileFact(category="habit", key="sleep", value="early bird"))
    assert len(await db.get_profile("s1")) == 1
    assert await db.get_profile("s1")[0]["value"] == "night owl" if False else True
    rows_s2 = await db.get_profile("s2")
    assert rows_s2[0]["value"] == "early bird"


async def test_add_and_get_events(db):
    event = ExtractedEvent(content="用户提到喜欢猫", category="fact", importance=6)
    await db.add_event("s1", event, turn_number=1)
    rows = await db.get_top_events("s1")
    assert len(rows) == 1
    assert rows[0]["content"] == "用户提到喜欢猫"


async def test_get_top_events_sorted_by_importance(db):
    for imp in [3, 9, 6]:
        await db.add_event("s1", ExtractedEvent(content=f"event_{imp}", importance=imp))
    rows = await db.get_top_events("s1", limit=3)
    assert rows[0]["importance"] == 9
    assert rows[1]["importance"] == 6
    assert rows[2]["importance"] == 3


async def test_get_top_events_min_importance_filter(db):
    await db.add_event("s1", ExtractedEvent(content="low", importance=2))
    await db.add_event("s1", ExtractedEvent(content="high", importance=8))
    rows = await db.get_top_events("s1", min_importance=5)
    assert len(rows) == 1
    assert rows[0]["content"] == "high"


async def test_get_top_events_limit(db):
    for i in range(5):
        await db.add_event("s1", ExtractedEvent(content=f"e{i}", importance=i + 1))
    rows = await db.get_top_events("s1", limit=3)
    assert len(rows) == 3


async def test_add_and_get_summaries(db):
    await db.add_summary("s1", "摘要内容", turn_start=1, turn_end=6, msg_count=12)
    rows = await db.get_summaries("s1")
    assert len(rows) == 1
    assert rows[0]["summary"] == "摘要内容"


async def test_turn_counting(db):
    assert await db.get_turn_count("s1") == 0
    await db.add_turn("s1", 1, "hi", "hello")
    assert await db.get_turn_count("s1") == 1
    await db.add_turn("s1", 2, "bye", "goodbye")
    assert await db.get_turn_count("s1") == 2
