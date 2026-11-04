"""Собственная реализация ReAct-цикла: не больше восьми шагов, повтор того же вызова или последний шаг
заканчиваются ещё одним вызовом модели без инструментов, чтобы она ответила тем, что уже нашла."""
from . import config
from .context import compact
from .llm import JOURNAL, chat

SYSTEM = ("You answer questions about recent events. Never answer from memory: look facts up with the tools, do not repeat the same call. "
          "Answer in the language of the question, write names as in the source. "
          "The last line must be FINAL: <short answer>, or FINAL: NOT_FOUND if the sources have no answer.")
LAST_STEP = ("Tools are no longer available. Answer from what you already found. "
             "The last line must be FINAL: <short answer> in the language of the question, or FINAL: NOT_FOUND.")
MAX_STEPS = 8
MAX_CONTEXT_CHARS = 16000


def run(question, toolbox, model=config.CHEAP, temperature=0.0, max_steps=MAX_STEPS):
    messages, seen = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}], set()
    for step in range(1, max_steps + 1):
        messages, context = compact(messages, MAX_CONTEXT_CHARS)
        if context["before_chars"] != context["after_chars"]:
            JOURNAL.add("context", step=step, **context)
        msg = chat(messages, model, toolbox.schemas, temperature)
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
        messages += [toolbox.run(c) for c in calls]
