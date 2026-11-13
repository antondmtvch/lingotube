import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from lingotube.auth.base import LOGIN_HINT
from lingotube.auth.devtools import (
    BrowserCookie,
    DevToolsConnectionClosed,
    DevToolsError,
)
from lingotube.auth.login_browser import PROFILE_BUSY_HINT, PROFILE_BUSY_MESSAGE
from lingotube.auth.login_flow import (
    LOGIN_PAGE_URL,
    REFRESH_PAGE_URL,
    ROTATING_COOKIE,
    refresh_cookies_from_login_profile,
    sign_in_with_login_browser,
    youtube_cookies_only,
)
from lingotube.auth.login_store import LoginCookieStore, SavedLogin
from lingotube.config import LoginPaths
from lingotube.errors import AuthError, ProfileBusyError


def cookie(name: str, value: str = "LEAKME", domain: str = ".youtube.com"):
    return BrowserCookie(name=name, value=value, domain=domain)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeConnection:
    def __init__(self, cookie_polls, page_counts=None, on_cookies=None) -> None:
        self.commands: list[str] = []
        self._cookie_polls = list(cookie_polls)
        self._page_counts = list(page_counts or [])
        self._on_cookies = on_cookies

    async def send_command(self, method, params=None):
        self.commands.append(method)
        if method == "Storage.getCookies":
            if self._on_cookies:
                await self._on_cookies()
            polls = self._cookie_polls
            batch = polls.pop(0) if len(polls) > 1 else polls[0]
            return {
                "cookies": [
                    {"name": c.name, "value": c.value, "domain": c.domain}
                    for c in batch
                ]
            }
        if method == "Target.getTargets":
            counts = self._page_counts
            count = counts.pop(0) if len(counts) > 1 else (counts[0] if counts else 1)
            return {"targetInfos": [{"type": "page"}] * count}
        if method == "Browser.close":
            raise DevToolsConnectionClosed("closed")
        return {}


class FakeRunningBrowser:
    websocket_url = "ws://127.0.0.1:1/devtools/browser/x"

    def __init__(self) -> None:
        self.shut_down_connections: list = []

    @property
    def shut_down_calls(self) -> int:
        return len(self.shut_down_connections)

    async def shut_down(self, connection) -> None:
        self.shut_down_connections.append(connection)


class FakeSignInWindow:
    """Exits once the fake clock reaches `exits_at` (None: never)."""

    def __init__(self, clock: FakeClock, events: list[str], exits_at) -> None:
        self._clock = clock
        self._events = events
        self._exits_at = exits_at
        self.close_calls = 0

    @property
    def has_exited(self) -> bool:
        exited = self._exits_at is not None and self._clock.now >= self._exits_at
        if exited and "window exited" not in self._events:
            self._events.append("window exited")
        return exited

    async def close(self) -> None:
        self.close_calls += 1


class Harness:
    def __init__(
        self, connection: FakeConnection, window_exits_at: float | None = 3.0
    ) -> None:
        self.connection = connection
        self.running = FakeRunningBrowser()
        self.clock = FakeClock()
        self.events: list[str] = []
        self.window = FakeSignInWindow(self.clock, self.events, window_exits_at)
        self.window_launch_args: tuple = ()
        self.launch_args: tuple = ()

    async def launch_window(self, executable, profile_dir, login_url):
        self.window_launch_args = (executable, profile_dir, login_url)
        self.events.append("window launched")
        return self.window

    async def launch(self, executable, profile_dir, mode, start_url):
        self.launch_args = (executable, profile_dir, mode, start_url)
        self.events.append("headless launched")
        return self.running

    @asynccontextmanager
    async def connect(self, websocket_url):
        yield self.connection


@pytest.fixture
def paths(tmp_path: Path) -> LoginPaths:
    return LoginPaths(
        profile_dir=tmp_path / "profile", cookies_file=tmp_path / "cookies.json"
    )


@pytest.fixture
def store(paths: LoginPaths) -> LoginCookieStore:
    return LoginCookieStore(paths.cookies_file)


async def sign_in(harness: Harness, paths, store, notify=lambda message: None):
    return await sign_in_with_login_browser(
        browser="chrome",
        executable=Path("chrome"),
        paths=paths,
        store=store,
        notify=notify,
        launch_window=harness.launch_window,
        launch=harness.launch,
        connect=harness.connect,
        sleep=harness.clock.sleep,
        clock=harness.clock,
    )


SIGNED_IN = [cookie("SAPISID", "LEAKME-sapisid"), cookie("LOGIN_INFO", "LEAKME-info")]


