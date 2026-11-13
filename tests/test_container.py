import io

from lingotube.auth.browser import BrowserCookieSource, ChainCookieSource
from lingotube.auth.file import FileCookieSource
from lingotube.auth.login_source import LoginProfileCookieSource
from lingotube.auth.login_store import LoginCookieStore, SavedLogin
from lingotube.config import LoginPaths, Settings
from lingotube.container import build_container


def make_container(tmp_path, settings: Settings):
    return build_container(
        settings=settings,
        env={},
        cache_dir=tmp_path / "cache",
        login_paths=LoginPaths(
            profile_dir=tmp_path / "login-profile",
            cookies_file=tmp_path / "login-cookies.json",
        ),
        err=io.StringIO(),
    )


async def save_login(tmp_path) -> None:
    await LoginCookieStore(cookies_file=tmp_path / "login-cookies.json").write(
        saved=SavedLogin(browser="chrome", cookies={"SAPISID": "s"})
    )


async def test_cookie_source_prefers_cookies_file_then_browser_then_login_profile(
    tmp_path,
):
    await save_login(tmp_path=tmp_path)
    with_file = make_container(
        tmp_path=tmp_path,
        settings=Settings(cookies_file=tmp_path / "c.txt", browser="firefox"),
    )
    assert isinstance(with_file.cookie_source(), FileCookieSource)
    with_browser = make_container(
        tmp_path=tmp_path, settings=Settings(browser="firefox")
    )
    assert isinstance(with_browser.cookie_source(), BrowserCookieSource)
    with_login = make_container(tmp_path=tmp_path, settings=Settings())
    assert isinstance(with_login.cookie_source(), LoginProfileCookieSource)


def test_cookie_source_falls_back_to_browser_chain_without_login(tmp_path):
    container = make_container(tmp_path=tmp_path, settings=Settings())
    assert isinstance(container.cookie_source(), ChainCookieSource)
