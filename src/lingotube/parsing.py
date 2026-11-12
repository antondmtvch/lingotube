"""Разбор текстового ответа чата YouTube в реплики с тайм-кодами."""

import re
from dataclasses import dataclass

_TIME = r"(\d{1,3}:\d{2}(?::\d{2})?)"
_CUE = re.compile(
    pattern=r"^(?:[-*•]\s++)?\**+\s*+[(\[]\s*"
    + _TIME
    + r"(?:\s*[-–—]\s*"
    + _TIME
    + r")?\s*[)\]]\s*\**\s*(.*)$"
)


@dataclass(
    frozen=True,
    slots=True,
)
class ParsedLine:
    start: float
    end: float | None
    text: str


def _seconds(stamp: str) -> float | None:
    """Секунды из м:сс / ч:мм:сс; None, если части вне диапазона 0-59."""
    parts = [int(p) for p in stamp.split(sep=":")]
    if any(p > 59 for p in parts[1:]) or (len(parts) == 3 and parts[0] > 99):
        return None
    total = 0
    for part in parts:
        total = total * 60 + part
    return float(total)


def parse_answer(text: str) -> list[ParsedLine]:
    """Превращает ответ чата в реплики; без тайм-кодов возвращает []. Не бросает."""
    cues: list[list] = []  # [start, end, text]
    gap = False  # после последней реплики встретилась пустая строка
    for raw in text.splitlines():
        line = raw.strip()
        match = _CUE.match(string=line)
        if match:
            start = _seconds(stamp=match.group(1))
            end = _seconds(stamp=match.group(2)) if match.group(2) else None
            if start is not None and (end is not None or not match.group(2)):
                if end is not None and end < start:
                    end = None  # конец вычислит fix_ends
                cues.append([start, end, match.group(3).strip()])
                gap = False
                continue
        if not cues:
            continue  # вступление до первого тайм-кода
        if not line:
            gap = True
        elif not gap:
            cues[-1][2] = f"{cues[-1][2]} {line}".strip()
        # иначе: заключительная фраза после пустой строки — отбрасывается
    return [
        ParsedLine(
            start=s,
            end=e,
            text=t,
        )
        for s, e, t in cues
        if t
    ]
