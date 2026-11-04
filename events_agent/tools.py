"""Клиент MCP: подключение к серверу слоя, белые списки инструментов по ролям и закреплённые описания.

Клиент MCP асинхронный, агент синхронный, поэтому соединение живёт в отдельном потоке со своим циклом событий. Описания инструментов закреплены отпечатками в mcp_pins.json: если сервер поменял
описание или схему, агент не запустится, пока человек не прочитает новое описание и не закрепит его заново.
"""
import asyncio, concurrent.futures, hashlib, json, os, threading, time
from mcp import Client
from . import config
from . import hooks
from .llm import JOURNAL

PINS = config.ROOT / "mcp_pins.json"
WEB_TOOLS = ["web_search", "ru_wiki_search", "gen_search", "espn_search", "page_find"]
ROLES = {"агент": ["knowledge_base", *WEB_TOOLS],               # основной агент: база и живой поиск
         "агент без базы": WEB_TOOLS}                           # альтернатива для таблицы: только живой поиск


class MCP:
    def __init__(self, server, timeout=120):
        self.timeout = timeout
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.ready = concurrent.futures.Future()
        self.held = asyncio.run_coroutine_threadsafe(self._hold(server), self.loop)
        self.client = self.ready.result(timeout)
        self.tools = self._run(self.client.list_tools()).tools

    async def _hold(self, server):
        self.stop = asyncio.Event()
        try:
            target = server() if callable(server) else server
            mode = "auto" if isinstance(target, str) else "legacy"
            async with Client(target, mode=mode) as client:
                self.ready.set_result(client)
                await self.stop.wait()
        except BaseException as e:
            if not self.ready.done():
                self.ready.set_exception(e)
            raise

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(self.timeout)

    def call(self, name, args=None):
        result = self._run(self.client.call_tool(name, args or {}))
        text = "\n".join(getattr(c, "text", None) or "" for c in result.content)
        return text, not result.is_error

    def close(self):
        self.loop.call_soon_threadsafe(self.stop.set)
        try:
            self.held.result(30)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)


def connect(url=None):
    """Подключиться к удалённому MCP-серверу по Streamable HTTP."""
    url = url or os.getenv("MCP_URL", "http://127.0.0.1:8090/mcp")
    return MCP(url)


def as_openai_tools(tools, allow=None):
    return [{"type": "function", "function": {"name": t.name, "description": t.description or "", "parameters": t.input_schema}}
            for t in tools if allow is None or t.name in allow]


def fingerprint(tools):
    return {t.name: hashlib.sha256(json.dumps([t.description, t.input_schema], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
            for t in tools}


def check_pins(tools, label, path=PINS):
    pins = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    now = fingerprint(tools)
    if label not in pins:
        pins[label] = now
        path.write_text(json.dumps(pins, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return f"{label}: закрепили {len(now)} описаний"
    changed = sorted(n for n in set(now) | set(pins[label]) if now.get(n) != pins[label].get(n))
    if changed:
        raise RuntimeError(f"{label}: изменились описания {changed}. Прочитайте их и закрепите заново, удалив запись из {path.name}")
    return f"{label}: описания совпадают"


class Toolbox:
    """Инструменты одной роли: модель видит только их схемы, и вызвать может только их."""

    def __init__(self, mcp, role, limit=3000):
        check_pins(mcp.tools, "fresh-knowledge")
        self.mcp, self.allowed, self.limit = mcp, ROLES[role], limit
        self.schemas = as_openai_tools(mcp.tools, self.allowed)
        self.before_hook, self.after_hook = hooks.before_tool, hooks.after_tool
        self.tax_tokens = max(1, len(json.dumps(self.schemas, ensure_ascii=False)) // 4)

    def run(self, call):
        name, started = call["function"]["name"], time.perf_counter()
        try:
            if name not in self.allowed:                        # модель может назвать инструмент, которого ей не давали
                raise KeyError("инструмент не разрешён")
            args = json.loads(call["function"]["arguments"] or "{}")
            before = getattr(self, "before_hook", hooks.before_tool)
            after = getattr(self, "after_hook", hooks.after_tool)
            args = before(name, args)
            result, ok = self.mcp.call(name, args)
            result = after(name, result, self.limit)
        except Exception as e:
            result, ok = str(e), False
        content = result if ok else f"НЕ удалось вызвать инструмент {name}: {result}"
        JOURNAL.add("tool", tool=name, arguments=call["function"]["arguments"], ok=ok, chars=len(content),
                    seconds=round(time.perf_counter() - started, 2))
        return {"role": "tool", "tool_call_id": call["id"], "content": content}
