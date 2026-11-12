"""Планирование отрезков, склейка, исправление концов реплик, проверка полноты."""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from lingotube.models import Cue
from lingotube.parsing import ParsedLine

_SEAM_WINDOW = 2.0


def plan_ranges(
    duration: float,
    chunk_seconds: int,
) -> list[tuple[float, float]]:
    """Отрезки [начало, конец) подряд длиной chunk_seconds; последний обрезан по длительности."""
    ranges: list[tuple[float, float]] = []
    start = 0.0
    while start < duration:
        ranges.append(
            (
                start,
                min(
                    start + chunk_seconds,
                    duration,
                ),
            )
        )
        start += chunk_seconds
    return ranges


def is_truncated(
    lines: Sequence[ParsedLine],
    range_end: float,
    tolerance: float = 60.0,
) -> bool:
    """Ответ оборван: последняя реплика заканчивается заметно раньше конца запрошенного отрезка."""
    if not lines:
        return True
    last = lines[-1]
    reached = last.end if last.end is not None else last.start
    return reached < range_end - tolerance


def merge(chunks: Sequence[Sequence[ParsedLine]]) -> list[Cue]:
    """Склейка отрезков: сортировка по началу, удаление дублей на стыках, номера с 1."""
    lines = sorted(
        (line for chunk in chunks for line in chunk),
        key=lambda line: line.start,
    )
    kept: list[ParsedLine] = []
    for line in lines:
        text = line.text.strip()
        if _is_duplicate(
            kept=kept,
            start=line.start,
            text=text,
        ):
            continue
        kept.append(
            replace(
                line,
                text=text,
            )
        )
    joined: list[ParsedLine] = []
    for line in kept:
        if joined and joined[-1].start == line.start:
            prev = joined[-1]
            ends = [e for e in (prev.end, line.end) if e is not None]
            joined[-1] = ParsedLine(
                start=prev.start,
                end=max(ends) if ends else None,
                text=f"{prev.text} {line.text}",
            )
        else:
            joined.append(line)
    return [
        Cue(
            id=i,
            start=line.start,
            end=line.end,
            text=line.text,
        )
        for i, line in enumerate(
            joined,
            1,
        )
    ]


def _is_duplicate(
    kept: Sequence[ParsedLine],
    start: float,
    text: str,
) -> bool:
    for prev in reversed(kept):
        if start - prev.start > _SEAM_WINDOW:
            return False
        if prev.text == text:
            return True
    return False


def fix_ends(
    cues: Sequence[Cue],
    duration: float,
    *,
    min_s: float = 1.5,
    max_s: float = 7.0,
    cps: float = 15.0,
) -> list[Cue]:
    """Оставляет конец чата, если он верен; иначе обрезает по границам или считает по времени чтения.

    Реплики, начинающиеся не раньше конца видео, отбрасываются; номера перенумеровываются с 1.
    """
    cues = [c for c in cues if c.start < duration]
    out: list[Cue] = []
    for i, cue in enumerate(cues):
        limit = duration
        next_start = next(
            (c.start for c in cues[i + 1 :] if c.start > cue.start),
            None,
        )
        if next_start is not None:
            limit = min(
                limit,
                next_start,
            )
        if cue.end is not None and cue.end > cue.start:
            end = min(
                cue.end,
                limit,
            )
        else:
            reading = min(
                max(
                    len(cue.text) / cps,
                    min_s,
                ),
                max_s,
            )
            end = min(
                cue.start + reading,
                limit,
            )
        out.append(
            replace(
                cue,
                id=i + 1,
                end=end,
            )
        )
    return out


@dataclass(frozen=True)
class Completeness:
    complete: bool
    last_end: float
    gaps: tuple[tuple[float, float], ...]


def check_completeness(
    cues: Sequence[Cue],
    duration: float,
    *,
    tail_tolerance: float | None = None,
    gap_warn: float = 120.0,
) -> Completeness:
    """Доходит ли последняя реплика до конца видео; пустоты длиннее gap_warn — только предупреждение."""
    if not cues:
        return Completeness(
            complete=False,
            last_end=0.0,
            gaps=(),
        )
    if tail_tolerance is None:
        tail_tolerance = max(
            60.0,
            0.05 * duration,
        )
    gaps: list[tuple[float, float]] = []
    reached = 0.0
    for cue in cues:
        if cue.start - reached > gap_warn:
            gaps.append((reached, cue.start))
        reached = max(
            reached,
            cue.end if cue.end is not None else cue.start,
        )
    return Completeness(
        complete=reached >= duration - tail_tolerance,
        last_end=reached,
        gaps=tuple(gaps),
    )
