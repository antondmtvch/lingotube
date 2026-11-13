import pytest

from lingotube.auth.base import LOGIN_HINT
from lingotube.auth.login_source import LoginProfileCookieSource
from lingotube.auth.login_store import LoginCookieStore, SavedLogin
from lingotube.config import LoginPaths
from lingotube.errors import AuthError


def make_paths(tmp_path) -> LoginPaths:
    return LoginPaths(
        profile_dir=tmp_path / "login-profile",
        cookies_file=tmp_path / "login-cookies.json",
    )


async def test_login_source_loads_saved_cookies(tmp_path):
    paths = make_paths(tmp_path=tmp_path)
    store = LoginCookieStore(cookies_file=paths.cookies_file)
    await store.write(saved=SavedLogin(browser="chrome", cookies={"SAPISID": "s1"}))
    credentials = await LoginProfileCookieSource(store=store, paths=paths).load()
    assert credentials.sapisid() == "s1"


async def test_login_source_without_sapisid_is_auth_error_with_login_hint(tmp_path):
    paths = make_paths(tmp_path=tmp_path)
    store = LoginCookieStore(cookies_file=paths.cookies_file)
    await store.write(saved=SavedLogin(browser="chrome", cookies={"SID": "LEAKME"}))
    with pytest.raises(AuthError) as info:
        await LoginProfileCookieSource(store=store, paths=paths).load()
    assert info.value.hint == LOGIN_HINT
    assert "LEAKME" not in info.value.message


async def test_refresh_from_profile_passes_paths_and_store(tmp_path):
    paths = make_paths(tmp_path=tmp_path)
    store = LoginCookieStore(cookies_file=paths.cookies_file)
    calls: list[dict] = []

    async def fake_refresh(**kwargs):
        calls.append(kwargs)

    await LoginProfileCookieSource(store=store, paths=paths, refresh=fake_refresh).refresh_from_profile()
    assert calls == [{"paths": paths, "store": store}]
