"""Render a Transcript as SRT, WebVTT or JSON text (no I/O)."""

import json
import re
from dataclasses import replace
from typing import Literal

from lingotube.errors import ValidationError
from lingotube.models import Cue, Transcript


def _shift(t: Transcript, offset: float) -> Transcript:
    cues: list[Cue] = []
    for c in t.cues:
        if c.end is None:
            raise ValidationError(f"Cue {c.id} has no end time")
        cues.append(replace(c, start=max(0.0, c.start + offset), end=max(0.0, c.end + offset)))
    return replace(t, cues=tuple(cues))


def _stamp(seconds: float, sep: str) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


_ARROW = re.compile(r"-{2,}>")


def _clean(text: str) -> str:
    lines = (ln.strip() for ln in re.split(r"\r\n|\r|\n", text))
    return _ARROW.sub("->", "\n".join(ln for ln in lines if ln))


def _blocks(t: Transcript, sep: str, numbered: bool) -> list[str]:
    out = []
    for c in t.cues:
        assert c.end is not None
        text = _clean(c.text)
        if not text:
            continue
        head = f"{len(out) + 1}\n" if numbered else ""
        out.append(f"{head}{_stamp(c.start, sep)} --> {_stamp(c.end, sep)}\n{text}\n")
    return out


def render(
    transcript: Transcript, fmt: Literal["srt", "vtt", "json"], offset: float = 0.0
) -> str:
    if fmt not in ("srt", "vtt", "json"):
        raise ValidationError(f"Unknown output format: {fmt!r}")
    t = _shift(transcript, offset)
    if fmt == "json":
        return json.dumps(t.to_dict(), ensure_ascii=False, indent=2)
    if fmt == "srt":
        return "\n".join(_blocks(t, ",", True))
    return "WEBVTT\n\n" + "\n".join(_blocks(t, ".", False))
