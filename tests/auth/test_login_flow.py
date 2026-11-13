import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from lingotube.auth.base import LOGIN_HINT
from lingotube.auth.devtools import BrowserCookie, DevToolsConnectionClosed
from lingotube.auth.login_browser import PROFILE_BUSY_HINT
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
        self.shut_down_calls = 0

    async def shut_down(self, connection) -> None:
        self.shut_down_calls += 1


class Harness:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.running = FakeRunningBrowser()
        self.clock = FakeClock()
        self.launch_args: tuple = ()

    async def launch(self, executable, profile_dir, mode, start_url):
        self.launch_args = (executable, profile_dir, mode, start_url)
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


async def test_sign_in_clears_cookies_before_opening_login_page(paths, store):
    harness = Harness(FakeConnection([SIGNED_IN]))
    messages: list[str] = []
    await sign_in(harness, paths, store, notify=messages.append)
    commands = harness.connection.commands
    assert commands.index("Storage.clearCookies") < commands.index(
        "Target.createTarget"
    )
    assert harness.launch_args == (
        Path("chrome"),
        paths.profile_dir,
        "window",
        "about:blank",
    )
    assert messages == ["Откройте окно браузера и войдите в YouTube; жду до 10 минут."]
    assert LOGIN_PAGE_URL.startswith("https://accounts.google.com/ServiceLogin")


async def test_sign_in_waits_for_sapisid_and_login_info_then_saves(paths, store):
    harness = Harness(FakeConnection([[], [cookie("SAPISID", "LEAKME-s")], SIGNED_IN]))
    saved = await sign_in(harness, paths, store)
    assert saved.browser == "chrome"
    assert set(saved.cookies) == {"SAPISID", "LOGIN_INFO"}
    assert await store.read() == saved
    assert harness.running.shut_down_calls >= 1


async def test_sign_in_accepts_sapisid_alone_after_grace(paths, store):
    harness = Harness(FakeConnection([[cookie("__Secure-3PAPISID", "LEAKME")]]))
    saved = await sign_in(harness, paths, store)
    assert "__Secure-3PAPISID" in saved.cookies
    assert harness.clock.now >= 15.0


async def test_sign_in_drops_foreign_domain_cookies(paths, store):
    harness = Harness(
        FakeConnection([SIGNED_IN + [cookie("TRACKER", "LEAKME", ".example.com")]])
    )
    saved = await sign_in(harness, paths, store)
    assert "TRACKER" not in saved.cookies
    assert "TRACKER" not in (await store.read()).cookies


async def test_window_closed_before_sign_in_is_auth_error_quickly(paths, store):
    harness = Harness(FakeConnection([[]], page_counts=[0]))
    with pytest.raises(AuthError) as caught:
        await sign_in(harness, paths, store)
    assert "закрыто" in caught.value.message
    assert harness.clock.now == 0.0
    assert harness.running.shut_down_calls >= 1


async def test_sign_in_timeout_is_auth_error_and_shuts_down(paths, store):
    harness = Harness(FakeConnection([[]]))
    with pytest.raises(AuthError) as caught:
        await sign_in(harness, paths, store)
    assert "10 минут" in caught.value.message
    assert harness.clock.now >= 600.0
    assert harness.running.shut_down_calls >= 1


async def test_sign_in_cancelled_shuts_down_browser(paths, store):
    polling = asyncio.Event()

    async def block_forever():
        polling.set()
        await asyncio.Event().wait()

    harness = Harness(FakeConnection([[]], on_cookies=block_forever))
    task = asyncio.create_task(sign_in(harness, paths, store))
    await polling.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
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
    closed_harness = Harness(FakeConnection([signed_out], page_counts=[0]))
    with pytest.raises(AuthError) as closed_error:
        await sign_in(closed_harness, paths, store)
    timeout_harness = Harness(FakeConnection([signed_out]))
    with pytest.raises(AuthError) as timeout_error:
        await sign_in(timeout_harness, paths, store)
    for error in (refresh_error.value, closed_error.value, timeout_error.value):
        assert "LEAKME" not in str(error)
        assert "LEAKME" not in error.hint
