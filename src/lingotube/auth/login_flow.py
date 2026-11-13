"""Sign-in and cookie refresh in the lingotube-owned login browser profile.

Cookie values stay in memory and are never put into exception messages.
"""

import asyncio
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from lingotube.auth.base import LOGIN_HINT, is_allowed_domain
from lingotube.auth.devtools import (
    BrowserCookie,
    DevToolsConnectionClosed,
    DevToolsError,
    clear_all_cookies,
    connect_to_browser_devtools,
    count_open_pages,
    open_page,
    read_all_cookies,
)
from lingotube.auth.login_browser import (
    PROFILE_BUSY_HINT,
    LaunchMode,
    find_browser_executable,
    is_login_profile_in_use,
    launch_login_browser,
)
from lingotube.auth.login_store import LoginCookieStore, SavedLogin
from lingotube.config import LoginPaths
from lingotube.errors import AuthError, ProfileBusyError

LOGIN_PAGE_URL = (
    "https://accounts.google.com/ServiceLogin"
    "?service=youtube&continue=https://www.youtube.com/"
)
REFRESH_PAGE_URL = "https://www.youtube.com/"
LOGIN_WAIT_SECONDS = 600.0
LOGIN_POLL_SECONDS = 2.0
LOGIN_INFO_GRACE_SECONDS = 15.0
REFRESH_WAIT_SECONDS = 15.0
REFRESH_POLL_SECONDS = 1.0
ROTATING_COOKIE = "__Secure-1PSIDTS"

_SAPISID_COOKIE_NAMES = ("SAPISID", "__Secure-3PAPISID")
_LOGIN_INFO_COOKIE = "LOGIN_INFO"


def youtube_cookies_only(cookies: Iterable[BrowserCookie]) -> dict[str, str]:
    """Name -> value of the cookies on youtube.com/google.com domains only."""
    return {
        cookie.name: cookie.value
        for cookie in cookies
        if is_allowed_domain(cookie.domain)
    }


def _has_sapisid(cookies: Iterable[BrowserCookie]) -> bool:
    return any(
        cookie.name in _SAPISID_COOKIE_NAMES and is_allowed_domain(cookie.domain)
        for cookie in cookies
    )


def _is_youtube_domain(domain: str) -> bool:
    bare = domain.lower().lstrip(".")
    return bare == "youtube.com" or bare.endswith(".youtube.com")


def _has_login_info(cookies: Iterable[BrowserCookie]) -> bool:
    return any(
        cookie.name == _LOGIN_INFO_COOKIE and _is_youtube_domain(cookie.domain)
        for cookie in cookies
    )


def _login_window_closed_error() -> AuthError:
    return AuthError(
        message="Окно входа закрыто до входа в YouTube.",
        hint="Повторите lingotube login и войдите в аккаунт.",
    )


def _profile_busy_error() -> AuthError:
    return AuthError(
        message="Профиль входа lingotube сейчас открыт.", hint=PROFILE_BUSY_HINT
    )


async def sign_in_with_login_browser(
    browser: str,
    executable: Path,
    paths: LoginPaths,
    store: LoginCookieStore,
    notify: Callable[[str], None],
    launch=launch_login_browser,
    connect=connect_to_browser_devtools,
    sleep=asyncio.sleep,
    clock=time.monotonic,
) -> SavedLogin:
    """Open a login window, wait for the person to sign in, save the cookies."""
    running = await launch(executable, paths.profile_dir, "window", "about:blank")
    connection = None
    try:
        async with connect(running.websocket_url) as connection:
            try:
                await clear_all_cookies(connection)
                await open_page(connection, LOGIN_PAGE_URL)
                notify("Откройте окно браузера и войдите в YouTube; жду до 10 минут.")
                cookies = await _wait_for_sign_in(
                    connection=connection, sleep=sleep, clock=clock
                )
            finally:
                await running.shut_down(connection)
        saved = SavedLogin(browser=browser, cookies=youtube_cookies_only(cookies))
        await store.write(saved)
        return saved
    except DevToolsConnectionClosed:
        raise _login_window_closed_error() from None
    except DevToolsError:
        raise AuthError(
            message="Не удалось связаться с окном входа.",
            hint="Повторите lingotube login.",
        ) from None
    finally:
        await running.shut_down(connection)


