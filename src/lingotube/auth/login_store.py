"""Cookies saved by `lingotube login`: one small JSON file, written atomically."""

import asyncio
import json
import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from lingotube.auth.base import LOGIN_HINT
from lingotube.auth.login_browser import LOGIN_BROWSERS
from lingotube.errors import AuthError

_FORMAT_VERSION = 1


@dataclass(frozen=True)
class SavedLogin:
    browser: str
    cookies: dict[str, str]

    def __repr__(self) -> str:
        return f"SavedLogin(browser={self.browser}, cookies=***)"


def _corrupted_login_error() -> AuthError:
    return AuthError(
        message="Сохранённый вход lingotube повреждён или отсутствует.",
        hint=LOGIN_HINT,
    )


def _is_current_format_version(version: object) -> bool:
    # `True == 1`, so a plain comparison would accept a JSON boolean.
    return type(version) is int and version == _FORMAT_VERSION


def _parse_saved_login(raw_text: str) -> SavedLogin:
    try:
        data = json.loads(raw_text)
    except ValueError, RecursionError:
        raise _corrupted_login_error() from None
    if not isinstance(data, dict) or not _is_current_format_version(
        data.get("version")
    ):
        raise _corrupted_login_error()
    browser = data.get("browser")
    cookies = data.get("cookies")
    if browser not in LOGIN_BROWSERS or not isinstance(cookies, dict):
        raise _corrupted_login_error()
    if not all(
        isinstance(name, str) and isinstance(value, str)
        for name, value in cookies.items()
    ):
        raise _corrupted_login_error()
    return SavedLogin(
        browser=browser,
        cookies=cookies,
    )


class LoginCookieStore:
    def __init__(self, cookies_file: Path) -> None:
        self._cookies_file = cookies_file

    def exists(self) -> bool:
        return self._cookies_file.is_file()

    async def read(self) -> SavedLogin:
        return await asyncio.to_thread(self._read_blocking)

    async def write(self, saved: SavedLogin) -> None:
        await asyncio.to_thread(
            self._write_blocking,
            saved,
        )

    async def delete(self) -> bool:
        """True if a file was removed."""
        return await asyncio.to_thread(self._delete_blocking)

    def _read_blocking(self) -> SavedLogin:
        try:
            raw_text = self._cookies_file.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            raise _corrupted_login_error() from None
        return _parse_saved_login(raw_text=raw_text)

    def _write_blocking(self, saved: SavedLogin) -> None:
        payload = json.dumps(
            {
                "version": _FORMAT_VERSION,
                "browser": saved.browser,
                "cookies": saved.cookies,
            },
            ensure_ascii=False,
        )
        directory = self._cookies_file.parent
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        fd, tmp = tempfile.mkstemp(
            dir=directory,
            prefix=".tmp-",
            suffix=".part",
        )  # mkstemp creates the file with mode 0600 (ignored on Windows)
        try:
            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
            ) as f:
                f.write(payload)
            os.replace(
                src=tmp,
                dst=self._cookies_file,
            )
        except BaseException:
            # Only a failed write leaves a temporary file behind; after a successful
            # replace it no longer exists.
            with suppress(FileNotFoundError):
                os.unlink(tmp)
            raise

    def _delete_blocking(self) -> bool:
        try:
            self._cookies_file.unlink()
        except FileNotFoundError:
            return False
        return True
