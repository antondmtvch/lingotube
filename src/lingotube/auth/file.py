"""Netscape cookies.txt source (parsed by hand: MozillaCookieJar drops #HttpOnly_ lines)."""

import asyncio
import os
import stat
from collections.abc import Callable
from pathlib import Path

from lingotube.auth.base import EXPORT_HINT, Credentials, is_allowed_domain
from lingotube.errors import AuthError

_HTTP_ONLY = "#HttpOnly_"


def _parse(text: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(_HTTP_ONLY):
            line = line[len(_HTTP_ONLY) :]
        elif not line or line.startswith("#"):
            continue
        parts = line.split("	")
        if len(parts) != 7:
            continue
        domain, name, value = parts[0], parts[5], parts[6]
        if name and is_allowed_domain(domain):
            cookies[name] = value
    return cookies


class FileCookieSource:
    def __init__(
        self, path: Path, warn: Callable[[str], None] = lambda msg: None
    ) -> None:
        self._path = Path(path)
        self._warn = warn

    def _read(self) -> tuple[str, int | None]:
        text = self._path.read_text(encoding="utf-8", errors="replace")
        mode = None if os.name == "nt" else stat.S_IMODE(self._path.stat().st_mode)
        return text, mode

    async def load(self) -> Credentials:
        try:
            text, mode = await asyncio.to_thread(self._read)
        except OSError:
            raise AuthError(
                f"Не удалось прочитать файл cookies: {self._path}", EXPORT_HINT
            ) from None
        if mode is not None and mode & 0o044:
            self._warn(
                f"Файл cookies доступен другим пользователям: {self._path} (chmod 600)."
            )
        creds = Credentials(_parse(text))
        creds.require_sapisid()
        return creds
