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
_WIN_HINT = "Chrome and Edge on Windows usually cannot be read directly. " + EXPORT_HINT


def default_loader(browser: str) -> Mapping[str, str]:
    """Read YouTube and Google cookies from a browser with browser-cookie3.

    The package is imported only when a browser is actually read.

    Args:
        browser: Browser name, one of BROWSERS.

    Returns:
        Cookie names mapped to values, for the allowed domains only.
    """
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
    """Load cookies from one browser, or from the first browser with a YouTube sign-in."""

    def __init__(
        self,
        browser: str | None = None,
        loader: Callable[[str], Mapping[str, str]] | None = None,
        platform: str = sys.platform,
    ) -> None:
        """Create the source.

        Args:
            browser: Browser to read, or None to try each known browser in turn.
            loader: Function that reads the cookies of a browser. Defaults to default_loader.
            platform: Platform name. On Windows the hint text is different.

        Raises:
            ValueError: If browser is not one of the known browsers.
        """
        if browser is not None and browser not in BROWSERS:
            raise ValueError(f"unknown browser: {browser}")
        self._browser = browser
        self._loader = loader or default_loader
        self._platform = platform

    def _hint(self, browser: str) -> str:
        if self._platform == "win32" and browser in ("chrome", "edge"):
            return _WIN_HINT
        return EXPORT_HINT

    def _load_one(self, browser: str) -> Credentials:
        try:
            cookies = self._loader(browser)
        except Exception:  # never propagate text: may contain paths or values
            raise AuthError(
                message=f"Could not read the cookies from the {browser} browser.",
                hint=self._hint(browser=browser),
            ) from None
        creds = Credentials(cookies=cookies)
        if not creds.sapisid():
            raise AuthError(
                message=f"The {browser} browser has no sign-in to YouTube.",
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
            message="Could not get the cookies from any browser.",
            hint=_WIN_HINT if self._platform == "win32" else EXPORT_HINT,
        )

    async def load(self) -> Credentials:
        """Load the credentials from the browser, in a worker thread.

        Returns:
            The loaded credentials.

        Raises:
            AuthError: If the browser cannot be read or has no YouTube sign-in.
        """
        return await asyncio.to_thread(self._load_all)


class ChainCookieSource:
    """Try several cookie sources in order and use the first one that works."""

    def __init__(self, sources: Sequence[CookieSource]) -> None:
        """Create the chain.

        Args:
            sources: Sources to try, in order.
        """
        self._sources = list(sources)

    async def load(self) -> Credentials:
        """Return the credentials of the first source that succeeds.

        Returns:
            The credentials of the first working source.

        Raises:
            AuthError: If every source fails. The hint comes from the last failing source.
        """
        hint = EXPORT_HINT
        for source in self._sources:
            try:
                return await source.load()
            except AuthError as e:
                hint = e.hint or hint  # keep the last source's own hint (e.g. the Windows one)
        raise AuthError(
            message="Could not get the cookies from any source.",
            hint=hint,
        )
