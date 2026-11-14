"""Tests of the sign-in and the cookie refresh in the login profile."""

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
    """Build a browser cookie for the tests.

    Args:
        name: Cookie name.
        value: Cookie value.
        domain: Cookie domain.

    Returns:
        The cookie.
    """
    return BrowserCookie(name=name, value=value, domain=domain)


class FakeClock:
    """Fake clock whose sleep advances the time without waiting."""

    def __init__(self) -> None:
        """Start the fake clock at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the fake current time.

        Returns:
            The fake time in seconds.
        """
        return self.now

    async def sleep(self, seconds: float) -> None:
        """Advance the fake time by the given number of seconds.

        Args:
            seconds: Seconds to advance.
        """
        self.now += seconds


class FakeConnection:
    """Fake DevTools connection that returns scripted cookies and page counts."""

    def __init__(self, cookie_polls, page_counts=None, on_cookies=None) -> None:
        """Create the fake connection with its scripted replies.

        Args:
            cookie_polls: Cookie batches returned on each cookie request, in order.
            page_counts: Page counts returned on each target request, in order.
            on_cookies: Optional coroutine function called on each cookie request.
        """
        self.commands: list[str] = []
        self._cookie_polls = list(cookie_polls)
        self._page_counts = list(page_counts or [])
        self._on_cookies = on_cookies

    async def send_command(self, method, params=None):
        """Record a command and return its scripted reply.

        Args:
            method: DevTools method name.
            params: Parameters of the command, or None.

        Returns:
            The scripted reply for the method.
        """
        self.commands.append(method)
        if method == "Storage.getCookies":
            if self._on_cookies:
                await self._on_cookies()
            polls = self._cookie_polls
            batch = polls.pop(0) if len(polls) > 1 else polls[0]
            return {"cookies": [{"name": c.name, "value": c.value, "domain": c.domain} for c in batch]}
        if method == "Target.getTargets":
            counts = self._page_counts
            count = counts.pop(0) if len(counts) > 1 else (counts[0] if counts else 1)
            return {"targetInfos": [{"type": "page"}] * count}
        if method == "Browser.close":
            raise DevToolsConnectionClosed("closed")
        return {}


class FakeRunningBrowser:
    """Fake browser started by the login flow that records its shut-down calls."""

    websocket_url = "ws://127.0.0.1:1/devtools/browser/x"

    def __init__(self) -> None:
        """Create the fake browser with no shut-down calls yet."""
        self.shut_down_connections: list = []

    @property
    def shut_down_calls(self) -> int:
        """Return how many times the browser was shut down.

        Returns:
            The number of shut-down calls.
        """
        return len(self.shut_down_connections)

    async def shut_down(self, connection) -> None:
        """Record a shut-down call.

        Args:
            connection: DevTools connection passed to the shut-down, or None.
        """
        self.shut_down_connections.append(connection)


class FakeSignInWindow:
    """Exits once the fake clock reaches `exits_at` (None: never)."""

    def __init__(self, clock: FakeClock, events: list[str], exits_at) -> None:
        """Create the fake sign-in window.

        Args:
            clock: Fake clock that decides when the window exits.
            events: Shared list where the window records its exit.
            exits_at: Fake time at which the window exits, or None if it never does.
        """
        self._clock = clock
        self._events = events
        self._exits_at = exits_at
        self.close_calls = 0

    @property
    def has_exited(self) -> bool:
        """Return True once the fake time has reached the exit time.

        Returns:
            True if the window has exited.
        """
        exited = self._exits_at is not None and self._clock.now >= self._exits_at
        if exited and "window exited" not in self._events:
            self._events.append("window exited")
        return exited

    async def close(self) -> None:
        """Record a close request."""
        self.close_calls += 1


