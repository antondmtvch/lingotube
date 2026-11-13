import io
import json
from pathlib import Path

import pytest
from dependency_injector import providers

from lingotube import cli
from lingotube.auth.base import LOGIN_HINT, Credentials
from lingotube.auth.browser import BROWSERS
from lingotube.auth.login_store import LoginCookieStore, SavedLogin
from lingotube.commands import AppContext
from lingotube.config import LoginPaths, Settings
from lingotube.container import build_container
from lingotube.doctor import (
    CHAT,
    DEFAULT_TEST_VIDEO,
    LOGIN,
    NETWORK,
    Check,
    doctor_exit_code,
    run_doctor,
)
from lingotube.errors import AuthError, ChatUnavailableError, NetworkError
from lingotube.models import VideoInfo

SECRET_SAPISID = "SAPISID_VALUE_DOCTOR_123"
SECRET_SID = "SID_VALUE_DOCTOR_456"


class GoodSource:
    def __init__(self) -> None:
        self.loads = 0

    async def load(self) -> Credentials:
        self.loads += 1
        return Credentials(cookies={"SAPISID": SECRET_SAPISID, "SID": SECRET_SID})


class BadSource:
    def __init__(self, message: str = "В браузере chrome нет входа в YouTube.") -> None:
        self.message = message

    async def load(self) -> Credentials:
        raise AuthError(
            message=self.message,
            hint="выгрузите cookies.txt и запустите с --cookies-file",
        )


class FakeSession:
    def __init__(self, video_id: str) -> None:
        self.info = VideoInfo(
            video_id=video_id,
            duration=60.0,
            title="t",
            language="en",
        )

    async def ask(self, prompt: str) -> str:  # doctor must never ask
        raise AssertionError("doctor must not send chat messages")


class FakeAsk:
    """`outcome`: None → chat opens; an exception → raised by open()."""

    def __init__(
        self,
        source,
        outcome,
        log: list,
    ) -> None:
        self.source = source
        self.outcome = outcome
        self.log = log

    async def open(self, video_id: str) -> FakeSession:
        creds = await self.source.load()
        assert creds.sapisid() == SECRET_SAPISID
        self.log.append(video_id)
        if self.outcome is not None:
            raise self.outcome
        return FakeSession(video_id=video_id)


def ask_factory(
    outcome=None,
    log: list | None = None,
):
    log = log if log is not None else []
    return lambda source: FakeAsk(
        source=source,
        outcome=outcome,
        log=log,
    )


def by_name(
    checks: list[Check],
    name: str,
) -> Check:
    return next(c for c in checks if c.name == name)


async def test_file_ok_browser_fails_is_success():
    opened: list[str] = []
    checks = await run_doctor(
        sources={"файл cookies": GoodSource(), "браузер chrome": BadSource()},
        make_ask=ask_factory(log=opened),
        test_video_id="abcdefghijk",
    )
    sources = [c for c in checks if c.name not in (LOGIN, CHAT, NETWORK)]
    assert [(c.name, c.ok) for c in sources] == [
        ("файл cookies", True),
        ("браузер chrome", False),
    ]
    assert (
        by_name(
            checks=checks,
            name=LOGIN,
        ).ok
        and by_name(
            checks=checks,
            name=CHAT,
        ).ok
    )
    assert doctor_exit_code(checks=checks) == 0
    assert opened == ["abcdefghijk"]