async def _wait_for_sign_in(connection, sleep, clock) -> list[BrowserCookie]:
    deadline = clock() + LOGIN_WAIT_SECONDS
    sapisid_seen_at: float | None = None
    while True:
        if await count_open_pages(connection) == 0:
            raise _login_window_closed_error()
        cookies = await read_all_cookies(connection)
        if _has_sapisid(cookies):
            if sapisid_seen_at is None:
                sapisid_seen_at = clock()
            if (
                _has_login_info(cookies)
                or clock() - sapisid_seen_at >= LOGIN_INFO_GRACE_SECONDS
            ):
                return cookies
        if clock() >= deadline:
            raise AuthError(
                message="За 10 минут вход в YouTube не выполнен.",
                hint="Повторите lingotube login.",
            )
        await sleep(LOGIN_POLL_SECONDS)


@dataclass(frozen=True)
class RefreshResult:
    saved: SavedLogin
    rotated: bool


async def refresh_cookies_from_login_profile(
    paths: LoginPaths,
    store: LoginCookieStore,
    mode: LaunchMode = "headless",
    find_executable=find_browser_executable,
    launch=launch_login_browser,
    connect=connect_to_browser_devtools,
    sleep=asyncio.sleep,
    clock=time.monotonic,
) -> RefreshResult:
    """Start the login profile briefly so the browser rotates cookies, then save them."""
    saved = await store.read()
    executable = find_executable(saved.browser)
    if executable is None:
        raise AuthError(
            message="Браузер для обновления входа не найден.", hint=LOGIN_HINT
        )
    if is_login_profile_in_use(paths.profile_dir):
        raise _profile_busy_error()
    try:
        running = await launch(executable, paths.profile_dir, mode, REFRESH_PAGE_URL)
    except ProfileBusyError:
        raise _profile_busy_error() from None
    connection = None
    try:
        async with connect(running.websocket_url) as connection:
            try:
                cookies = await _wait_for_rotated_cookie(
                    connection=connection,
                    previous_value=saved.cookies.get(ROTATING_COOKIE),
                    sleep=sleep,
                    clock=clock,
                )
            finally:
                await running.shut_down(connection)
        if not _has_sapisid(cookies):
            raise AuthError(
                message="Вход в профиле lingotube больше не действует.",
                hint=LOGIN_HINT,
            )
        refreshed = SavedLogin(
            browser=saved.browser, cookies=youtube_cookies_only(cookies)
        )
        await store.write(refreshed)
        new_rotating_value = refreshed.cookies.get(ROTATING_COOKIE)
        rotated = (
            new_rotating_value is not None
            and new_rotating_value != saved.cookies.get(ROTATING_COOKIE)
        )
        return RefreshResult(saved=refreshed, rotated=rotated)
    except DevToolsError:
        raise AuthError(
            message="Не удалось обновить вход в профиле lingotube.", hint=LOGIN_HINT
        ) from None
    finally:
        await running.shut_down(connection)


async def _wait_for_rotated_cookie(
    connection, previous_value: str | None, sleep, clock
) -> list[BrowserCookie]:
    """Poll until the rotating cookie changes or the wait runs out; return the last read."""
    deadline = clock() + REFRESH_WAIT_SECONDS
    while True:
        cookies = await read_all_cookies(connection)
        current = youtube_cookies_only(cookies).get(ROTATING_COOKIE)
        if (current is not None and current != previous_value) or clock() >= deadline:
            return cookies
        await sleep(REFRESH_POLL_SECONDS)