class Harness:
    """Test harness that provides fake windows, browsers and connections."""

    def __init__(self, connection: FakeConnection, window_exits_at: float | None = 3.0) -> None:
        """Create the harness.

        Args:
            connection: Fake DevTools connection that the harness hands out.
            window_exits_at: Fake time at which the sign-in window exits, or None.
        """
        self.connection = connection
        self.running = FakeRunningBrowser()
        self.clock = FakeClock()
        self.events: list[str] = []
        self.window = FakeSignInWindow(self.clock, self.events, window_exits_at)
        self.window_launch_args: tuple = ()
        self.launch_args: tuple = ()

    async def launch_window(self, executable, profile_dir, login_url):
        """Record a sign-in window launch and return the fake window.

        Args:
            executable: Browser executable.
            profile_dir: Login profile folder.
            login_url: Sign-in page.

        Returns:
            The fake sign-in window.
        """
        self.window_launch_args = (executable, profile_dir, login_url)
        self.events.append("window launched")
        return self.window

    async def launch(self, executable, profile_dir, mode, start_url):
        """Record a headless launch and return the fake browser.

        Args:
            executable: Browser executable.
            profile_dir: Login profile folder.
            mode: Launch mode.
            start_url: Page to open first.

        Returns:
            The fake browser.
        """
        self.launch_args = (executable, profile_dir, mode, start_url)
        self.events.append("headless launched")
        return self.running

    @asynccontextmanager
    async def connect(self, websocket_url):
        """Open the fake DevTools connection.

        Args:
            websocket_url: DevTools URL, not checked here.

        Yields:
            The fake connection.
        """
        yield self.connection


@pytest.fixture
def paths(tmp_path: Path) -> LoginPaths:
    """Provide the login paths inside a temporary folder.

    Args:
        tmp_path: Temporary folder of the test.

    Returns:
        The login paths.
    """
    return LoginPaths(profile_dir=tmp_path / "profile", cookies_file=tmp_path / "cookies.json")


@pytest.fixture
def store(paths: LoginPaths) -> LoginCookieStore:
    """Provide a cookie store for the login paths.

    Args:
        paths: Login paths of the test.

    Returns:
        The cookie store.
    """
    return LoginCookieStore(paths.cookies_file)


async def sign_in(harness: Harness, paths, store, notify=lambda message: None):
    """Run the sign-in with the fakes of the harness.

    Args:
        harness: Test harness.
        paths: Login paths.
        store: Cookie store.
        notify: Function that receives the messages for the person.

    Returns:
        The saved sign-in.
    """
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
    """Check that only the YouTube and Google cookies are kept."""
    result = youtube_cookies_only(
        [
            cookie("A", "1"),
            cookie("B", "2", ".example.com"),
            cookie("C", "3", "google.com"),
        ]
    )
    assert result == {"A": "1", "C": "3"}


def test_youtube_cookies_win_over_google_cookies_with_the_same_name():
    """Check that a youtube.com cookie wins over a Google cookie with the same name."""
    google_first = [
        cookie("SIDCC", "google", "google.com"),
        cookie("SIDCC", "youtube", ".youtube.com"),
    ]
    youtube_first = list(reversed(google_first))
    assert youtube_cookies_only(google_first) == {"SIDCC": "youtube"}
    assert youtube_cookies_only(youtube_first) == {"SIDCC": "youtube"}


async def test_sign_in_opens_login_page_in_window_and_notifies_once(paths, store):
    """Check that the sign-in opens the login page and notifies the person once."""
    harness = Harness(FakeConnection([SIGNED_IN]))
    messages: list[str] = []
    await sign_in(harness, paths, store, notify=messages.append)
    assert harness.window_launch_args == (
        Path("chrome"),
        paths.profile_dir,
        LOGIN_PAGE_URL,
    )
    assert messages == [
        "Sign in to YouTube in the window that opens and close the browser window; waiting up to 10 minutes."
    ]
    assert LOGIN_PAGE_URL.startswith("https://accounts.google.com/ServiceLogin")


async def test_cookies_are_read_by_headless_launch_after_window_exited(paths, store):
    """Check that the cookies are read by a headless launch after the window exits."""
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
    """Check that the __Secure-3PAPISID cookie alone counts as a sign-in."""
    harness = Harness(FakeConnection([[cookie("__Secure-3PAPISID", "LEAKME")]]))
    saved = await sign_in(harness, paths, store)
    assert "__Secure-3PAPISID" in saved.cookies


async def test_sign_in_drops_foreign_domain_cookies(paths, store):
    """Check that cookies from other domains are dropped after the sign-in."""
    harness = Harness(FakeConnection([SIGNED_IN + [cookie("TRACKER", "LEAKME", ".example.com")]]))
    saved = await sign_in(harness, paths, store)
    assert "TRACKER" not in saved.cookies
    assert "TRACKER" not in (await store.read()).cookies


