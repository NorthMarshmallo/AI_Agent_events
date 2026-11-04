"""Вызов модели через OpenRouter и журнал: каждый вызов модели и инструмента пишется строкой в logs/calls-<запуск>.jsonl."""
import contextvars, json, os, threading, time
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

    @staticmethod
    def _limit(name, default):
        try:
            return float(os.getenv(name, default))
        except ValueError:
            return float(default)

    def spent_for_task(self, qid):
        return sum(float(c.get("cost") or 0) * 100 for c in self.calls
                   if c.get("kind") in {"model", "embed"} and c.get("qid") == qid)

    def spent_today(self):
        """Вернуть накопленную стоимость вызовов за текущую календарную дату."""
        today = datetime.now().strftime("%Y%m%d")
        total = 0.0
        for path in config.LOGS.glob(f"calls-{today}-*.jsonl"):
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    row = json.loads(line)
                    if row.get("kind") in {"model", "embed"}:
                        total += float(row.get("cost") or 0)
            except (OSError, json.JSONDecodeError):
                continue
        return total * 100

    def check_budget(self):
        """Остановить следующий сетевой вызов после превышения лимита.

        Стоимость становится известна только в ответе провайдера, поэтому
        проверка выполняется перед каждым следующим вызовом. Она не позволяет
        продолжать задание или день после достигнутого потолка.
        """
        qid = QID.get()
        task = self.spent_for_task(qid) if qid is not None else sum(
            float(c.get("cost") or 0) * 100 for c in self.calls if c.get("kind") in {"model", "embed"}
        )
        task_limit = self._limit("MAX_TASK_CENTS", 5.0)
        day_limit = self._limit("MAX_DAILY_CENTS", 500.0)
        day = self.spent_today()
        if task >= task_limit:
            raise RuntimeError(f"потолок задачи достигнут: {task:.4f} из {task_limit:.4f} цента")
        if day >= day_limit:
            raise RuntimeError(f"дневной потолок достигнут: {day:.4f} из {day_limit:.4f} цента")

    def of(self, qid, kind="model", tag=None):
        return [c for c in self.calls if c["kind"] == kind and c["qid"] == qid and (tag is None or c["tag"] == tag)]


JOURNAL = Journal()
_HTTP = None


def cache_marks(messages):
    """Пометить стабильное начало и конец префикса для Claude через OpenRouter."""
    out = [dict(message) for message in messages]
    for index in {0, len(out) - 1}:
        content = out[index].get("content")
        if isinstance(content, str) and content:
            out[index]["content"] = [{"type": "text", "text": content,
                                       "cache_control": {"type": "ephemeral"}}]
    return out


def _tool_tax(tools):
    return len(json.dumps(tools or [], ensure_ascii=False)) // 4


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
    JOURNAL.check_budget()
    body = {"model": model,
            "messages": cache_marks(messages) if model.startswith("anthropic/") else messages,
            "temperature": temperature, "usage": {"include": True}}
    if tools:
        body["tools"] = tools
    started = time.perf_counter()
    data = post("/chat/completions", body)
    msg = data["choices"][0]["message"]
    record("model", model, data.get("usage") or {}, time.perf_counter() - started,
           tools_offered=len(tools or []), tool_tax_tokens=_tool_tax(tools),
           tool_calls=[c["function"]["name"] for c in msg.get("tool_calls") or []])
    return msg


def embed(texts, model=config.EMBED_MODEL, dim=config.DIM):
    JOURNAL.check_budget()
    started = time.perf_counter()
    data = post("/embeddings", {"model": model, "input": texts, "dimensions": dim})
    record("embed", model, data.get("usage") or {}, time.perf_counter() - started, texts=len(texts))
    return [row["embedding"] for row in data["data"]]
