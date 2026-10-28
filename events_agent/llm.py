"""Вызов модели через OpenRouter и журнал: каждый вызов модели и инструмента пишется строкой в logs/calls-<запуск>.jsonl."""
import contextvars, json, threading, time
from datetime import datetime
import httpx
from . import config

QID = contextvars.ContextVar("QID", default=None)   # номер задачи: потоки прогона получают его через copy_context
TAG = contextvars.ContextVar("TAG", default="без метки")


class Journal:
    def __init__(self):
        self.calls, self.lock, self.path = [], threading.Lock(), None

    def start(self, name="run"):
        config.LOGS.mkdir(exist_ok=True)
        self.path = config.LOGS / f"calls-{datetime.now():%Y%m%d-%H%M%S}-{name}.jsonl"
        return self.path

    def add(self, kind, **row):
        row = {"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, "tag": TAG.get(), "qid": QID.get(), **row}
        with self.lock:
            self.calls.append(row)
            if self.path:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def of(self, qid, kind="model", tag=None):
        return [c for c in self.calls if c["kind"] == kind and c["qid"] == qid and (tag is None or c["tag"] == tag)]


JOURNAL = Journal()
_HTTP = None


def http():
    global _HTTP
    if _HTTP is None:
        _HTTP = httpx.Client(timeout=180, headers={"Authorization": f"Bearer {config.api_key()}", "X-Title": "ai-agent-events"})
    return _HTTP


def post(path, body, attempts=5):
    problem = "нет ответа"
    for attempt in range(attempts):
        try:
            r = http().post(f"{config.BASE_URL}{path}", json=body)
            if r.status_code == 200:
                return r.json()
            problem = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        except httpx.HTTPError as e:
            problem = type(e).__name__
        time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(problem)


def record(kind, model, usage, seconds, **extra):
    details = usage.get("prompt_tokens_details") or {}
    return JOURNAL.add(kind, model=model.split("/")[-1], prompt=usage.get("prompt_tokens", 0),
                       completion=usage.get("completion_tokens", 0), cached=details.get("cached_tokens") or 0,
                       cost=usage.get("cost") or 0.0, seconds=round(seconds, 2), **extra)


def chat(messages, model=config.CHEAP, tools=None, temperature=0.0):
    body = {"model": model, "messages": messages, "temperature": temperature, "usage": {"include": True}}
    if tools:
        body["tools"] = tools
    started = time.perf_counter()
    data = post("/chat/completions", body)
    msg = data["choices"][0]["message"]
    record("model", model, data.get("usage") or {}, time.perf_counter() - started,
           tools_offered=len(tools or []), tool_calls=[c["function"]["name"] for c in msg.get("tool_calls") or []])
    return msg


def embed(texts, model=config.EMBED_MODEL, dim=config.DIM):
    started = time.perf_counter()
    data = post("/embeddings", {"model": model, "input": texts, "dimensions": dim})
    record("embed", model, data.get("usage") or {}, time.perf_counter() - started, texts=len(texts))
    return [row["embedding"] for row in data["data"]]
