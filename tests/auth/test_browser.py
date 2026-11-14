"""Tests of the browser cookie source and the fallback chain."""

import pytest

from lingotube.auth import BrowserCookieSource, ChainCookieSource, Credentials
from lingotube.errors import AuthError


async def test_browser_source_uses_injected_loader():
    """Check that the browser source reads cookies through the injected loader."""
    src = BrowserCookieSource(
        browser="firefox",
        loader=lambda b: {"SAPISID": "s"},
    )
    assert (await src.load()).cookies["SAPISID"] == "s"


async def test_browser_loader_failure_is_auth_error_with_hint():
    """Check that a failing loader raises AuthError with a hint."""

    def boom(b):
        raise RuntimeError("locked SECRETVALUE")

    with pytest.raises(expected_exception=AuthError) as e:
        await BrowserCookieSource(
            browser="chrome",
            loader=boom,
        ).load()
    assert "cookies-file" in e.value.hint and "SECRETVALUE" not in str(e.value)
    assert "SECRETVALUE" not in e.value.hint


async def test_none_tries_browsers_in_order():
    """Check that without a browser name the browsers are tried in order."""
    seen = []

    def loader(b):
        seen.append(b)
        if b != "edge":
            raise RuntimeError("x")
        return {"SAPISID": "s"}

    await BrowserCookieSource(loader=loader).load()
    assert seen == ["firefox", "chrome", "edge"]


async def test_no_login_is_auth_error():
    """Check that no sign-in in any browser raises AuthError."""
    with pytest.raises(expected_exception=AuthError):
        await BrowserCookieSource(
            browser="firefox",
            loader=lambda b: {"SID": "x"},
        ).load()


class _Fail:
    async def load(self):
        raise AuthError(message="no")


class _Ok:
    async def load(self):
        return Credentials(cookies={"SAPISID": "s"})


async def test_chain_falls_back():
    """Check that the chain uses the next source when the first one fails."""
    assert (await ChainCookieSource(sources=[_Fail(), _Ok()]).load()).cookies == {"SAPISID": "s"}


async def test_chain_all_fail():
    """Check that the chain raises AuthError when every source fails."""
    with pytest.raises(expected_exception=AuthError) as e:
        await ChainCookieSource(sources=[_Fail()]).load()
    assert "cookies-file" in e.value.hint


async def test_default_chain_on_windows_keeps_chrome_edge_hint():
    """Check that on Windows the default chain keeps the hint for Chrome and Edge."""

    def boom(b):
        raise RuntimeError("locked")

    chain = ChainCookieSource(
        sources=[
            BrowserCookieSource(
                browser=None,
                loader=boom,
                platform="win32",
            )
        ]
    )
    with pytest.raises(expected_exception=AuthError) as e:
        await chain.load()
    assert "Chrome/Edge" in e.value.hint and "cookies-file" in e.value.hint


async def test_default_chain_elsewhere_has_only_export_hint():
    """Check that outside Windows the default chain gives only the export hint."""

    def boom(b):
        raise RuntimeError("locked")

    chain = ChainCookieSource(
        sources=[
            BrowserCookieSource(
                browser=None,
                loader=boom,
                platform="linux",
            )
        ]
    )
    with pytest.raises(expected_exception=AuthError) as e:
        await chain.load()
    assert "Chrome/Edge" not in e.value.hint and "cookies-file" in e.value.hint