async def test_all_sources_fail_is_exit_4_with_export_hint():
    checks = await run_doctor(
        sources={
            "файл cookies": BadSource(message="Файл cookies не задан."),
            "браузер edge": BadSource(),
        },
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    assert (
        not by_name(
            checks=checks,
            name=LOGIN,
        ).ok
        and not by_name(
            checks=checks,
            name=CHAT,
        ).ok
    )
    assert doctor_exit_code(checks=checks) == 4
    assert "--cookies-file" in (
        by_name(
            checks=checks,
            name=LOGIN,
        ).hint
        or ""
    )


async def test_signed_in_but_chat_unavailable_is_exit_3():
    checks = await run_doctor(
        sources={"файл cookies": GoodSource()},
        make_ask=ask_factory(
            outcome=ChatUnavailableError(message="Чат недоступен для этого видео.")
        ),
        test_video_id="abcdefghijk",
    )
    assert by_name(
        checks=checks,
        name=LOGIN,
    ).ok
    assert not by_name(
        checks=checks,
        name=CHAT,
    ).ok
    assert doctor_exit_code(checks=checks) == 3


async def test_stale_first_source_falls_back_to_next():
    class Stale:
        async def load(self) -> Credentials:
            return Credentials(cookies={"SAPISID": "STALE"})

    class StaleAware:
        def __init__(self, source) -> None:
            self.source = source

        async def open(self, video_id: str) -> FakeSession:
            if (await self.source.load()).sapisid() == "STALE":
                raise AuthError(message="cookies устарели")
            return FakeSession(video_id=video_id)

    checks = await run_doctor(
        sources={"файл cookies": Stale(), "браузер firefox": GoodSource()},
        make_ask=StaleAware,
        test_video_id="abcdefghijk",
    )
    assert not by_name(
        checks=checks,
        name="файл cookies",
    ).ok
    assert by_name(
        checks=checks,
        name="браузер firefox",
    ).ok
    assert (
        by_name(
            checks=checks,
            name=LOGIN,
        ).ok
        and by_name(
            checks=checks,
            name=CHAT,
        ).ok
    )
    assert doctor_exit_code(checks=checks) == 0


async def test_all_loaded_sources_stale_is_exit_4():
    checks = await run_doctor(
        sources={"файл cookies": GoodSource()},
        make_ask=ask_factory(outcome=AuthError(message="cookies устарели")),
        test_video_id="abcdefghijk",
    )
    assert not by_name(
        checks=checks,
        name=LOGIN,
    ).ok
    assert doctor_exit_code(checks=checks) == 4


async def test_network_failure_is_exit_6():
    checks = await run_doctor(
        sources={"файл cookies": GoodSource()},
        make_ask=ask_factory(outcome=NetworkError(message="сеть")),
        test_video_id="abcdefghijk",
    )
    assert not by_name(
        checks=checks,
        name=NETWORK,
    ).ok
    assert doctor_exit_code(checks=checks) == 6


async def test_source_read_once():
    source = GoodSource()
    await run_doctor(
        sources={"файл cookies": source},
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    assert source.loads == 1


async def test_checks_never_contain_cookie_values():
    for outcome in (
        None,
        ChatUnavailableError(message="нет чата"),
        AuthError(message="нет входа"),
        NetworkError(message="сеть"),
    ):
        checks = await run_doctor(
            sources={"файл cookies": GoodSource(), "браузер chrome": BadSource()},
            make_ask=ask_factory(outcome=outcome),
            test_video_id="abcdefghijk",
        )
        text = repr(checks)
        assert SECRET_SAPISID not in text and SECRET_SID not in text


# --- command ---


class Harness:
    def __init__(
        self,
        tmp_path: Path,
        sources: dict,
        outcome=None,
        settings: Settings | None = None,
    ) -> None:
        self.tmp = tmp_path
        self.sources = sources
        self.opened: list[str] = []
        self.outcome = outcome
        self.settings = settings or Settings()
        self.containers: list = []

    def factory(
        self,
        out,
        err,
    ) -> AppContext:
        container = build_container(
            settings=self.settings,
            env={},
            cache_dir=self.tmp / "cache",
            login_paths=LoginPaths(
                profile_dir=self.tmp / "login-profile",
                cookies_file=self.tmp / "login-cookies.json",
            ),
            err=err,
        )
        container.doctor_sources.override(provider=providers.Object(self.sources))
        container.ask_factory.override(
            provider=providers.Object(
                ask_factory(
                    outcome=self.outcome,
                    log=self.opened,
                )
            )
        )
        self.containers.append(container)
        return AppContext(
            container=container,
            out=out,
            err=err,
            cwd=self.tmp,
            settings_path=None,
        )

    def run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = cli.run(
            argv=["doctor", *argv],
            out=out,
            err=err,
            context_factory=self.factory,
        )
        return code, out.getvalue(), err.getvalue()


def test_doctor_command_success_prints_table(tmp_path):
    h = Harness(
        tmp_path=tmp_path,
        sources={"файл cookies": GoodSource(), "браузер chrome": BadSource()},
    )
    code, out, err = h.run()
    assert code == 0, err
    assert (
        "файл cookies" in out
        and "браузер chrome" in out
        and LOGIN in out
        and CHAT in out
    )
    assert h.opened == [DEFAULT_TEST_VIDEO]
    assert SECRET_SAPISID not in out + err and SECRET_SID not in out + err


def test_doctor_command_all_sources_fail_exit_4(tmp_path):
    h = Harness(
        tmp_path=tmp_path,
        sources={
            "файл cookies": BadSource(message="Файл cookies не задан."),
            "браузер chrome": BadSource(),
        },
    )
    code, out, err = h.run()
    assert code == 4
    assert "--cookies-file" in err
    assert "cookies.txt" in err
    assert h.opened == []


def test_doctor_command_chat_unavailable_exit_3(tmp_path):
    h = Harness(
        tmp_path=tmp_path,
        sources={"файл cookies": GoodSource()},
        outcome=ChatUnavailableError(message="Чат недоступен."),
    )
    code, out, err = h.run()
    assert code == 3
    assert "Чат недоступен." in out
    assert "--video" in err


def test_doctor_command_json(tmp_path):
    h = Harness(
        tmp_path=tmp_path,
        sources={"файл cookies": GoodSource()},
        outcome=ChatUnavailableError(message="Чат недоступен."),
    )
    code, out, _ = h.run("--json")
    assert code == 3
    doc = json.loads(s=out)
    assert doc["ok"] is False and doc["error"]["code"] == "chat_unavailable"
    assert doc["result"]["video_id"] == DEFAULT_TEST_VIDEO
    names = [c["name"] for c in doc["result"]["checks"]]
    assert names == ["файл cookies", LOGIN, CHAT]
    assert SECRET_SAPISID not in out and SECRET_SID not in out


def test_doctor_command_json_unexpected_source_row_is_neutral_for_exit(tmp_path):
    h = Harness(
        tmp_path=tmp_path,
        sources={"файл cookies": CrashingSource(), "браузер chrome": GoodSource()},
    )
    code, out, _ = h.run("--json")
    assert code == 0
    doc = json.loads(s=out)
    assert doc["ok"] is True and doc.get("error") is None
    row = doc["result"]["checks"][0]
    assert row["name"] == "файл cookies" and row["ok"] is False
    assert "RuntimeError" in row["detail"] and SECRET_SAPISID not in out


@pytest.mark.parametrize(
    argnames="arg",
    argvalues=["-n5MqamatXE", "https://youtu.be/-n5MqamatXE", "abcdefghijk"],
)
def test_doctor_video_option(
    tmp_path,
    arg,
):
    h = Harness(
        tmp_path=tmp_path,
        sources={"файл cookies": GoodSource()},
    )
    code, _, err = h.run(
        "--video",
        arg,
    )
    assert code == 0, err
    assert h.opened == [arg[-11:]]


def test_doctor_bad_video_option_fails_before_network(tmp_path):
    h = Harness(
        tmp_path=tmp_path,
        sources={"файл cookies": GoodSource()},
    )
    code, _, _ = h.run(
        "--video",
        "https://example.com/x",
    )
    assert code == 7
    assert h.opened == []


async def test_container_doctor_sources(tmp_path):
    def make(settings):
        return build_container(
            settings=settings,
            env={},
            cache_dir=tmp_path / "c",
            login_paths=LoginPaths(
                profile_dir=tmp_path / "login-profile",
                cookies_file=tmp_path / "login-cookies.json",
            ),
            err=io.StringIO(),
        )

    plain = make(settings=Settings()).doctor_sources()
    assert list(plain) == [
        "файл cookies",
        "профиль входа",
        *[f"браузер {b}" for b in BROWSERS],
    ]
    with pytest.raises(expected_exception=AuthError) as unset_login:
        await plain["профиль входа"].load()
    assert unset_login.value.hint == LOGIN_HINT
    with pytest.raises(expected_exception=AuthError) as info:
        await plain["файл cookies"].load()
    assert "--cookies-file" in (info.value.hint or "")

    chosen = make(
        settings=Settings(
            cookies_file=tmp_path / "c.txt",
            browser="firefox",
        )
    ).doctor_sources()
    assert list(chosen) == ["файл cookies", "профиль входа", "браузер firefox"]

    loaded: list[str] = []

    def loader(browser):
        loaded.append(browser)
        return {"SAPISID": "x"}

    container = make(settings=Settings(browser="edge"))
    container.browser_loader.override(provider=providers.Object(loader))
    creds = await container.doctor_sources()["браузер edge"].load()
    assert creds.sapisid() == "x" and loaded == ["edge"]


async def test_container_ask_factory_builds_youtube_clients(tmp_path):
    from lingotube.ask.client import YouTubeAskClient

    container = build_container(
        settings=Settings(),
        env={},
        cache_dir=tmp_path / "c",
        login_paths=LoginPaths(
            profile_dir=tmp_path / "login-profile",
            cookies_file=tmp_path / "login-cookies.json",
        ),
        err=io.StringIO(),
    )
    try:
        make = await container.ask_factory()
        first, second = make(GoodSource()), make(GoodSource())
        assert (
            isinstance(
                first,
                YouTubeAskClient,
            )
            and first is not second
        )
    finally:
        await container.shutdown_resources()


def test_doctor_registered_in_cli():
    import typer.main

    app = cli.build_app(
        registry=cli.build_registry(),
        get_context=lambda: None,
    )  # type: ignore[arg-type, return-value]
    assert "doctor" in typer.main.get_command(typer_instance=app).commands  # type: ignore[attr-defined]


def test_table_lists_hints_of_failed_checks_once():
    from lingotube.doctor import render_table

    checks = [
        Check(
            name="a",
            ok=False,
            detail="x",
            hint="сделайте A",
        ),
        Check(
            name="b",
            ok=False,
            detail="y",
            hint="сделайте A",
        ),
        Check(
            name="c",
            ok=True,
            detail="z",
            hint=None,
        ),
        Check(
            name="d",
            ok=False,
            detail="w",
            hint="общая",
        ),
    ]
    error = AuthError(
        message="e",
        hint="общая",
    )
    text = render_table(
        checks=checks,
        error=error,
    )
    assert text.count("сделайте A") == 1
    assert "общая" not in text


async def test_failed_browsers_are_not_critical_when_a_source_works():
    from lingotube.doctor import render_table

    checks = await run_doctor(
        sources={"файл cookies": GoodSource(), "браузер chrome": BadSource()},
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    chrome = by_name(
        checks=checks,
        name="браузер chrome",
    )
    assert not chrome.ok and not chrome.critical
    text = render_table(
        checks=checks,
        error=None,
    )
    assert "ошибка" not in text
    chrome_row = next(
        line for line in text.splitlines() if line.startswith("браузер chrome")
    )
    assert chrome_row.split()[2:5] == ["не", "прочитан", "В"]
    assert "Подсказки" not in text and "cookies.txt" not in text
    assert doctor_exit_code(checks=checks) == 0


async def test_stale_source_is_reported_as_not_accepted_not_as_unread():
    from lingotube.doctor import render_table

    class Stale:
        async def load(self) -> Credentials:
            return Credentials(cookies={"SAPISID": "STALE"})

    class StaleAware:
        def __init__(self, source) -> None:
            self.source = source

        async def open(self, video_id: str) -> FakeSession:
            if (await self.source.load()).sapisid() == "STALE":
                raise AuthError(message="cookies устарели")
            return FakeSession(video_id=video_id)

    checks = await run_doctor(
        sources={"файл cookies": Stale(), "браузер firefox": GoodSource()},
        make_ask=StaleAware,
        test_video_id="abcdefghijk",
    )
    text = render_table(checks=checks, error=None)
    row = next(line for line in text.splitlines() if line.startswith("файл cookies"))
    assert "не принят" in row and "не прочитан" not in row


async def test_failed_sources_stay_critical_when_none_works():
    from lingotube.doctor import doctor_error, render_table

    checks = await run_doctor(
        sources={"файл cookies": BadSource(), "браузер edge": BadSource()},
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    assert all(c.critical for c in checks)
    text = render_table(
        checks=checks,
        error=doctor_error(checks=checks),
    )
    assert "ошибка" in text and "Подсказки" in text
    assert doctor_exit_code(checks=checks) == 4


async def test_network_error_does_not_claim_missing_login():
    from lingotube.doctor import NETWORK_HINT

    checks = await run_doctor(
        sources={"файл cookies": GoodSource()},
        make_ask=ask_factory(outcome=NetworkError(message="сеть")),
        test_video_id="abcdefghijk",
    )
    for name in (LOGIN, CHAT):
        detail = by_name(
            checks=checks,
            name=name,
        ).detail
        assert "нет входа" not in detail
        assert "соединени" in detail
    assert NETWORK_HINT in (
        by_name(
            checks=checks,
            name=NETWORK,
        ).hint
        or ""
    )
    assert doctor_exit_code(checks=checks) == 6


class CrashingSource:
    async def load(self) -> Credentials:
        raise RuntimeError(f"boom {SECRET_SAPISID}")


async def test_unexpected_error_in_source_keeps_row_failed_but_exit_0_when_another_works():
    checks = await run_doctor(
        sources={"файл cookies": CrashingSource(), "браузер chrome": GoodSource()},
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    row = by_name(
        checks=checks,
        name="файл cookies",
    )
    assert not row.ok and row.critical
    assert "RuntimeError" in row.detail
    assert SECRET_SAPISID not in repr(checks)
    assert by_name(
        checks=checks,
        name="браузер chrome",
    ).ok
    assert doctor_exit_code(checks=checks) == 0
    from lingotube.doctor import render_table

    assert "ошибка" in render_table(checks=checks)


async def test_unexpected_error_without_a_working_source_still_exits_1():
    checks = await run_doctor(
        sources={"файл cookies": CrashingSource()},
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    assert doctor_exit_code(checks=checks) == 1


async def test_unexpected_error_in_chat_open_marks_row_failed_and_exit_1():
    checks = await run_doctor(
        sources={"файл cookies": GoodSource()},
        make_ask=ask_factory(outcome=KeyError(SECRET_SID)),
        test_video_id="abcdefghijk",
    )
    row = by_name(
        checks=checks,
        name="файл cookies",
    )
    assert not row.ok and "KeyError" in row.detail
    assert SECRET_SID not in repr(checks)
    assert doctor_exit_code(checks=checks) == 1


def test_doctor_command_unexpected_error_still_prints_table(tmp_path):
    h = Harness(
        tmp_path=tmp_path,
        sources={"файл cookies": CrashingSource(), "браузер chrome": GoodSource()},
    )
    code, out, err = h.run()
    assert code == 0
    assert "файл cookies" in out and "RuntimeError" in out and LOGIN in out
    assert SECRET_SAPISID not in out + err


async def test_doctor_lists_login_profile_row_after_file(tmp_path):
    await LoginCookieStore(cookies_file=tmp_path / "login-cookies.json").write(
        saved=SavedLogin(browser="chrome", cookies={"SAPISID": SECRET_SAPISID})
    )
    container = build_container(
        settings=Settings(),
        env={},
        cache_dir=tmp_path / "c",
        login_paths=LoginPaths(
            profile_dir=tmp_path / "login-profile",
            cookies_file=tmp_path / "login-cookies.json",
        ),
        err=io.StringIO(),
    )
    sources = container.doctor_sources()
    assert list(sources)[:2] == ["файл cookies", "профиль входа"]
    assert (await sources["профиль входа"].load()).sapisid() == SECRET_SAPISID


async def test_doctor_login_profile_works_marks_others_non_critical():
    checks = await run_doctor(
        sources={
            "файл cookies": BadSource(),
            "профиль входа": GoodSource(),
            "браузер chrome": BadSource(),
        },
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    assert by_name(checks=checks, name="профиль входа").ok
    assert not by_name(checks=checks, name="файл cookies").critical
    assert not by_name(checks=checks, name="браузер chrome").critical
    assert doctor_exit_code(checks=checks) == 0
