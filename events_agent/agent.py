"""Цикл агента из этапа 3 (голый ReAct): не больше восьми шагов, повтор того же вызова или последний шаг
заканчиваются ещё одним вызовом модели без инструментов, чтобы она ответила тем, что уже нашла."""
from . import config
from .llm import chat
from .tools import run_tool, schemas

SYSTEM = ("You answer questions about recent events. Never answer from memory: look facts up with the tools, do not repeat the same call. "
          "Answer in the language of the question, write names as in the source. "
          "The last line must be FINAL: <short answer>, or FINAL: NOT_FOUND if the sources have no answer.")
LAST_STEP = ("Tools are no longer available. Answer from what you already found. "
             "The last line must be FINAL: <short answer> in the language of the question, or FINAL: NOT_FOUND.")
MAX_STEPS = 8


def run(question, tools, model=config.CHEAP, temperature=0.0, max_steps=MAX_STEPS):
    messages, seen = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}], set()
    offered = schemas(tools)
    for step in range(1, max_steps + 1):
        msg = chat(messages, model, offered, temperature)
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content") or "", messages
        keys = [(c["function"]["name"], c["function"]["arguments"]) for c in calls]
        if any(k in seen for k in keys) or step == max_steps:      # повтор или лимит шагов: последний шаг без инструментов
            messages[-1] = {"role": "user", "content": LAST_STEP}
            msg = chat(messages, model, None, temperature)
            messages.append(msg)
            return msg.get("content") or "", messages
        seen.update(keys)
        messages += [run_tool(c, tools) for c in calls]