def test_youtube_cookies_only_filters_domains():
    result = youtube_cookies_only(
        [
            cookie("A", "1"),
            cookie("B", "2", ".example.com"),
            cookie("C", "3", "google.com"),
        ]
    )
    assert result == {"A": "1", "C": "3"}


def test_youtube_cookies_win_over_google_cookies_with_the_same_name():
    google_first = [
        cookie("SIDCC", "google", "google.com"),
        cookie("SIDCC", "youtube", ".youtube.com"),
    ]
    youtube_first = list(reversed(google_first))
    assert youtube_cookies_only(google_first) == {"SIDCC": "youtube"}
    assert youtube_cookies_only(youtube_first) == {"SIDCC": "youtube"}


async def test_sign_in_opens_login_page_in_window_and_notifies_once(paths, store):
    harness = Harness(FakeConnection([SIGNED_IN]))
    messages: list[str] = []
    await sign_in(harness, paths, store, notify=messages.append)
    assert harness.window_launch_args == (
        Path("chrome"),
        paths.profile_dir,
        LOGIN_PAGE_URL,
    )
    assert messages == [
        "Войдите в YouTube в открывшемся окне и закройте окно браузера; "
        "жду до 10 минут."
    ]
    assert LOGIN_PAGE_URL.startswith("https://accounts.google.com/ServiceLogin")


async def test_cookies_are_read_by_headless_launch_after_window_exited(paths, store):
    harness = Harness(FakeConnection([SIGNED_IN]), window_exits_at=3.0)
    saved = await sign_in(harness, paths, store)
    assert harness.events == ["window launched", "window exited", "headless launched"]
    assert harness.launch_args == (
        Path("chrome"),
        paths.profile_dir,
        "headless",
        "about:blank",
    )
    assert harness.clock.now == 3.0
    assert saved.browser == "chrome"
    assert set(saved.cookies) == {"SAPISID", "LOGIN_INFO"}
    assert await store.read() == saved
    assert harness.running.shut_down_connections[0] is harness.connection
    assert "Target.createTarget" not in harness.connection.commands
    assert "Storage.clearCookies" not in harness.connection.commands


async def test_sign_in_accepts_secure_3papisid_alone(paths, store):
    harness = Harness(FakeConnection([[cookie("__Secure-3PAPISID", "LEAKME")]]))
    saved = await sign_in(harness, paths, store)
    assert "__Secure-3PAPISID" in saved.cookies


async def test_sign_in_drops_foreign_domain_cookies(paths, store):
    harness = Harness(
        FakeConnection([SIGNED_IN + [cookie("TRACKER", "LEAKME", ".example.com")]])
    )
    saved = await sign_in(harness, paths, store)
    assert "TRACKER" not in saved.cookies
    assert "TRACKER" not in (await store.read()).cookies


async def test_window_closed_without_sign_in_is_auth_error_and_nothing_written(
    paths, store
):
    harness = Harness(FakeConnection([[cookie("PREF", "LEAKME")]]), window_exits_at=1.0)
    with pytest.raises(AuthError) as caught:
        await sign_in(harness, paths, store)
    assert "закрыто" in caught.value.message
    assert caught.value.hint == "Повторите lingotube login и войдите в аккаунт."
    assert harness.clock.now == 1.0
    assert harness.running.shut_down_calls >= 1
    assert not paths.cookies_file.exists()


async def test_foreign_domain_sapisid_does_not_count_as_sign_in(paths, store):
    harness = Harness(FakeConnection([[cookie("SAPISID", "LEAKME", ".example.com")]]))
    with pytest.raises(AuthError):
        await sign_in(harness, paths, store)
    assert not paths.cookies_file.exists()


async def test_sign_in_timeout_terminates_own_window_and_skips_headless(paths, store):
    harness = Harness(FakeConnection([SIGNED_IN]), window_exits_at=None)
    with pytest.raises(AuthError) as caught:
        await sign_in(harness, paths, store)
    assert caught.value.message == "За 10 минут вход в YouTube не выполнен."
    assert caught.value.hint == "Повторите lingotube login."
    assert 600.0 <= harness.clock.now < 610.0
    assert harness.window.close_calls >= 1
    assert harness.launch_args == ()
    assert not paths.cookies_file.exists()


