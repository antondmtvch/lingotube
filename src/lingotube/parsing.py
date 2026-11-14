"""Parse the text answer of the YouTube chat into timed lines."""

import re
from dataclasses import dataclass

_TIME = r"\d{1,3}:\d{2}(?::\d{2})?"
_CUE = re.compile(
    pattern=r"^(?:(?:[-*•–—]|\d{1,3}[.)])\s++)?(?P<bold>\**+)\s*+[(\[]\s*"
    + "(?P<start>"
    + _TIME
    + r")(?:\s*[-–—]\s*(?P<end>"
    + _TIME
    + r"))?\s*[)\]]\s*\**\s*(?P<text>.*)$"
)


@dataclass(
    frozen=True,
    slots=True,
)
class ParsedLine:
    """One timed line parsed from a chat answer.

    Attributes:
        start: Start time in seconds.
        end: End time in seconds, or None if the answer gave no end.
        text: Text of the line.
    """

    start: float
    end: float | None
    text: str


def _seconds(stamp: str) -> float | None:
    """Convert a timecode in m:ss or h:mm:ss form to seconds.

    Args:
        stamp: Timecode text, for example ``1:05`` or ``1:02:03``.

    Returns:
        The number of seconds, or None if a part is outside 0-59.
    """
    parts = [int(p) for p in stamp.split(":")]
    if any(p > 59 for p in parts[1:]) or (len(parts) == 3 and parts[0] > 99):
        return None
    total = 0
    for part in parts:
        total = total * 60 + part
    return float(total)


def parse_answer(text: str) -> list[ParsedLine]:
    """Turn the chat answer into timed lines.

    Lines without a valid timecode are not used. The function never raises.

    Args:
        text: Text answer of the chat.

    Returns:
        The timed lines in order, or an empty list if the answer has no timecodes.
    """
    cues: list[list] = []  # [start, end, text]
    gap = False  # после последней реплики встретилась пустая строка
    for raw in text.splitlines():
        line = raw.strip()
        match = _CUE.match(string=line)
        if match:
            start = _seconds(stamp=match.group("start"))
            end = _seconds(stamp=match.group("end")) if match.group("end") else None
            if start is not None and (end is not None or not match.group("end")):
                if end is not None and end < start:
                    end = None  # конец вычислит fix_ends
                body = match.group("text").strip()
                if match.group("bold"):
                    body = body.rstrip("*").strip()  # "**(0:02) x**": closing bold
                cues.append([start, end, body])
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
