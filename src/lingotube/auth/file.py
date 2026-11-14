"""Netscape cookies.txt source (parsed by hand: MozillaCookieJar drops #HttpOnly_ lines)."""

import asyncio
import os
import re
import stat
from collections.abc import Callable
from pathlib import Path

from lingotube.auth.base import EXPORT_HINT, Credentials, is_allowed_domain
from lingotube.errors import AuthError

_HTTP_ONLY = "#HttpOnly_"
_CONTROL = re.compile(pattern=r"[--]")


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
        if _CONTROL.search(string=name + value):
            continue  # would break HTTP headers; never echo the value
        if name and is_allowed_domain(domain=domain):
            cookies[name] = value
    return cookies


class FileCookieSource:
    """Load cookies from a Netscape cookies.txt file.

    The file is parsed by hand, because MozillaCookieJar drops the ``#HttpOnly_`` lines,
    and those cookies are needed.
    """

    def __init__(
        self,
        path: Path,
        warn: Callable[[str], None] = lambda msg: None,
    ) -> None:
        """Create the source.

        Args:
            path: Path to the cookies.txt file.
            warn: Function that receives warnings, for example about file permissions.
        """
        self._path = Path(path)
        self._warn = warn

    def _read(self) -> tuple[str, int | None]:
        text = self._path.read_text(
            encoding="utf-8",
            errors="replace",
        )
        mode = None if os.name == "nt" else stat.S_IMODE(self._path.stat().st_mode)
        return text, mode

    async def load(self) -> Credentials:
        """Read the file and return the credentials.

        Returns:
            The credentials found in the file.

        Raises:
            AuthError: If the file cannot be read or has no SAPISID cookie.
        """
        try:
            text, mode = await asyncio.to_thread(self._read)
        except OSError:
            raise AuthError(
                message=f"Не удалось прочитать файл cookies: {self._path}",
                hint=EXPORT_HINT,
            ) from None
        if mode is not None and mode & 0o044:
            self._warn(f"Файл cookies доступен другим пользователям: {self._path} (chmod 600).")
        creds = Credentials(cookies=_parse(text=text))
        creds.require_sapisid()
        return creds
