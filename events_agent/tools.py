"""Реестр инструментов: схема параметров из Pydantic-модели, ею же проверяются аргументы, которые прислала модель."""
import time
from .llm import JOURNAL

TOOLS = {}


def register(fn, args_model, description, name=None):
    name = name or fn.__name__
    TOOLS[name] = {"fn": fn, "args": args_model, "description": description, "schema": {"type": "function", "function": {
        "name": name, "description": description, "parameters": args_model.model_json_schema()}}}


def schemas(names):
    return [TOOLS[n]["schema"] for n in names]


def run_tool(call, allowed, limit=3000):
    name, started = call["function"]["name"], time.perf_counter()
    try:
        if name not in allowed:                      # модель может назвать инструмент, которого ей не давали
            raise KeyError("инструмент не разрешён")
        spec = TOOLS[name]
        args = spec["args"].model_validate_json(call["function"]["arguments"])
        result, ok = spec["fn"](**args.model_dump()), True
    except Exception as e:
        result, ok = f"НЕ удалось вызвать инструмент {name}: {e}", False
    content = str(result)[:limit]
    JOURNAL.add("tool", tool=name, arguments=call["function"]["arguments"], ok=ok, chars=len(content),
                seconds=round(time.perf_counter() - started, 2))
    return {"role": "tool", "tool_call_id": call["id"], "content": content}
