import json
from pydantic import BaseModel
from events_agent.llm import JOURNAL
from events_agent.tools import register, run_tool


class EchoArgs(BaseModel):
    text: str


def echo(text: str) -> str:
    return text.upper()


register(echo, EchoArgs, "echo")


def call(name, args):
    return {"id": "c1", "function": {"name": name, "arguments": json.dumps(args)}}


def test_runs_allowed_tool_and_logs_it():
    out = run_tool(call("echo", {"text": "hi"}), ["echo"])
    assert out == {"role": "tool", "tool_call_id": "c1", "content": "HI"}
    assert JOURNAL.calls[-1]["tool"] == "echo" and JOURNAL.calls[-1]["ok"]


def test_rejects_tool_not_in_allowlist():
    assert "не разрешён" in run_tool(call("echo", {"text": "hi"}), ["web_search"])["content"]


def test_rejects_bad_arguments():
    out = run_tool(call("echo", {"words": "hi"}), ["echo"])
    assert out["content"].startswith("НЕ удалось вызвать инструмент echo")
    assert not JOURNAL.calls[-1]["ok"]
