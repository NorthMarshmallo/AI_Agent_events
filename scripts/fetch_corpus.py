# -*- coding: utf-8 -*-
"""Корпус для RAG: полные тексты страниц, из которых взяты вопросы.

Запуск: python scripts/fetch_corpus.py
Основа корпуса - data/corpus_2026.jsonl: 28 обзорных страниц английской Википедии про 2026 год.
Скрипт докачивает страницы, которых в нём нет (английская и русская Википедия, GEN, ESPN), и дописывает их
в тот же файл. Уже скачанные страницы не трогает, поэтому повторный запуск ничего не скачивает.
В конце проверяет, что цитата evidence каждого вопроса есть в корпусе, и печатает вопросы, у которых её нет.
"""
import html, json, re, sys, time
from pathlib import Path
from urllib.parse import unquote, urlparse
import requests

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent.parent   # корень репозитория, скрипт лежит в scripts/
DATA = HERE / "data"
CORPUS, QUESTIONS = DATA / "corpus_2026.jsonl", DATA / "fresh_2026.jsonl"
HEADERS = {"User-Agent": "ai-agent-events/1.0 (educational project)"}


def get(url, params=None):
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=40)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"не удалось скачать {url}")


def html_lines(markup, tags="p|li|tr|h[2-4]"):
    """Абзацы, пункты списков, строки таблиц и подзаголовки, по одному на строку, как в тексте из Википедии."""
    markup = re.sub(r"(?s)<(style|script|figure|sup)[^>]*>.*?</\1>", "", markup)
    lines = []
    for tag, inner in re.findall(rf"(?s)<({tags})[^>]*>(.*?)</\1>", markup):
        if tag == "tr":
            inner = " | ".join(re.findall(r"(?s)<t[dh][^>]*>(.*?)</t[dh]>", inner))
        text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", inner)).split())
        text = text.replace("[ edit ]", "").replace("[ править | править код ]", "").strip()
        text = re.sub(r"\(\s+", "(", re.sub(r"\s+([,.;:!?)])", r"\1", text))   # пробелы, оставшиеся от вырезанных тегов
        if text and not text.startswith(("^", "↑")):             # строки, начинающиеся с ^ или ↑, это сноски
            lines.append(f"== {text} ==" if tag.startswith("h") else text)
    return "\n".join(lines)


def wiki_text(url):
    """Полная страница Википедии вместе с таблицами и списками: в них лежат результаты соревнований и премий."""
    host, title = urlparse(url).netloc, unquote(url.split("/wiki/")[1]).replace("_", " ")
    params = {"action": "parse", "page": title, "prop": "text", "redirects": 1, "format": "json", "formatversion": 2}
    page = get(f"https://{host}/w/api.php", params).json()
    return html_lines(page["parse"]["text"]) if "parse" in page else ""


def gen_text(url):
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    posts = get("https://www.genengnews.com/wp-json/wp/v2/posts", {"slug": slug, "_fields": "content"}).json()
    return html_lines(posts[0]["content"]["rendered"]) if posts else ""


def espn_text(url):
    """Только абзацы и подзаголовки: списки на странице ESPN это меню сайта и подвал."""
    return html_lines(get(url).text, tags="p|h[2-4]")


FETCHERS = {"en.wikipedia.org": wiki_text, "ru.wikipedia.org": wiki_text, "www.genengnews.com": gen_text, "www.espn.com": espn_text}


def norm(t):
    return " ".join(re.sub(r"[^\w\s]", " ", str(t).lower()).split())


def load(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


if __name__ == "__main__":
    tasks, corpus = load(QUESTIONS), load(CORPUS)
    have = {c["page"] for c in corpus}
    missing = {t["page"]: t["url"] for t in tasks if t["page"] not in have}
    with CORPUS.open("a", encoding="utf-8") as f:
        for page, url in missing.items():
            text = FETCHERS[urlparse(url).netloc](url)
            print(f"{page[:60]:60s} {len(text):8d} символов")
            if text:
                doc = {"page": page, "url": url, "text": text}
                corpus.append(doc)
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    texts = {c["page"]: norm(c["text"]) for c in corpus}
    lost = [t for t in tasks if norm(t["evidence"])[:120] not in texts.get(t["page"], "")]
    lines = sum(len([l for l in c["text"].splitlines() if len(l.strip()) >= 40]) for c in corpus)
    print(f"\nстраниц: {len(corpus)} (скачано сейчас: {len(missing)}), символов: {sum(len(c['text']) for c in corpus)}, "
          f"содержательных строк: {lines}")
    print(f"вопросов с цитатой, найденной в корпусе: {len(tasks) - len(lost)} из {len(tasks)}")
    for t in lost:
        print(f"  нет цитаты: {t['id']} [{t['page']}] {t['evidence'][:100]}")
