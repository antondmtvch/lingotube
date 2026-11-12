"""YouTube video id parsing."""

import re
from urllib.parse import parse_qs, urlparse

from lingotube.errors import ValidationError

_ID = re.compile(pattern=r"[A-Za-z0-9_-]{11}")
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_SHORT_HOST = "youtu.be"
_PATH_PREFIXES = ("shorts", "embed")


def _bad(value: str) -> ValidationError:
    return ValidationError(
        message=f"Not a YouTube video link or id: {value!r}",
        hint="Pass a youtube.com / youtu.be link or an 11-character video id.",
    )


def parse_video_id(value: str) -> str:
    raw = value.strip()
    if _ID.fullmatch(string=raw):
        return raw
    try:
        url = urlparse(url=raw)
        host = (url.hostname or "").lower()
    except ValueError:
        raise _bad(value=value) from None
    if url.scheme not in ("http", "https"):
        raise _bad(value=value)
    candidate: str | None = None
    parts = [p for p in url.path.split("/") if p]
    if host == _SHORT_HOST:
        candidate = parts[0] if parts else None
    elif host in _HOSTS:
        if url.path.rstrip("/") == "/watch":
            vals = parse_qs(qs=url.query).get("v")
            candidate = vals[0] if vals else None
        elif len(parts) >= 2 and parts[0] in _PATH_PREFIXES:
            candidate = parts[1]
    if candidate is None or not _ID.fullmatch(string=candidate):
        raise _bad(value=value)
    return candidate
