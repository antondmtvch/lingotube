import os
import stat

import pytest

from lingotube.auth.base import LOGIN_HINT
from lingotube.auth.login_store import LoginCookieStore, SavedLogin
from lingotube.errors import AuthError


async def test_write_then_read_roundtrip(tmp_path):
    store = LoginCookieStore(cookies_file=tmp_path / "sub" / "login-cookies.json")
    assert not store.exists()
    await store.write(saved=SavedLogin(browser="edge", cookies={"SAPISID": "abc"}))
    assert store.exists()
    saved = await store.read()
    assert saved == SavedLogin(browser="edge", cookies={"SAPISID": "abc"})


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")
async def test_written_file_is_owner_only(tmp_path):
    path = tmp_path / "login-cookies.json"
    await LoginCookieStore(cookies_file=path).write(
        saved=SavedLogin(browser="chrome", cookies={"a": "b"})
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{",
        '{"version": 1, "browser": "chrome", "cookies": ["LEAKME"]}',
        '{"version": 2, "browser": "chrome", "cookies": {}}',
        '{"version": 1, "browser": "firefox", "cookies": {"a": "LEAKME"}}',
    ],
)
async def test_corrupted_file_is_auth_error_without_content(tmp_path, content):
    path = tmp_path / "login-cookies.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(AuthError) as caught:
        await LoginCookieStore(cookies_file=path).read()
    assert "LEAKME" not in caught.value.message + (caught.value.hint or "")
    assert caught.value.hint == LOGIN_HINT


async def test_missing_file_is_auth_error(tmp_path):
    with pytest.raises(AuthError) as caught:
        await LoginCookieStore(cookies_file=tmp_path / "none.json").read()
    assert caught.value.hint == LOGIN_HINT


async def test_delete_reports_whether_file_existed(tmp_path):
    store = LoginCookieStore(cookies_file=tmp_path / "login-cookies.json")
    assert await store.delete() is False
    await store.write(saved=SavedLogin(browser="chrome", cookies={}))
    assert await store.delete() is True
    assert not store.exists()


def test_saved_login_repr_hides_values():
    text = repr(SavedLogin(browser="chrome", cookies={"SAPISID": "LEAKME"}))
    assert text == "SavedLogin(browser=chrome, cookies=***)"
