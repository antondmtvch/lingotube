"""Browser cookie source (browser-cookie3, imported lazily) and the fallback chain."""

import asyncio
import sys
from collections.abc import Callable, Mapping, Sequence

from lingotube.auth.base import (
    EXPORT_HINT,
    CookieSource,
    Credentials,
    is_allowed_domain,
)
from lingotube.errors import AuthError

BROWSERS = ("firefox", "chrome", "edge", "brave")
_WIN_HINT = "Chrome/Edge на Windows обычно нельзя прочитать напрямую. " + EXPORT_HINT


def default_loader(browser: str) -> Mapping[str, str]:
    import browser_cookie3  # lazy: optional at runtime, never needed in tests

    func = getattr(
        browser_cookie3,
        browser,
    )
    cookies: dict[str, str] = {}
    for domain in ("youtube.com", "google.com"):
        for c in func(domain_name=domain):
            if c.value is not None and is_allowed_domain(domain=c.domain):
                cookies[c.name] = c.value
    return cookies


class BrowserCookieSource:
    def __init__(
        self,
        browser: str | None = None,
        loader: Callable[[str], Mapping[str, str]] | None = None,
    ) -> None:
        if browser is not None and browser not in BROWSERS:
            raise ValueError(f"unknown browser: {browser}")
        self._browser = browser
        self._loader = loader or default_loader

    def _hint(self, browser: str) -> str:
        if sys.platform == "win32" and browser in ("chrome", "edge"):
            return _WIN_HINT
        return EXPORT_HINT

    def _load_one(self, browser: str) -> Credentials:
        try:
            cookies = self._loader(browser)
        except Exception:  # never propagate text: may contain paths or values
            raise AuthError(
                message=f"Не удалось прочитать cookies из браузера {browser}.",
                hint=self._hint(browser=browser),
            ) from None
        creds = Credentials(cookies=cookies)
        if not creds.sapisid():
            raise AuthError(
                message=f"В браузере {browser} нет входа в YouTube.",
                hint=self._hint(browser=browser),
            )
        return creds

    def _load_all(self) -> Credentials:
        if self._browser:
            return self._load_one(browser=self._browser)
        for browser in BROWSERS:
            try:
                return self._load_one(browser=browser)
            except AuthError:
                continue
        raise AuthError(
            message="Не удалось получить cookies ни из одного браузера.",
            hint=EXPORT_HINT,
        )

    async def load(self) -> Credentials:
        return await asyncio.to_thread(self._load_all)


class ChainCookieSource:
    def __init__(self, sources: Sequence[CookieSource]) -> None:
        self._sources = list(sources)

    async def load(self) -> Credentials:
        for source in self._sources:
            try:
                return await source.load()
            except AuthError:
                continue
        raise AuthError(
            message="Не удалось получить cookies ни из одного источника.",
            hint=EXPORT_HINT,
        )
