"""Разбор текстового ответа чата YouTube в реплики с тайм-кодами."""

import re
from dataclasses import dataclass

_TIME = r"(\d{1,2}(?::\d{2}){1,2})"
_CUE = re.compile(
    r"^\s*(?:[-*•]\s+)?\**\s*[(\[]\s*" + _TIME + r"(?:\s*[-–—]\s*" + _TIME + r")?\s*[)\]]\s*\**\s*(.*)$"
)


@dataclass(frozen=True, slots=True)
class ParsedLine:
    start: float
    end: float | None
    text: str


def _seconds(stamp: str) -> float:
    total = 0
    for part in stamp.split(":"):
        total = total * 60 + int(part)
    return float(total)


def parse_answer(text: str) -> list[ParsedLine]:
    """Превращает ответ чата в реплики; без тайм-кодов возвращает []. Не бросает."""
    cues: list[list] = []  # [start, end, text]
    gap = False  # после последней реплики встретилась пустая строка
    for raw in text.splitlines():
        match = _CUE.match(raw)
        if match:
            end = match.group(2)
            cues.append([_seconds(match.group(1)), _seconds(end) if end else None, match.group(3).strip()])
            gap = False
            continue
        line = raw.strip()
        if not cues:
            continue  # вступление до первого тайм-кода
        if not line:
            gap = True
        elif not gap:
            cues[-1][2] = f"{cues[-1][2]} {line}".strip()
        # иначе: заключительная фраза после пустой строки — отбрасывается
    return [ParsedLine(s, e, t) for s, e, t in cues if t]
