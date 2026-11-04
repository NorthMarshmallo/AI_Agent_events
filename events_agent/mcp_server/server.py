"""MCP-сервер слоя свежих знаний.

В Docker он работает как удалённый сервер по Streamable HTTP. База знаний
готовится до начала приёма запросов, поэтому успешный запуск означает, что
Milvus и индекс доступны.
"""
import os
from typing import Annotated, Literal

from pydantic import Field
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .. import golden
from . import kb, web

INSTRUCTIONS = "Fresh knowledge about 2025-2026 events: a local knowledge base of articles and live search on Wikipedia, GEN and ESPN."
Query = Annotated[str, Field(description="короткий поисковый запрос: имя, название, термин")]


def checked(fn, *args):
    """Преобразовать ошибку инструмента в понятный MCP ToolError."""
    try:
        return fn(*args)
    except Exception as e:
        raise ToolError(str(e)) from e


def build(label="full", prepare=True):
    """Собрать MCP-сервер с базой full или eval.

    В обычном запуске prepare=True: база подключается до запуска HTTP-сервера.
    prepare=False оставлен для изолированных тестов, которым нужен только
    список MCP-инструментов без подключения к Milvus.
    """
    exclude = golden.held_out_pages() if label == "eval" else ()
    base = {"kb": kb.connect(exclude, label)} if prepare else {}

    def knowledge(query, page):
        if "kb" not in base:
            base["kb"] = kb.connect(exclude, label)
        hits = base["kb"].search(query, page=page.replace('"', ""))
        if not hits:
            return "nothing found"
        return "\n".join(f"[{h['page']} / {h['section']}] {h['text']}" for h in hits)

    server = MCPServer("fresh-knowledge", instructions=INSTRUCTIONS)

    @server.tool()
    def knowledge_base(query: Annotated[str, Field(description="short search query in English: names, dates, key terms of the event")],
                       page: Annotated[str, Field(description="optional exact page title to search within, for example '2026 in Japan'; empty means all pages")] = "") -> str:
        """Searches the local knowledge base of 2026 events and returns the five closest facts with their page and section. The base holds English Wikipedia overview pages by country and field, such as '2026 in Japan', '2026 in sports', '2026 in science'"""
        return checked(knowledge, query, page)

    @server.tool()
    def web_search(query: Query) -> str:
        """Ищет статью в англоязычной Википедии и возвращает её вступление"""
        return checked(web.web_search, query)

    @server.tool()
    def ru_wiki_search(query: Query) -> str:
        """Ищет статью в русской Википедии и возвращает название и начало статьи. Запрос пишется по-русски, продолжение статьи ищи через page_find с site=ru_wiki"""
        return checked(web.ru_wiki_search, query)

    @server.tool()
    def gen_search(query: Query) -> str:
        """Ищет статью на GEN (Genetic Engineering & Biotechnology News) про биотех и AI в биологии и возвращает название и начало статьи. Запрос пишется по-английски, продолжение статьи ищи через page_find с site=gen"""
        return checked(web.gen_search, query)

    @server.tool()
    def espn_search(query: Query) -> str:
        """Ищет спортивную новость на ESPN и возвращает название и начало статьи. Запрос пишется по-английски, продолжение статьи ищи через page_find с site=espn"""
        return checked(web.espn_search, query)

    @server.tool()
    def page_find(title: Annotated[str, Field(description="название статьи из квадратных скобок в ответе поиска, например 2026 in Japan")],
                  keywords: Annotated[list[str], Field(description="ключевые слова для поиска предложений в статье: имена, места, даты, например ['Haneda', 'August 24']")],
                  site: Annotated[Literal["en_wiki", "ru_wiki", "gen", "espn"], Field(description="откуда статья: en_wiki после web_search, ru_wiki после ru_wiki_search, gen после gen_search, espn после espn_search")] = "en_wiki") -> str:
        """Ищет предложения с ключевыми словами в полном тексте статьи, которую нашёл инструмент поиска. Нужна, когда во вступлении из поиска ответа нет: передай название статьи из квадратных скобок и сайт, где она найдена"""
        return checked(web.page_find, title, keywords, site)

    return server


def main():
    build(os.getenv("KB_BASE", "full")).run(
        "streamable-http",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8090")),
    )


if __name__ == "__main__":
    main()
