"""SessionManager 记忆注入 + pop_oldest_messages 单元测试。"""

import pytest

from app.llm.session import SessionManager


def test_get_messages_no_memory():
    sm = SessionManager()
    sm.add_user("s1", "hi")
    msgs = sm.get_messages("s1")
    assert msgs[0]["role"] == "system"
    assert msgs[1]["content"] == "hi"
    assert len(msgs) == 2


def test_get_messages_with_memory_context():
    sm = SessionManager()
    sm.set_memory_context("s1", "[记忆模块]\n## 用户画像\n- 喜欢猫")
    sm.add_user("s1", "你好")
    msgs = sm.get_messages("s1")
    # [system_prompt, memory_system, user_message]
    assert len(msgs) == 3
    assert msgs[1]["role"] == "system"
    assert "记忆模块" in msgs[1]["content"]
    assert msgs[2]["content"] == "你好"


def test_set_memory_context_updates():
    sm = SessionManager()
    sm.set_memory_context("s1", "old")
    sm.set_memory_context("s1", "new")
    sm.add_user("s1", "hi")
    msgs = sm.get_messages("s1")
    memory_msg = next(m for m in msgs if m.get("content") in ("old", "new"))
    assert memory_msg["content"] == "new"


def test_pop_oldest_messages_basic():
    sm = SessionManager()
    sm.add_user("s1", "msg1")
    sm.add_assistant("s1", "reply1")
    sm.add_user("s1", "msg2")
    sm.add_assistant("s1", "reply2")

    popped = sm.pop_oldest_messages("s1", 2)
    assert len(popped) == 2
    assert popped[0]["content"] == "msg1"
    assert popped[1]["content"] == "reply1"

    # 剩余消息只有 msg2 + reply2
    remaining = sm.get_messages("s1")
    contents = [m["content"] for m in remaining if m["role"] != "system"]
    assert contents == ["msg2", "reply2"]


def test_pop_oldest_messages_empty_session():
    sm = SessionManager()
    popped = sm.pop_oldest_messages("nonexistent", 4)
    assert popped == []


def test_pop_oldest_messages_count_exceeds_history():
    sm = SessionManager()
    sm.add_user("s1", "only_msg")
    popped = sm.pop_oldest_messages("s1", 100)
    assert len(popped) == 1
    assert popped[0]["content"] == "only_msg"


def test_pop_zero_returns_empty():
    sm = SessionManager()
    sm.add_user("s1", "msg")
    popped = sm.pop_oldest_messages("s1", 0)
    assert popped == []


def test_memory_context_isolated_per_session():
    sm = SessionManager()
    sm.set_memory_context("s1", "memory for s1")
    sm.set_memory_context("s2", "memory for s2")
    sm.add_user("s1", "hi")
    sm.add_user("s2", "hello")
    msgs_s1 = sm.get_messages("s1")
    msgs_s2 = sm.get_messages("s2")
    assert any("s1" in m["content"] for m in msgs_s1 if m["role"] == "system")
    assert any("s2" in m["content"] for m in msgs_s2 if m["role"] == "system")
