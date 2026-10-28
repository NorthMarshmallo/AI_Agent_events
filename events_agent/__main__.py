"""Командная строка, после uv sync доступна как events-agent (или python -m events_agent).

    events-agent ask "Who won the 2026 Indianapolis 500?"                ответить на один вопрос по всей базе и поиску
    events-agent eval                                                    таблица по готовым трейсам, без вызовов модели
    events-agent eval --ids fresh-0 fresh-125 none-0                     то же для отдельных задач
    events-agent eval --config "s4-1-база и поиск" --limit 3 --yes       прогнать недостающие задачи: это тратит деньги
"""
import argparse, sys
import pandas as pd
from . import agent, config, evaluate, golden, kb
from .grading import final_answer
from .llm import JOURNAL
from .web import WEB_TOOLS


def ask(args):
    kb.connect()
    path = JOURNAL.start("ask")
    answer, _ = agent.run(args.question, ["knowledge_base", *WEB_TOOLS], args.model)
    calls, embeds = JOURNAL.of(None), JOURNAL.of(None, "embed")
    print(final_answer(answer))
    print(f"\nвызовов модели: {len(calls)}, цена: {sum(c['cost'] for c in calls + embeds) * 100:.4f} цента, журнал: {path}")


def run_eval(args):
    tasks = golden.tasks()
    tasks = [t for t in tasks if t["id"] in args.ids] if args.ids else tasks[:args.limit] if args.limit else tasks
    rows = [evaluate.row("Sonnet без инструментов, этапы 1-2", config.STRONG, evaluate.reference(tasks))]
    for variant in [args.config] if args.config else evaluate.CONFIGS:
        todo = evaluate.pending(variant, args.model, tasks)
        if todo and not args.yes:
            print(f"{variant}: без трейса {len(todo)} задач из {len(tasks)}; чтобы прогнать их моделью, добавьте --yes")
            continue
        if todo:
            if "knowledge_base" in evaluate.CONFIGS[variant]:
                kb.connect(golden.held_out_pages(), "eval")
            print(f"{variant}: прогон {len(todo)} задач, журнал {JOURNAL.start(variant.split('-')[1])}")
        rows.append(evaluate.row(variant, args.model, evaluate.run(variant, args.model, tasks)))
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).to_string(index=False))


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="events-agent", description="Слой свежих знаний: база статей и живой поиск")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("ask", help="ответить на вопрос")
    p.add_argument("question")
    p.add_argument("--model", default=config.CHEAP)
    p.set_defaults(fn=ask)
    p = sub.add_parser("eval", help="прогон golden set и таблица")
    p.add_argument("--config", choices=list(evaluate.CONFIGS))
    p.add_argument("--model", default=config.CHEAP)
    p.add_argument("--limit", type=int, help="первые N задач: для отладки")
    p.add_argument("--ids", nargs="+", help="только эти задачи, например fresh-0 fresh-125 none-0")
    p.add_argument("--yes", action="store_true", help="разрешить вызовы модели для задач без трейса")
    p.set_defaults(fn=run_eval)
    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
