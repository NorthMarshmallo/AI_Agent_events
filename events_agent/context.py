"""Ограничение истории сообщений, передаваемой модели."""
from __future__ import annotations

from typing import Any


def message_chars(messages: list[dict[str, Any]]) -> int:
    return sum(len(str(message.get("content") or "")) for message in messages)


def compact(messages: list[dict[str, Any]], max_chars: int = 16000, keep_rounds: int = 2):
    """Сжать старые пары вызов инструмента/результат.

    Начало запроса и последние полные раунды сохраняются. Старые результаты
    заменяются коротким техническим конспектом, чтобы следующий вызов модели
    не получал бесконечно растущую историю.
    """
    before = message_chars(messages)
    if before <= max_chars or len(messages) <= 2:
        return messages, {"before_chars": before, "after_chars": before, "dropped_rounds": 0}

    head, body = messages[:2], messages[2:]
    rounds: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for message in body:
        if message.get("role") == "assistant" and message.get("tool_calls") and current:
            rounds.append(current)
            current = []
        current.append(message)
    if current:
        rounds.append(current)

    dropped = max(0, len(rounds) - keep_rounds)
    if dropped:
        notes = []
        for round_messages in rounds[:-keep_rounds]:
            for message in round_messages:
                if message.get("role") == "tool" and message.get("content"):
                    text = str(message["content"]).replace("\n", " ")
                    notes.append(text[:240])
        summary = "Ранние результаты инструментов сокращены кодом: " + " | ".join(notes[:6])
        out = head + [{"role": "user", "content": summary}] + [m for r in rounds[-keep_rounds:] for m in r]
    else:
        out = list(messages)

    if message_chars(out) > max_chars:
        # Последний рубеж: не удаляем структуру раундов, только уменьшаем текст
        # результатов инструментов, которые занимают основную часть контекста.
        trimmed = []
        for message in out:
            copy = dict(message)
            if copy.get("role") == "tool" and isinstance(copy.get("content"), str):
                copy["content"] = copy["content"][:600] + ("…" if len(copy["content"]) > 600 else "")
            trimmed.append(copy)
        out = trimmed

    return out, {"before_chars": before, "after_chars": message_chars(out), "dropped_rounds": dropped}
