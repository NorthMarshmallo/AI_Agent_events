"""Golden set этапа 4: 27 вопросов с ответом в базе, 30 с ответом только в интернете и 10 без ответа в базе.

Страницы вопросов по интересам (fresh-125...fresh-154) в базу не кладутся: так база отстаёт от событий, как в жизни,
и на этих вопросах ответ находит только живой поиск. Вместе с ними откладывается русская страница про женское
одиночное катание на Олимпиаде: у неё нет своих вопросов, но она пересказывает отложенную английскую.
"""
import json
from . import config

IN_BASE, SEARCH_ONLY, NO_ANSWER = "ответ в базе", "ответ только в интернете", "ответа нет в базе"
EXTRA_HELD_OUT = {"Фигурное катание на зимних Олимпийских играх 2026 — одиночное катание (женщины)"}


def load_jsonl(name):
    return [json.loads(line) for line in (config.DATA / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def number(task):
    return int(task["id"].split("-")[1])


def held_out_pages():
    return {t["page"] for t in load_jsonl("fresh_2026.jsonl") if number(t) >= 125} | EXTRA_HELD_OUT


def tasks():
    fresh = load_jsonl("fresh_2026.jsonl")
    return ([{**t, "group": IN_BASE} for t in fresh[:27]] + [{**t, "group": SEARCH_ONLY} for t in fresh[125:]]
            + [{**t, "group": NO_ANSWER} for t in load_jsonl("unanswerable_2026.jsonl")])
