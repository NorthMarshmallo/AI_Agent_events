"""Прогон конфигураций на golden set и итоговая таблица.

Ответ, вызовы модели и инструментов каждой задачи пишутся в traces/<вариант>/<модель>/<задача>.json.
Если трейс уже есть, модель не вызывается: повторный прогон и печать таблицы бесплатны.
Строка сильной модели без инструментов собрана из трейсов этапов 1 и 2, новых вызовов для неё нет.
"""
import contextvars, json, statistics, time
from concurrent.futures import ThreadPoolExecutor
from . import agent, config, golden
from .grading import final_answer, score
from .llm import JOURNAL, QID, TAG

CONFIGS = {"s4-1-база и поиск": "агент",                       # вариант таблицы: роль с её белым списком инструментов
           "s4-2-только поиск": "агент без базы"}
REFERENCE = {"fresh": "s1-1-без инструментов", "unanswerable": "s2-3-без инструментов"}   # Sonnet без инструментов


def folder(variant, model):
    return config.TRACES / variant / model.split("/")[-1]


def pending(variant, model, tasks):
    return [t for t in tasks if not (folder(variant, model) / f"{t['id']}.json").exists()]


def solve(variant, model, task, toolbox):
    path = folder(variant, model) / f"{task['id']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    TAG.set(variant)
    QID.set(task["id"])
    started = time.perf_counter()
    try:
        answer, messages = agent.run(task["question"], toolbox, model)
    except Exception as e:                                      # сбой сети или API: не сохраняем, в следующий раз задача пройдёт заново
        return {"task": task, "answer": f"ошибка: {type(e).__name__}: {e}"[:300], "calls": [], "tools": [], "seconds": None}
    trace = {"task": task, "answer": answer, "seconds": round(time.perf_counter() - started, 1),
             "calls": JOURNAL.of(task["id"], "model", variant), "embeds": JOURNAL.of(task["id"], "embed", variant),
             "tools": JOURNAL.of(task["id"], "tool", variant), "messages": messages}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace, ensure_ascii=False, indent=1), encoding="utf-8")
    return trace


def run(variant, model=config.CHEAP, tasks=None, toolbox=None, workers=6):
    tasks = tasks or golden.tasks()
    with ThreadPoolExecutor(workers) as ex:                     # copy_context: у каждого потока свои метка и номер задачи
        futures = [ex.submit(contextvars.copy_context().run, solve, variant, model, t, toolbox) for t in tasks]
        return [f.result() for f in futures]


def reference(tasks=None):
    out = []
    for t in tasks or golden.tasks():
        path = folder(REFERENCE[t["source"]], config.STRONG) / f"{t['id']}.json"
        old = json.loads(path.read_text(encoding="utf-8"))
        out.append({"task": t, "answer": old["answer"], "seconds": old.get("seconds"), "calls": None, "cost": old["cost"]})
    return out


def row(variant, model, traces):
    n = len(traces)
    ok = [score(t["task"], t["answer"]) for t in traces]
    by_group = {g: f"{sum(o for o, t in zip(ok, traces) if t['task']['group'] == g)}/{sum(t['task']['group'] == g for t in traces)}"
                for g in (golden.IN_BASE, golden.SEARCH_ONLY, golden.NO_ANSWER)}
    known = all(t["calls"] is not None for t in traces)         # у трейсов этапов 1-2 нет списка вызовов
    calls = [c for t in traces for c in (t["calls"] or [])]
    embeds = [c for t in traces for c in t.get("embeds", [])]
    cost = sum(t["cost"] for t in traces) if not known else sum(c["cost"] for c in calls + embeds)
    prompt = sum(c["prompt"] for c in calls)
    tool_tax = sum(c.get("tool_tax_tokens", 0) for c in calls)
    seconds = [t["seconds"] for t in traces if t["seconds"] is not None]
    return {"вариант": variant, "модель": model.split("/")[-1], "верно": f"{sum(ok)}/{n}", "доля верных": round(sum(ok) / n, 3), **by_group,
            "вызовов на задачу": round(len(calls) / n, 1) if known else 1.0,
            "токенов на задачу": round((prompt + sum(c["completion"] for c in calls)) / n) if known else None,
            "доля входа из кэша": round(sum(c.get("cached", 0) for c in calls) / prompt, 3) if known and prompt else None,
            "налог инструментов, токенов": round(tool_tax / n) if known else None,
            "центов на задачу": round(cost / n * 100, 4), "центов за верный": round(cost / sum(ok) * 100, 4) if sum(ok) else None,
            "задержка, с": round(statistics.mean(seconds), 1) if len(seconds) == n else None}


def wrong(traces, n=None):
    return [{"id": t["task"]["id"], "группа": t["task"]["group"], "эталон": t["task"]["answer"], "ответ": final_answer(t["answer"])[:110]}
            for t in traces if not score(t["task"], t["answer"])][:n]
