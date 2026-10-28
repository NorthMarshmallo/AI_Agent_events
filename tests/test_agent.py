import json
from events_agent import agent


def tool_call(n, query):
    return {"id": f"c{n}", "type": "function", "function": {"name": "echo", "arguments": json.dumps({"text": query})}}


def fake_chat(replies):
    sent = []

    def chat(messages, model, tools=None, temperature=0.0):
        sent.append({"messages": list(messages), "tools": tools})
        return replies.pop(0)
    return chat, sent


def test_answer_without_tools(monkeypatch):
    chat, sent = fake_chat([{"role": "assistant", "content": "FINAL: 43"}])
    monkeypatch.setattr(agent, "chat", chat)
    monkeypatch.setattr(agent, "schemas", lambda names: [])
    answer, messages = agent.run("q", ["echo"])
    assert answer == "FINAL: 43" and len(sent) == 1


def test_repeated_call_ends_with_step_without_tools(monkeypatch):
    same = {"role": "assistant", "content": None, "tool_calls": [tool_call(1, "x")]}
    chat, sent = fake_chat([same, dict(same), {"role": "assistant", "content": "FINAL: NOT_FOUND"}])
    monkeypatch.setattr(agent, "chat", chat)
    monkeypatch.setattr(agent, "schemas", lambda names: [])
    monkeypatch.setattr(agent, "run_tool", lambda c, allowed: {"role": "tool", "tool_call_id": c["id"], "content": "X"})
    answer, messages = agent.run("q", ["echo"])
    assert answer == "FINAL: NOT_FOUND"
    assert sent[-1]["tools"] is None and sent[-1]["messages"][-1]["content"] == agent.LAST_STEP