async def test_window_closed_without_sign_in_is_auth_error_and_nothing_written(paths, store):
    """Check that closing the window without signing in raises AuthError and writes nothing."""
    harness = Harness(FakeConnection([[cookie("PREF", "LEAKME")]]), window_exits_at=1.0)
    with pytest.raises(AuthError) as caught:
        await sign_in(harness, paths, store)
    assert "was closed" in caught.value.message
    assert caught.value.hint == "Run lingotube login again and sign in to the account."
    assert harness.clock.now == 1.0
    assert harness.running.shut_down_calls >= 1
    assert not paths.cookies_file.exists()


async def test_foreign_domain_sapisid_does_not_count_as_sign_in(paths, store):
    """Check that a SAPISID cookie from another domain does not count as a sign-in."""
    harness = Harness(FakeConnection([[cookie("SAPISID", "LEAKME", ".example.com")]]))
    with pytest.raises(AuthError):
        await sign_in(harness, paths, store)
    assert not paths.cookies_file.exists()


async def test_sign_in_timeout_terminates_own_window_and_skips_headless(paths, store):
    """Check that a sign-in timeout stops the own window and skips the headless read."""
    harness = Harness(FakeConnection([SIGNED_IN]), window_exits_at=None)
    with pytest.raises(AuthError) as caught:
        await sign_in(harness, paths, store)
    assert caught.value.message == "The sign-in to YouTube was not completed within 10 minutes."
    assert caught.value.hint == "Run lingotube login again."
    assert 600.0 <= harness.clock.now < 610.0
    assert harness.window.close_calls >= 1
    assert harness.launch_args == ()
    assert not paths.cookies_file.exists()


async def test_ctrl_c_while_waiting_terminates_own_window(paths, store):
    """Check that an interrupt while waiting closes the own window."""
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
    """Check that closing the window ends the wait within a few seconds."""
    harness = Harness(FakeConnection([[]]), window_exits_at=2.0)
    with pytest.raises(AuthError):
        await sign_in(harness, paths, store)
    assert harness.clock.now < 10.0


async def test_headless_read_failure_is_auth_error_and_shuts_down(paths, store):
    """Check that a failing headless read raises AuthError and shuts the browser down."""

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


async def test_sign_in_connect_failure_is_auth_error_and_shuts_down_without_connection(paths, store):
    """Check that a failed connection raises AuthError and shuts the browser down without a connection."""
    harness = Harness(FakeConnection([[]]))

    @asynccontextmanager
    async def failing_connect(websocket_url):
        raise DevToolsError("LEAKME-detail")
        yield

    harness.connect = failing_connect
    with pytest.raises(AuthError) as caught:
        await sign_in(harness, paths, store)
    assert caught.value.message == "Could not read the sign-in from the lingotube profile."
    assert "LEAKME" not in str(caught.value)
    assert harness.running.shut_down_connections[-1] is None
    assert not paths.cookies_file.exists()


async def test_sign_in_store_write_failure_is_auth_error_with_fixed_text(paths, store):
    """Check that a failed store write raises AuthError with a fixed text."""
    harness = Harness(FakeConnection([SIGNED_IN]))

    async def failing_write(saved):
        raise OSError("disk LEAKME-path")

    store.write = failing_write
    with pytest.raises(AuthError) as caught:
        await sign_in(harness, paths, store)
    assert caught.value.message == "Could not save the lingotube sign-in."
    assert "LEAKME" not in (caught.value.hint or "")
    assert harness.running.shut_down_calls >= 1


async def refresh(harness: Harness, paths, store, find=lambda browser: Path("edge")):
    """Run the refresh of the login profile with the fakes of the harness.

    Args:
        harness: Test harness.
        paths: Login paths.
        store: Cookie store.
        find: Function that finds the browser executable by name.

    Returns:
        The refresh result.
    """
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
    """Check that a refresh saves the rotated cookies."""
    await store.write(SavedLogin(browser="edge", cookies={ROTATING_COOKIE: "OLD-LEAKME"}))
    rotated_cookies = [cookie("SAPISID", "LEAKME-new"), cookie(ROTATING_COOKIE, "NEW")]
    harness = Harness(FakeConnection([[cookie(ROTATING_COOKIE, "OLD-LEAKME")], rotated_cookies]))
    result = await refresh(harness, paths, store)
    assert result.rotated is True
    assert result.saved.browser == "edge"
    assert (await store.read()).cookies[ROTATING_COOKIE] == "NEW"
    assert harness.launch_args[2:] == ("headless", REFRESH_PAGE_URL)
    assert harness.running.shut_down_calls >= 1