async def test_ctrl_c_while_waiting_terminates_own_window(paths, store):
    waiting = asyncio.Event()
    harness = Harness(FakeConnection([SIGNED_IN]), window_exits_at=None)

    async def sleep_forever(seconds):
        waiting.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(
        sign_in_with_login_browser(
            browser="chrome",
            executable=Path("chrome"),
            paths=paths,
            store=store,
            notify=lambda message: None,
            launch_window=harness.launch_window,
            launch=harness.launch,
            connect=harness.connect,
            sleep=sleep_forever,
            clock=harness.clock,
        )
    )
    await waiting.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert harness.window.close_calls >= 1
    assert harness.launch_args == ()


async def test_closing_the_window_ends_the_wait_within_seconds(paths, store):
    harness = Harness(FakeConnection([[]]), window_exits_at=2.0)
    with pytest.raises(AuthError):
        await sign_in(harness, paths, store)
    assert harness.clock.now < 10.0


async def test_headless_read_failure_is_auth_error_and_shuts_down(paths, store):
    class BrokenConnection(FakeConnection):
        async def send_command(self, method, params=None):
            if method == "Storage.getCookies":
                raise DevToolsError("LEAKME-detail")
            return await super().send_command(method, params)

    harness = Harness(BrokenConnection([[]]))
    with pytest.raises(AuthError) as caught:
        await sign_in(harness, paths, store)
    assert "LEAKME" not in str(caught.value)
    assert harness.running.shut_down_calls >= 1


async def test_sign_in_connect_failure_is_auth_error_and_shuts_down_without_connection(
    paths, store
):
    harness = Harness(FakeConnection([[]]))

    @asynccontextmanager
    async def failing_connect(websocket_url):
        raise DevToolsError("LEAKME-detail")
        yield

    harness.connect = failing_connect
    with pytest.raises(AuthError) as caught:
        await sign_in(harness, paths, store)
    assert caught.value.message == "Не удалось прочитать вход из профиля lingotube."
    assert "LEAKME" not in str(caught.value)
    assert harness.running.shut_down_connections[-1] is None
    assert not paths.cookies_file.exists()


async def test_sign_in_store_write_failure_is_auth_error_with_fixed_text(paths, store):
    harness = Harness(FakeConnection([SIGNED_IN]))

    async def failing_write(saved):
        raise OSError("disk LEAKME-path")

    store.write = failing_write
    with pytest.raises(AuthError) as caught:
        await sign_in(harness, paths, store)
    assert caught.value.message == "Не удалось сохранить вход lingotube."
    assert "LEAKME" not in (caught.value.hint or "")
    assert harness.running.shut_down_calls >= 1


async def refresh(harness: Harness, paths, store, find=lambda browser: Path("edge")):
    return await refresh_cookies_from_login_profile(
        paths=paths,
        store=store,
        find_executable=find,
        launch=harness.launch,
        connect=harness.connect,
        sleep=harness.clock.sleep,
        clock=harness.clock,
    )


async def test_refresh_saves_rotated_cookies(paths, store):
    await store.write(
        SavedLogin(browser="edge", cookies={ROTATING_COOKIE: "OLD-LEAKME"})
    )
    rotated_cookies = [cookie("SAPISID", "LEAKME-new"), cookie(ROTATING_COOKIE, "NEW")]
    harness = Harness(
        FakeConnection([[cookie(ROTATING_COOKIE, "OLD-LEAKME")], rotated_cookies])
    )
    result = await refresh(harness, paths, store)
    assert result.rotated is True
    assert result.saved.browser == "edge"
    assert (await store.read()).cookies[ROTATING_COOKIE] == "NEW"
    assert harness.launch_args[2:] == ("headless", REFRESH_PAGE_URL)
    assert harness.running.shut_down_calls >= 1


async def test_refresh_without_rotation_still_saves_and_reports(paths, store):
    await store.write(SavedLogin(browser="chrome", cookies={ROTATING_COOKIE: "SAME"}))
    unchanged = [cookie("SAPISID", "LEAKME-s"), cookie(ROTATING_COOKIE, "SAME")]
    harness = Harness(FakeConnection([unchanged]))
    result = await refresh(harness, paths, store)
    assert result.rotated is False
    assert harness.clock.now >= 15.0
    assert (await store.read()).cookies["SAPISID"] == "LEAKME-s"


async def test_refresh_waits_at_least_one_poll_before_deciding(paths, store):
    await store.write(SavedLogin(browser="chrome", cookies={"SAPISID": "old"}))
    cookies = [cookie("SAPISID", "LEAKME-s"), cookie(ROTATING_COOKIE, "EARLY")]
    harness = Harness(FakeConnection([cookies]))
    await refresh(harness, paths, store)
    assert harness.connection.commands.count("Storage.getCookies") >= 2
    assert harness.clock.now >= 1.0


