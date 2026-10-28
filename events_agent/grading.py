"""Проверка ответа кодом, та же, что на этапах 1-3: эталон и ответ приводятся к одному виду, каждая часть эталона должна быть в ответе."""
import re

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
RU_MONTHS = dict(zip(["январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"], MONTHS))
NUMBERS = {w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
NUMBERS.update({w: str(10 * i) for i, w in enumerate("thirty forty fifty sixty seventy eighty ninety".split(), 3)})
NUMBERS.update({w: str(i) for i, w in enumerate("ноль один два три четыре пять шесть семь восемь девять десять одиннадцать двенадцать тринадцать четырнадцать пятнадцать шестнадцать семнадцать восемнадцать девятнадцать двадцать".split())})
NUMBERS.update({w: str(10 * i) for i, w in enumerate("тридцать сорок пятьдесят шестьдесят семьдесят восемьдесят девяносто".split(), 3)})
NUMBERS.update({"одна": "1", "две": "2"})
SCALES = {"thousand": 1e3, "тысяча": 1e3, "тысячи": 1e3, "тысяч": 1e3, "тыс": 1e3,
          "million": 1e6, "m": 1e6, "миллион": 1e6, "миллиона": 1e6, "миллионов": 1e6, "млн": 1e6,
          "billion": 1e9, "bn": 1e9, "миллиард": 1e9, "миллиарда": 1e9, "миллиардов": 1e9, "млрд": 1e9}
REFUSAL = re.compile(r"NOT_FOUND|нет (?:информации|данных|сведений)|отсутству|недоступн|неизвестн|не известн|не удалось|не найден|не установлен"
                     r"|no (?:information|data)|unknown|not (?:available|found)|unable|wasn't able|could ?n[o']t|don't know", re.I)


def normalize(text):
    text = str(text).lower().replace("ё", "е")
    text = re.sub(r"\b\d{1,3}(?:[   ]\d{3})+\b", lambda m: re.sub(r"\D", "", m[0]), text)
    text = re.sub(r"(\d),(?=\d{3}\b)", r"\1", text).replace(",", ".") if re.search(r"\d,\d", text) else text
    text = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", lambda m: f"{int(m[3])} {MONTHS[int(m[2]) - 1]} {m[1]}", text)
    text = re.sub(r"\b(" + "|".join(RU_MONTHS) + r")(?:я|а|е|ь|й)?\b", lambda m: RU_MONTHS[m[1]], text)
    text = re.sub(r"\b(" + "|".join(NUMBERS) + r")\b", lambda m: NUMBERS[m[1]], text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*(" + "|".join(SCALES) + r")(?!\w)", lambda m: str(round(float(m[1]) * SCALES[m[2]])), text)
    text = re.sub(r"(\d)(st|nd|rd|th|-?[а-я]{1,2})\b", r"\1", text)
    text = re.sub(r"(\d+)\.(\d+)", lambda m: m[1] + ("_" + m[2].rstrip("0") if m[2].strip("0") else ""), text)
    text = re.sub(r"(\d) of ", r"\1 ", text)
    text = re.sub(r"[^\w\s]", " ", text.replace(",", ""))
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    text = re.sub(r"\b(" + "|".join(MONTHS) + r") (\d{1,2})\b", r"\2 \1", " ".join(text.split()))
    return text


def part_correct(gold, answer):
    number = re.fullmatch(r"(?:at least |about |over |more than )?(\d+(?:_\d+)?)(?: [^\W\d]+)*", gold)
    if number and not any(m in gold for m in MONTHS):
        return number[1] in answer.split()
    return gold in answer


def final_answer(text):
    m = re.search(r"FINAL:\s*(.+)", text or "")
    return m.group(1).strip() if m else (text or "").strip()


def is_correct(task, answer):
    answer = normalize(final_answer(answer))
    return all(part_correct(normalize(p), answer) for p in task["answer"].split(", "))   # ответ из нескольких частей проверяем по частям


def is_refusal(answer):
    return bool(REFUSAL.search(final_answer(answer)))


def score(task, answer):
    """Верен ли результат: на вопрос без ответа нигде верен только отказ, на остальные - ответ, совпавший с эталоном."""
    if task.get("kind") == "no_answer":
        return is_refusal(answer)
    return is_correct(task, answer)