async def test_refresh_without_rotation_still_saves_and_reports(paths, store):
    """Check that a refresh without rotation still saves and reports it."""
    await store.write(SavedLogin(browser="chrome", cookies={ROTATING_COOKIE: "SAME"}))
    unchanged = [cookie("SAPISID", "LEAKME-s"), cookie(ROTATING_COOKIE, "SAME")]
    harness = Harness(FakeConnection([unchanged]))
    result = await refresh(harness, paths, store)
    assert result.rotated is False
    assert harness.clock.now >= 15.0
    assert (await store.read()).cookies["SAPISID"] == "LEAKME-s"


async def test_refresh_waits_at_least_one_poll_before_deciding(paths, store):
    """Check that the refresh waits for at least one poll before it decides."""
    await store.write(SavedLogin(browser="chrome", cookies={"SAPISID": "old"}))
    cookies = [cookie("SAPISID", "LEAKME-s"), cookie(ROTATING_COOKIE, "EARLY")]
    harness = Harness(FakeConnection([cookies]))
    await refresh(harness, paths, store)
    assert harness.connection.commands.count("Storage.getCookies") >= 2
    assert harness.clock.now >= 1.0


async def test_refresh_store_write_failure_is_auth_error(paths, store):
    """Check that a failed store write during refresh raises AuthError."""
    await store.write(SavedLogin(browser="chrome", cookies={}))
    cookies = [cookie("SAPISID", "LEAKME-s"), cookie(ROTATING_COOKIE, "NEW")]
    harness = Harness(FakeConnection([cookies]))

    async def failing_write(saved):
        raise OSError("disk LEAKME-path")

    store.write = failing_write
    with pytest.raises(AuthError) as caught:
        await refresh(harness, paths, store)
    assert caught.value.message == "Could not save the lingotube sign-in."


async def test_refresh_busy_profile_is_auth_error_with_close_window_hint(paths, store, monkeypatch):
    """Check that a busy profile during refresh raises AuthError with the close-window hint."""
    await store.write(SavedLogin(browser="chrome", cookies={}))
    monkeypatch.setattr("lingotube.auth.login_flow.is_login_profile_in_use", lambda profile_dir: True)
    harness = Harness(FakeConnection([[]]))
    with pytest.raises(AuthError) as caught:
        await refresh(harness, paths, store)
    assert caught.value.message == PROFILE_BUSY_MESSAGE
    assert caught.value.hint == PROFILE_BUSY_HINT
    assert harness.launch_args == ()


async def test_refresh_converts_profile_busy_error_from_launch(paths, store):
    """Check that ProfileBusyError from the launch is converted to AuthError."""
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
    """Check that a signed-out profile during refresh raises AuthError with the login hint."""
    await store.write(SavedLogin(browser="chrome", cookies={}))
    harness = Harness(FakeConnection([[cookie("PREF", "LEAKME")]]))
    with pytest.raises(AuthError) as caught:
        await refresh(harness, paths, store)
    assert caught.value.hint == LOGIN_HINT
    assert harness.running.shut_down_calls >= 1


async def test_refresh_devtools_failure_is_auth_error_with_login_hint(paths, store):
    """Check that a DevTools failure during refresh raises AuthError with the login hint."""
    await store.write(SavedLogin(browser="chrome", cookies={}))

    class BrokenConnection(FakeConnection):
        async def send_command(self, method, params=None):
            if method == "Storage.getCookies":
                raise DevToolsConnectionClosed("LEAKME-detail")
            return await super().send_command(method, params)

    harness = Harness(BrokenConnection([[]]))
    with pytest.raises(AuthError) as caught:
        await refresh(harness, paths, store)
    assert caught.value.message == "Could not refresh the sign-in in the lingotube profile."
    assert caught.value.hint == LOGIN_HINT
    assert "LEAKME" not in str(caught.value)
    assert harness.running.shut_down_calls >= 1


async def test_refresh_without_browser_is_auth_error(paths, store):
    """Check that a refresh without an installed browser raises AuthError."""
    await store.write(SavedLogin(browser="chrome", cookies={}))
    harness = Harness(FakeConnection([[]]))
    with pytest.raises(AuthError) as caught:
        await refresh(harness, paths, store, find=lambda browser: None)
    assert caught.value.hint == LOGIN_HINT


async def test_no_cookie_value_in_any_error_message(paths, store):
    """Check that no cookie value appears in any error message."""
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
