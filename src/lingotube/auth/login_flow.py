"""Sign-in and cookie refresh in the lingotube-owned login browser profile.

Cookie values stay in memory and are never put into exception messages.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path

from lingotube.auth.base import LOGIN_HINT, is_allowed_domain
from lingotube.auth.devtools import (
    BrowserCookie,
    DevToolsConnection,
    DevToolsError,
    connect_to_browser_devtools,
    read_all_cookies,
)
from lingotube.auth.login_browser import (
    PROFILE_BUSY_HINT,
    PROFILE_BUSY_MESSAGE,
    LaunchMode,
    RunningLoginBrowser,
    SignInWindow,
    find_browser_executable,
    is_login_profile_in_use,
    launch_login_browser,
    launch_sign_in_window,
)
from lingotube.auth.login_store import LoginCookieStore, SavedLogin
from lingotube.config import LoginPaths
from lingotube.errors import AuthError, ProfileBusyError

type LaunchSignInWindow = Callable[[Path, Path, str], Awaitable[SignInWindow]]
type LaunchLoginBrowser = Callable[
    [Path, Path, LaunchMode, str], Awaitable[RunningLoginBrowser]
]
type ConnectToBrowser = Callable[[str], AbstractAsyncContextManager[DevToolsConnection]]
type Sleep = Callable[[float], Awaitable[None]]
type Clock = Callable[[], float]
type ReadFromConnection = Callable[[DevToolsConnection], Awaitable[list[BrowserCookie]]]

LOGIN_PAGE_URL = (
    "https://accounts.google.com/ServiceLogin"
    "?service=youtube&continue=https://www.youtube.com/"
)
REFRESH_PAGE_URL = "https://www.youtube.com/"
LOGIN_WAIT_SECONDS = 600.0
WINDOW_POLL_SECONDS = 1.0
REFRESH_WAIT_SECONDS = 15.0
REFRESH_POLL_SECONDS = 1.0
ROTATING_COOKIE = "__Secure-1PSIDTS"

_SAPISID_COOKIE_NAMES = ("SAPISID", "__Secure-3PAPISID")


def youtube_cookies_only(cookies: Iterable[BrowserCookie]) -> dict[str, str]:
    """Name -> value of the cookies on youtube.com/google.com domains only.

    Same-named cookies on both sites are merged with youtube.com winning, whatever
    the order the browser returned them in.
    """
    allowed = [cookie for cookie in cookies if is_allowed_domain(cookie.domain)]
    ordered = sorted(allowed, key=lambda cookie: _is_youtube_domain(cookie.domain))
    return {cookie.name: cookie.value for cookie in ordered}


def _has_sapisid(cookies: Iterable[BrowserCookie]) -> bool:
    return any(
        cookie.name in _SAPISID_COOKIE_NAMES and is_allowed_domain(cookie.domain)
        for cookie in cookies
    )


def _is_youtube_domain(domain: str) -> bool:
    bare = domain.lower().lstrip(".")
    return bare == "youtube.com" or bare.endswith(".youtube.com")


def _login_window_closed_error() -> AuthError:
    return AuthError(
        message="Окно входа закрыто до входа в YouTube.",
        hint="Повторите lingotube login и войдите в аккаунт.",
    )


def _profile_busy_auth_error() -> AuthError:
    return AuthError(message=PROFILE_BUSY_MESSAGE, hint=PROFILE_BUSY_HINT)


async def _save_login(store: LoginCookieStore, saved: SavedLogin) -> None:
    try:
        await store.write(saved)
    except OSError:
        # No exception text: it may contain paths.
        raise AuthError(
            message="Не удалось сохранить вход lingotube.",
            hint="Проверьте место на диске и права на папку, затем повторите lingotube login.",
        ) from None


async def sign_in_with_login_browser(
    browser: str,
    executable: Path,
    paths: LoginPaths,
    store: LoginCookieStore,
    notify: Callable[[str], None],
    launch_window: LaunchSignInWindow = launch_sign_in_window,
    launch: LaunchLoginBrowser = launch_login_browser,
    connect: ConnectToBrowser = connect_to_browser_devtools,
    sleep: Sleep = asyncio.sleep,
    clock: Clock = time.monotonic,
) -> SavedLogin:
    """Open a sign-in window without a debugging port, wait until the person closes
    it, then read the cookies of the login profile in a headless launch."""
    window = await launch_window(executable, paths.profile_dir, LOGIN_PAGE_URL)
    try:
        notify(
            "Войдите в YouTube в открывшемся окне и закройте окно браузера; "
            "жду до 10 минут."
        )
        await wait_for_sign_in_window_to_close(window=window, sleep=sleep, clock=clock)
    finally:
        # Ctrl+C or a timeout: close our own window; no-op once it has exited.
        await window.close()
    try:
        cookies = await read_cookies_from_login_profile(
            executable=executable,
            profile_dir=paths.profile_dir,
            mode="headless",
            start_url="about:blank",
            read_from_connection=read_all_cookies,
            launch=launch,
            connect=connect,
        )
    except DevToolsError:
        raise AuthError(
            message="Не удалось прочитать вход из профиля lingotube.",
            hint="Повторите lingotube login.",
        ) from None
    if not _has_sapisid(cookies):
        raise _login_window_closed_error()
    saved = SavedLogin(browser=browser, cookies=youtube_cookies_only(cookies))
    await _save_login(store, saved)
    return saved


async def wait_for_sign_in_window_to_close(
    window: SignInWindow, sleep: Sleep, clock: Clock
) -> None:
    """Poll our own window process until it exits; AuthError after LOGIN_WAIT_SECONDS."""
    deadline = clock() + LOGIN_WAIT_SECONDS
    while not window.has_exited:
        if clock() >= deadline:
            raise AuthError(
                message="За 10 минут вход в YouTube не выполнен.",
                hint="Повторите lingotube login.",
            )
        await sleep(WINDOW_POLL_SECONDS)


async def read_cookies_from_login_profile(
    executable: Path,
    profile_dir: Path,
    mode: LaunchMode,
    start_url: str,
    read_from_connection: ReadFromConnection,
    launch: LaunchLoginBrowser = launch_login_browser,
    connect: ConnectToBrowser = connect_to_browser_devtools,
) -> list[BrowserCookie]:
    """Start the login profile with a debugging port, read cookies, shut it down.

    `read_from_connection` is an async callable taking the DevTools connection and
    returning the cookies. The browser started here never outlives this call.
    """
    running = await launch(executable, profile_dir, mode, start_url)
    connection: DevToolsConnection | None = None
    try:
        async with connect(running.websocket_url) as connection:
            try:
                return await read_from_connection(connection)
            finally:
                await running.shut_down(connection)
    finally:
        # Load-bearing: a second Ctrl+C aborts the inner shut_down above; this one
        # completes the close (shut_down is a no-op once the process has exited).
        await running.shut_down(connection)


@dataclass(frozen=True)
class RefreshResult:
    saved: SavedLogin
    rotated: bool


async def refresh_cookies_from_login_profile(
    paths: LoginPaths,
    store: LoginCookieStore,
    mode: LaunchMode = "headless",
    find_executable: Callable[[str], Path | None] = find_browser_executable,
    launch: LaunchLoginBrowser = launch_login_browser,
    connect: ConnectToBrowser = connect_to_browser_devtools,
    sleep: Sleep = asyncio.sleep,
    clock: Clock = time.monotonic,
) -> RefreshResult:
    """Start the login profile briefly so the browser rotates cookies, then save them."""
    saved = await store.read()
    executable = find_executable(saved.browser)
    if executable is None:
        raise AuthError(
            message="Браузер для обновления входа не найден.", hint=LOGIN_HINT
        )
    if is_login_profile_in_use(paths.profile_dir):
        raise _profile_busy_auth_error()
    previous_value = saved.cookies.get(ROTATING_COOKIE)

    async def wait_for_rotation(connection: DevToolsConnection) -> list[BrowserCookie]:
        return await _wait_for_rotated_cookie(
            connection=connection,
            previous_value=previous_value,
            sleep=sleep,
            clock=clock,
        )

    try:
        cookies = await read_cookies_from_login_profile(
            executable=executable,
            profile_dir=paths.profile_dir,
            mode=mode,
            start_url=REFRESH_PAGE_URL,
            read_from_connection=wait_for_rotation,
            launch=launch,
            connect=connect,
        )
    except ProfileBusyError:
        raise _profile_busy_auth_error() from None
    except DevToolsError:
        raise AuthError(
            message="Не удалось обновить вход в профиле lingotube.", hint=LOGIN_HINT
        ) from None
    if not _has_sapisid(cookies):
        raise AuthError(
            message="Вход в профиле lingotube больше не действует.", hint=LOGIN_HINT
        )
    refreshed = SavedLogin(browser=saved.browser, cookies=youtube_cookies_only(cookies))
    await _save_login(store, refreshed)
    new_rotating_value = refreshed.cookies.get(ROTATING_COOKIE)
    rotated = new_rotating_value is not None and new_rotating_value != previous_value
    return RefreshResult(saved=refreshed, rotated=rotated)


async def _wait_for_rotated_cookie(
    connection: DevToolsConnection,
    previous_value: str | None,
    sleep: Sleep,
    clock: Clock,
) -> list[BrowserCookie]:
    """Poll until the rotating cookie changes or the wait runs out; return the last read."""
    deadline = clock() + REFRESH_WAIT_SECONDS
    is_first_poll = True
    while True:
        cookies = await read_all_cookies(connection)
        current = youtube_cookies_only(cookies).get(ROTATING_COOKIE)
        # The first poll may run before the page loaded, so it never decides alone.
        has_rotated = current is not None and current != previous_value
        if (has_rotated and not is_first_poll) or clock() >= deadline:
            return cookies
        is_first_poll = False
        await sleep(REFRESH_POLL_SECONDS)
