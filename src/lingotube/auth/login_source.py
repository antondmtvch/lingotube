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
    """The cookies saved by ``lingotube login`` as a cookie source."""

    def __init__(
        self,
        store: LoginCookieStore,
        paths: LoginPaths,
        refresh: Callable[..., Awaitable[RefreshResult]] = refresh_cookies_from_login_profile,
    ) -> None:
        """Create the source.

        Args:
            store: Store of the saved sign-in.
            paths: Locations of the login profile.
            refresh: Function that refreshes the saved cookies from the login profile.
        """
        self._store = store
        self._paths = paths
        self._refresh = refresh

    async def load(self) -> Credentials:
        """Return the saved credentials.

        Returns:
            The credentials of the saved sign-in.

        Raises:
            AuthError: If the saved sign-in has no SAPISID cookie.
        """
        saved = await self._store.read()
        credentials = Credentials(cookies=saved.cookies)
        if not credentials.sapisid():
            raise AuthError(
                message="The saved lingotube sign-in has no SAPISID (no sign-in to YouTube found).",
                hint=LOGIN_HINT,
            )
        return credentials

    async def refresh_from_profile(self) -> None:
        """Let the login profile's browser rotate cookies and save the fresh ones."""
        await self._refresh(
            paths=self._paths,
            store=self._store,
        )
