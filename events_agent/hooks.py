"""Проверки на границе между моделью и инструментами.

Модель предлагает имя инструмента и аргументы, но окончательное решение
принимает код клиента. Хуки не заменяют MCP-схемы: они добавляют проверки,
которые должны выполняться перед сетью и после получения результата.
"""
from __future__ import annotations

from typing import Any

QUERY_TOOLS = {"knowledge_base", "web_search", "ru_wiki_search", "gen_search", "espn_search"}
SITES = {"en_wiki", "ru_wiki", "gen", "espn"}
MAX_QUERY_CHARS = 300
MAX_KEYWORDS = 8


def before_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Проверить аргументы до вызова удалённого MCP-инструмента."""
    if not isinstance(args, dict):
        raise ValueError("аргументы инструмента должны быть объектом")

    if name in QUERY_TOOLS:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("поисковый запрос не должен быть пустым")
        if len(query) > MAX_QUERY_CHARS:
            raise ValueError(f"поисковый запрос длиннее {MAX_QUERY_CHARS} символов")
        args = {**args, "query": query.strip()}

    if name == "page_find":
        title = args.get("title")
        keywords = args.get("keywords")
        site = args.get("site", "en_wiki")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("название статьи не должно быть пустым")
        if not isinstance(keywords, list) or not 1 <= len(keywords) <= MAX_KEYWORDS:
            raise ValueError(f"нужно от одного до {MAX_KEYWORDS} ключевых слов")
        if not all(isinstance(word, str) and word.strip() for word in keywords):
            raise ValueError("ключевые слова должны быть непустыми строками")
        if site not in SITES:
            raise ValueError(f"неизвестный сайт: {site}")
        args = {**args, "title": title.strip(), "keywords": [word.strip() for word in keywords]}

    return args


def after_tool(name: str, result: str, limit: int) -> str:
    """Ограничить результат инструмента до безопасного размера контекста."""
    if not isinstance(result, str):
        raise ValueError(f"инструмент {name} вернул не текст")
    clean = result.replace("\x00", "")
    return clean[:limit]
