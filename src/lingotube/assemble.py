"""Plan the time ranges, join them, fix the line ends and check completeness."""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from lingotube.models import Cue
from lingotube.parsing import ParsedLine

_SEAM_WINDOW = 2.0
_MIN_TAIL = 1.0  # a shorter last range is merged into the previous one


def plan_ranges(
    duration: float,
    chunk_seconds: int,
) -> list[tuple[float, float]]:
    """Split the video into consecutive ranges of ``chunk_seconds``.

    The last range is cut at the end of the video.

    Args:
        duration: Length of the video in seconds.
        chunk_seconds: Length of one range in seconds.

    Returns:
        Half-open ranges ``[start, end)`` in seconds.
    """
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
    if len(ranges) > 1 and ranges[-1][1] - ranges[-1][0] < _MIN_TAIL:
        tail = ranges.pop()
        ranges[-1] = (
            ranges[-1][0],
            tail[1],
        )
    return ranges


def is_truncated(
    lines: Sequence[ParsedLine],
    range_end: float,
    tolerance: float = 60.0,
) -> bool:
    """Check whether a chat answer stops well before the end of its range.

    Args:
        lines: Lines parsed from the answer.
        range_end: End of the requested range in seconds.
        tolerance: How much shorter than the range the answer may be, in seconds.

    Returns:
        True if the answer is empty or ends more than ``tolerance`` seconds before
        ``range_end``.
    """
    if not lines:
        return True
    reached = max(line.end if line.end is not None else line.start for line in lines)
    return reached < range_end - tolerance


def merge(chunks: Sequence[Sequence[ParsedLine]]) -> list[Cue]:
    """Join the parsed ranges into one list of cues.

    Lines are sorted by start time, duplicates at the seams are removed, and the cues
    are numbered from 1.

    Args:
        chunks: Parsed lines of each range.

    Returns:
        The joined cues.
    """
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
    """Keep the end time from the chat when it is valid, otherwise fix it.

    The end is cut at the next cue or at the end of the video. If there is no valid end,
    it is estimated from the reading time. Cues that start at or after the end of the
    video are dropped, and the rest are renumbered from 1.

    Args:
        cues: Cues to fix.
        duration: Length of the video in seconds.
        min_s: Shortest estimated duration of a cue, in seconds.
        max_s: Longest estimated duration of a cue, in seconds.
        cps: Reading speed in characters per second.

    Returns:
        The cues with fixed end times.
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
    """Result of the completeness check.

    Attributes:
        complete: True if the last cue reaches the end of the video.
        last_end: End time of the last cue, in seconds.
        gaps: Silent stretches longer than the warning threshold, as (start, end) pairs.
    """

    complete: bool
    last_end: float
    gaps: tuple[tuple[float, float], ...]


def check_completeness(
    cues: Sequence[Cue],
    duration: float,
    *,
    tail_tolerance: float | None = None,
    gap_warn: float = 60.0,
) -> Completeness:
    """Check whether the transcript reaches the end of the video.

    Silent stretches longer than ``gap_warn`` are reported as gaps. They do not make the
    transcript incomplete.

    Args:
        cues: Cues of the transcript.
        duration: Length of the video in seconds.
        tail_tolerance: How far before the end the last cue may stop, in seconds. Defaults
            to the larger of 60 seconds and 5% of the duration.
        gap_warn: Length in seconds from which a silent stretch is reported.

    Returns:
        The completeness result.
    """
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
    for cue in sorted(
        cues,
        key=lambda c: c.start,
    ):
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
