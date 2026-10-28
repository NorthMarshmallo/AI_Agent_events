"""Живой поиск из этапов 1 и 3: английская и русская Википедия, GEN, ESPN и page_find по полному тексту найденной статьи."""
import html, re, time
from typing import Literal
import requests
from pydantic import BaseModel, Field
from .tools import register

WIKI = "https://en.wikipedia.org/w/api.php"
RU_WIKI = "https://ru.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "ai-agent-events/0.4 (https://github.com/NorthMarshmallo)"}


def wiki(params, attempts=3):
    for attempt in range(attempts):
        try:
            r = requests.get(WIKI, params={**params, "format": "json"}, headers=HEADERS, timeout=15)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
                return r.json()["query"]
            error = f"ответила {r.status_code}"
        except requests.RequestException as e:
            error = f"недоступна: {type(e).__name__}"
        time.sleep(1.0 + attempt)
    raise RuntimeError(f"Википедия {error}")


def get_page(url, site, params=None, attempts=3):
    for attempt in range(attempts):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r
            error = f"ответил {r.status_code}"
        except requests.RequestException as e:
            error = f"недоступен: {type(e).__name__}"
        time.sleep(1.0 + attempt)
    raise RuntimeError(f"{site} {error}")


def clean(markup):
    markup = re.sub(r"(?s)<(style|script)[^>]*>.*?</\1>", "", markup)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def en_wiki_article(title):
    page = next(iter(wiki({"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1, "titles": title})["pages"].values()))
    return None if "missing" in page else (page["title"], page.get("extract", ""))


def ru_wiki_article(title):
    page = get_page(RU_WIKI, "Русская Википедия", {"action": "parse", "page": title, "prop": "text", "redirects": 1, "format": "json", "formatversion": 2}).json()
    if "parse" not in page:
        return None
    return page["parse"]["title"], clean(page["parse"]["text"]).replace("[ править | править код ]", "")


def gen_article(query):
    posts = get_page("https://www.genengnews.com/wp-json/wp/v2/posts", "GEN", {"search": query, "orderby": "relevance", "per_page": 5, "_fields": "title,content"}).json()
    if not posts:
        return None
    post = next((p for p in posts if clean(p["title"]["rendered"]) == query), posts[0])
    return clean(post["title"]["rendered"]), clean(post["content"]["rendered"])


def espn_article(query):
    results = get_page("https://site.web.api.espn.com/apis/search/v2", "ESPN", {"query": query, "limit": 5}).json().get("results", [])
    articles = [c for r in results if r.get("type") == "article" for c in r["contents"]]
    if not articles:
        return None
    article = next((a for a in articles if a["displayName"] == query), articles[0])
    story = get_page(f"https://content.core.api.espn.com/v1/sports/news/{article['id']}", "ESPN").json()["headlines"][0]["story"]
    return article["displayName"], clean(story)


def preview(article):
    return f"[{article[0]}] {article[1][:5000]}" if article else "No data"


def web_search(query: str) -> str:
    hits = wiki({"action": "query", "list": "search", "srsearch": query, "srlimit": 1})["search"]
    if not hits:
        return "No data"
    pages = wiki({"action": "query", "prop": "extracts", "explaintext": 1, "exintro": 1, "titles": hits[0]["title"]})["pages"]
    text = " ".join(next(iter(pages.values())).get("extract", "").split())
    return f"[{hits[0]['title']}] {text[:5000]}"


def ru_wiki_search(query: str) -> str:
    hits = get_page(RU_WIKI, "Русская Википедия", {"action": "query", "list": "search", "srsearch": query, "srlimit": 1, "format": "json"}).json()["query"]["search"]
    return preview(ru_wiki_article(hits[0]["title"]) if hits else None)


def gen_search(query: str) -> str:
    return preview(gen_article(query))


def espn_search(query: str) -> str:
    return preview(espn_article(query))


ARTICLES = {"en_wiki": en_wiki_article, "ru_wiki": ru_wiki_article, "gen": gen_article, "espn": espn_article}


def page_find(title: str, keywords: list[str], site: str = "en_wiki") -> str:
    article = ARTICLES[site](title)
    if not article:
        return f"Статья {title} не найдена"
    sentences = re.split(r"(?<=[.!?])\s+|\n+", article[1])
    found = [s for s in sentences if any(k.lower() in s.lower() for k in keywords)]
    return "\n".join(found) if found else "No data"


class SearchArgs(BaseModel):
    query: str = Field(description="короткий поисковый запрос: имя, название, термин")


class FindArgs(BaseModel):
    title: str = Field(description="название статьи из квадратных скобок в ответе поиска, например 2026 in Japan")
    keywords: list[str] = Field(description="ключевые слова для поиска предложений в статье: имена, места, даты, например ['Haneda', 'August 24']")
    site: Literal["en_wiki", "ru_wiki", "gen", "espn"] = Field("en_wiki", description="откуда статья: en_wiki после web_search, ru_wiki после ru_wiki_search, gen после gen_search, espn после espn_search")


register(web_search, SearchArgs, "Ищет статью в англоязычной Википедии и возвращает её вступление")
register(ru_wiki_search, SearchArgs, "Ищет статью в русской Википедии и возвращает название и начало статьи. Запрос пишется по-русски, продолжение статьи ищи через page_find с site=ru_wiki")
register(gen_search, SearchArgs, "Ищет статью на GEN (Genetic Engineering & Biotechnology News) про биотех и AI в биологии и возвращает название и начало статьи. Запрос пишется по-английски, продолжение статьи ищи через page_find с site=gen")
register(espn_search, SearchArgs, "Ищет спортивную новость на ESPN и возвращает название и начало статьи. Запрос пишется по-английски, продолжение статьи ищи через page_find с site=espn")
register(page_find, FindArgs, "Ищет предложения с ключевыми словами в полном тексте статьи, которую нашёл инструмент поиска. Нужна, когда во вступлении из поиска ответа нет: передай название статьи из квадратных скобок и сайт, где она найдена")
WEB_TOOLS = ["web_search", "ru_wiki_search", "gen_search", "espn_search", "page_find"]
