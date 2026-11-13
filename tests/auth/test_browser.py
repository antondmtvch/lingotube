import pytest

from lingotube.auth import BrowserCookieSource, ChainCookieSource, Credentials
from lingotube.errors import AuthError


async def test_browser_source_uses_injected_loader():
    src = BrowserCookieSource(
        browser="firefox",
        loader=lambda b: {"SAPISID": "s"},
    )
    assert (await src.load()).cookies["SAPISID"] == "s"


async def test_browser_loader_failure_is_auth_error_with_hint():
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
    seen = []

    def loader(b):
        seen.append(b)
        if b != "edge":
            raise RuntimeError("x")
        return {"SAPISID": "s"}

    await BrowserCookieSource(loader=loader).load()
    assert seen == ["firefox", "chrome", "edge"]


async def test_no_login_is_auth_error():
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
    assert (await ChainCookieSource(sources=[_Fail(), _Ok()]).load()).cookies == {"SAPISID": "s"}


async def test_chain_all_fail():
    with pytest.raises(expected_exception=AuthError) as e:
        await ChainCookieSource(sources=[_Fail()]).load()
    assert "cookies-file" in e.value.hint


async def test_default_chain_on_windows_keeps_chrome_edge_hint():
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
