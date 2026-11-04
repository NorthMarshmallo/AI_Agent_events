import pytest

from events_agent import context, hooks
from events_agent.llm import cache_marks


def test_before_hook_rejects_empty_and_normalizes_query():
    with pytest.raises(ValueError, match="пустым"):
        hooks.before_tool("web_search", {"query": "  "})
    assert hooks.before_tool("web_search", {"query": "  event  "}) == {"query": "event"}


def test_before_hook_validates_page_find():
    args = {"title": " Article ", "keywords": [" date "], "site": "en_wiki"}
    assert hooks.before_tool("page_find", args) == {"title": "Article", "keywords": ["date"], "site": "en_wiki"}
    with pytest.raises(ValueError, match="сайт"):
        hooks.before_tool("page_find", {"title": "x", "keywords": ["y"], "site": "other"})


def test_after_hook_removes_nul_and_limits_result():
    assert hooks.after_tool("web_search", "a\x00bcd", 3) == "abc"


def test_context_compacts_old_tool_rounds():
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
    for i in range(4):
        messages.extend([
            {"role": "assistant", "content": None, "tool_calls": [{"id": str(i)}]},
            {"role": "tool", "tool_call_id": str(i), "content": "x" * 5000},
        ])
    compacted, info = context.compact(messages, max_chars=1000)
    assert info["dropped_rounds"] == 2
    assert context.message_chars(compacted) < context.message_chars(messages)
    assert compacted[-1]["role"] == "tool"


def test_cache_marks_only_copy_for_anthropic_payload():
    messages = [{"role": "system", "content": "stable"}, {"role": "user", "content": "question"}]
    marked = cache_marks(messages)
    assert isinstance(marked[0]["content"], list)
    assert marked[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert messages[0]["content"] == "stable"

