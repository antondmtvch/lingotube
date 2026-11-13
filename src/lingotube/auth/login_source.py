"""The lingotube login profile as a cookie source: cookies saved by `lingotube login`."""

from collections.abc import Awaitable, Callable

from lingotube.auth.base import LOGIN_HINT, Credentials
from lingotube.auth.login_flow import (
    RefreshResult,
    refresh_cookies_from_login_profile,
)
from lingotube.auth.login_store import LoginCookieStore
from lingotube.config import LoginPaths
from lingotube.errors import AuthError


class LoginProfileCookieSource:
    def __init__(
        self,
        store: LoginCookieStore,
        paths: LoginPaths,
        refresh: Callable[
            ..., Awaitable[RefreshResult]
        ] = refresh_cookies_from_login_profile,
    ) -> None:
        self._store = store
        self._paths = paths
        self._refresh = refresh

    async def load(self) -> Credentials:
        saved = await self._store.read()
        credentials = Credentials(cookies=saved.cookies)
        if not credentials.sapisid():
            raise AuthError(
                message="В сохранённом входе lingotube нет SAPISID (вход в YouTube не найден).",
                hint=LOGIN_HINT,
            )
        return credentials

    async def refresh_from_profile(self) -> None:
        """Let the login profile's browser rotate cookies and save the fresh ones."""
        await self._refresh(
            paths=self._paths,
            store=self._store,
        )