async def test_refresh_store_write_failure_is_auth_error(paths, store):
    await store.write(SavedLogin(browser="chrome", cookies={}))
    cookies = [cookie("SAPISID", "LEAKME-s"), cookie(ROTATING_COOKIE, "NEW")]
    harness = Harness(FakeConnection([cookies]))

    async def failing_write(saved):
        raise OSError("disk LEAKME-path")

    store.write = failing_write
    with pytest.raises(AuthError) as caught:
        await refresh(harness, paths, store)
    assert caught.value.message == "Не удалось сохранить вход lingotube."


async def test_refresh_busy_profile_is_auth_error_with_close_window_hint(
    paths, store, monkeypatch
):
    await store.write(SavedLogin(browser="chrome", cookies={}))
    monkeypatch.setattr(
        "lingotube.auth.login_flow.is_login_profile_in_use", lambda profile_dir: True
    )
    harness = Harness(FakeConnection([[]]))
    with pytest.raises(AuthError) as caught:
        await refresh(harness, paths, store)
    assert caught.value.message == PROFILE_BUSY_MESSAGE
    assert caught.value.hint == PROFILE_BUSY_HINT
    assert harness.launch_args == ()


async def test_refresh_converts_profile_busy_error_from_launch(paths, store):
    await store.write(SavedLogin(browser="chrome", cookies={}))
    harness = Harness(FakeConnection([[]]))

    async def busy_launch(*args):
        raise ProfileBusyError(message="x", hint="y")

    with pytest.raises(AuthError) as caught:
        await refresh_cookies_from_login_profile(
            paths=paths,
            store=store,
            find_executable=lambda browser: Path("chrome"),
            launch=busy_launch,
            connect=harness.connect,
            sleep=harness.clock.sleep,
            clock=harness.clock,
        )
    assert type(caught.value) is AuthError
    assert caught.value.hint == PROFILE_BUSY_HINT


async def test_refresh_signed_out_profile_is_auth_error_with_login_hint(paths, store):
    await store.write(SavedLogin(browser="chrome", cookies={}))
    harness = Harness(FakeConnection([[cookie("PREF", "LEAKME")]]))
    with pytest.raises(AuthError) as caught:
        await refresh(harness, paths, store)
    assert caught.value.hint == LOGIN_HINT
    assert harness.running.shut_down_calls >= 1


async def test_refresh_devtools_failure_is_auth_error_with_login_hint(paths, store):
    await store.write(SavedLogin(browser="chrome", cookies={}))

    class BrokenConnection(FakeConnection):
        async def send_command(self, method, params=None):
            if method == "Storage.getCookies":
                raise DevToolsConnectionClosed("LEAKME-detail")
            return await super().send_command(method, params)

    harness = Harness(BrokenConnection([[]]))
    with pytest.raises(AuthError) as caught:
        await refresh(harness, paths, store)
    assert caught.value.message == "Не удалось обновить вход в профиле lingotube."
    assert caught.value.hint == LOGIN_HINT
    assert "LEAKME" not in str(caught.value)
    assert harness.running.shut_down_calls >= 1


async def test_refresh_without_browser_is_auth_error(paths, store):
    await store.write(SavedLogin(browser="chrome", cookies={}))
    harness = Harness(FakeConnection([[]]))
    with pytest.raises(AuthError) as caught:
        await refresh(harness, paths, store, find=lambda browser: None)
    assert caught.value.hint == LOGIN_HINT


async def test_no_cookie_value_in_any_error_message(paths, store):
    await store.write(SavedLogin(browser="chrome", cookies={"X": "LEAKME-saved"}))
    signed_out = [cookie("PREF", "LEAKME-pref")]
    refresh_harness = Harness(FakeConnection([signed_out]))
    with pytest.raises(AuthError) as refresh_error:
        await refresh(refresh_harness, paths, store)
    closed_harness = Harness(FakeConnection([signed_out]))
    with pytest.raises(AuthError) as closed_error:
        await sign_in(closed_harness, paths, store)
    timeout_harness = Harness(FakeConnection([signed_out]), window_exits_at=None)
    with pytest.raises(AuthError) as timeout_error:
        await sign_in(timeout_harness, paths, store)
    for error in (refresh_error.value, closed_error.value, timeout_error.value):
        assert "LEAKME" not in str(error)
        assert "LEAKME" not in error.hint
