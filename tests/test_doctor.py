import io
import json
from pathlib import Path

import pytest
from dependency_injector import providers

from lingotube import cli
from lingotube.auth.base import Credentials
from lingotube.auth.browser import BROWSERS
from lingotube.commands import AppContext
from lingotube.config import Settings
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
        return Credentials({"SAPISID": SECRET_SAPISID, "SID": SECRET_SID})


class BadSource:
    def __init__(self, message: str = "В браузере chrome нет входа в YouTube.") -> None:
        self.message = message

    async def load(self) -> Credentials:
        raise AuthError(
            self.message, hint="выгрузите cookies.txt и запустите с --cookies-file"
        )


class FakeSession:
    def __init__(self, video_id: str) -> None:
        self.info = VideoInfo(video_id, 60.0, "t", "en")

    async def ask(self, prompt: str) -> str:  # doctor must never ask
        raise AssertionError("doctor must not send chat messages")


class FakeAsk:
    """`outcome`: None → chat opens; an exception → raised by open()."""

    def __init__(self, source, outcome, log: list) -> None:
        self.source = source
        self.outcome = outcome
        self.log = log

    async def open(self, video_id: str) -> FakeSession:
        creds = await self.source.load()
        assert creds.sapisid() == SECRET_SAPISID
        self.log.append(video_id)
        if self.outcome is not None:
            raise self.outcome
        return FakeSession(video_id)


def ask_factory(outcome=None, log: list | None = None):
    log = log if log is not None else []
    return lambda source: FakeAsk(source, outcome, log)


def by_name(checks: list[Check], name: str) -> Check:
    return next(c for c in checks if c.name == name)


async def test_file_ok_browser_fails_is_success():
    opened: list[str] = []
    checks = await run_doctor(
        {"файл cookies": GoodSource(), "браузер chrome": BadSource()},
        ask_factory(log=opened),
        "abcdefghijk",
    )
    sources = [c for c in checks if c.name not in (LOGIN, CHAT, NETWORK)]
    assert [(c.name, c.ok) for c in sources] == [
        ("файл cookies", True),
        ("браузер chrome", False),
    ]
    assert by_name(checks, LOGIN).ok and by_name(checks, CHAT).ok
    assert doctor_exit_code(checks) == 0
    assert opened == ["abcdefghijk"]


async def test_all_sources_fail_is_exit_4_with_export_hint():
    checks = await run_doctor(
        {
            "файл cookies": BadSource("Файл cookies не задан."),
            "браузер edge": BadSource(),
        },
        ask_factory(),
        "abcdefghijk",
    )
    assert not by_name(checks, LOGIN).ok and not by_name(checks, CHAT).ok
    assert doctor_exit_code(checks) == 4
    assert "--cookies-file" in (by_name(checks, LOGIN).hint or "")


async def test_signed_in_but_chat_unavailable_is_exit_3():
    checks = await run_doctor(
        {"файл cookies": GoodSource()},
        ask_factory(ChatUnavailableError("Чат недоступен для этого видео.")),
        "abcdefghijk",
    )
    assert by_name(checks, LOGIN).ok
    assert not by_name(checks, CHAT).ok
    assert doctor_exit_code(checks) == 3


async def test_stale_first_source_falls_back_to_next():
    class Stale:
        async def load(self) -> Credentials:
            return Credentials({"SAPISID": "STALE"})

    class StaleAware:
        def __init__(self, source) -> None:
            self.source = source

        async def open(self, video_id: str) -> FakeSession:
            if (await self.source.load()).sapisid() == "STALE":
                raise AuthError("cookies устарели")
            return FakeSession(video_id)

    checks = await run_doctor(
        {"файл cookies": Stale(), "браузер firefox": GoodSource()},
        StaleAware,
        "abcdefghijk",
    )
    assert not by_name(checks, "файл cookies").ok
    assert by_name(checks, "браузер firefox").ok
    assert by_name(checks, LOGIN).ok and by_name(checks, CHAT).ok
    assert doctor_exit_code(checks) == 0


async def test_all_loaded_sources_stale_is_exit_4():
    checks = await run_doctor(
        {"файл cookies": GoodSource()},
        ask_factory(AuthError("cookies устарели")),
        "abcdefghijk",
    )
    assert not by_name(checks, LOGIN).ok
    assert doctor_exit_code(checks) == 4


async def test_network_failure_is_exit_6():
    checks = await run_doctor(
        {"файл cookies": GoodSource()}, ask_factory(NetworkError("сеть")), "abcdefghijk"
    )
    assert not by_name(checks, NETWORK).ok
    assert doctor_exit_code(checks) == 6


async def test_source_read_once():
    source = GoodSource()
    await run_doctor({"файл cookies": source}, ask_factory(), "abcdefghijk")
    assert source.loads == 1


async def test_checks_never_contain_cookie_values():
    for outcome in (
        None,
        ChatUnavailableError("нет чата"),
        AuthError("нет входа"),
        NetworkError("сеть"),
    ):
        checks = await run_doctor(
            {"файл cookies": GoodSource(), "браузер chrome": BadSource()},
            ask_factory(outcome),
            "abcdefghijk",
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

    def factory(self, out, err) -> AppContext:
        container = build_container(
            settings=self.settings, env={}, cache_dir=self.tmp / "cache", err=err
        )
        container.doctor_sources.override(providers.Object(self.sources))
        container.ask_factory.override(
            providers.Object(ask_factory(self.outcome, self.opened))
        )
        self.containers.append(container)
        return AppContext(
            container=container, out=out, err=err, cwd=self.tmp, settings_path=None
        )

    def run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = cli.run(
            ["doctor", *argv], out=out, err=err, context_factory=self.factory
        )
        return code, out.getvalue(), err.getvalue()


def test_doctor_command_success_prints_table(tmp_path):
    h = Harness(tmp_path, {"файл cookies": GoodSource(), "браузер chrome": BadSource()})
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
        tmp_path,
        {
            "файл cookies": BadSource("Файл cookies не задан."),
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
        tmp_path,
        {"файл cookies": GoodSource()},
        outcome=ChatUnavailableError("Чат недоступен."),
    )
    code, out, err = h.run()
    assert code == 3
    assert "Чат недоступен." in out
    assert "--video" in err


def test_doctor_command_json(tmp_path):
    h = Harness(
        tmp_path,
        {"файл cookies": GoodSource()},
        outcome=ChatUnavailableError("Чат недоступен."),
    )
    code, out, _ = h.run("--json")
    assert code == 3
    doc = json.loads(out)
    assert doc["ok"] is False and doc["error"]["code"] == "chat_unavailable"
    assert doc["result"]["video_id"] == DEFAULT_TEST_VIDEO
    names = [c["name"] for c in doc["result"]["checks"]]
    assert names == ["файл cookies", LOGIN, CHAT]
    assert SECRET_SAPISID not in out and SECRET_SID not in out


@pytest.mark.parametrize(
    "arg", ["-n5MqamatXE", "https://youtu.be/-n5MqamatXE", "abcdefghijk"]
)
def test_doctor_video_option(tmp_path, arg):
    h = Harness(tmp_path, {"файл cookies": GoodSource()})
    code, _, err = h.run("--video", arg)
    assert code == 0, err
    assert h.opened == [arg[-11:]]


def test_doctor_bad_video_option_fails_before_network(tmp_path):
    h = Harness(tmp_path, {"файл cookies": GoodSource()})
    code, _, _ = h.run("--video", "https://example.com/x")
    assert code == 7
    assert h.opened == []


async def test_container_doctor_sources(tmp_path):
    def make(settings):
        return build_container(
            settings=settings, env={}, cache_dir=tmp_path / "c", err=io.StringIO()
        )

    plain = make(Settings()).doctor_sources()
    assert list(plain) == ["файл cookies", *[f"браузер {b}" for b in BROWSERS]]
    with pytest.raises(AuthError) as info:
        await plain["файл cookies"].load()
    assert "--cookies-file" in (info.value.hint or "")

    chosen = make(
        Settings(cookies_file=tmp_path / "c.txt", browser="firefox")
    ).doctor_sources()
    assert list(chosen) == ["файл cookies", "браузер firefox"]

    loaded: list[str] = []

    def loader(browser):
        loaded.append(browser)
        return {"SAPISID": "x"}

    container = make(Settings(browser="edge"))
    container.browser_loader.override(providers.Object(loader))
    creds = await container.doctor_sources()["браузер edge"].load()
    assert creds.sapisid() == "x" and loaded == ["edge"]


async def test_container_ask_factory_builds_youtube_clients(tmp_path):
    from lingotube.ask.client import YouTubeAskClient

    container = build_container(
        settings=Settings(), env={}, cache_dir=tmp_path / "c", err=io.StringIO()
    )
    try:
        make = await container.ask_factory()
        first, second = make(GoodSource()), make(GoodSource())
        assert isinstance(first, YouTubeAskClient) and first is not second
    finally:
        await container.shutdown_resources()


def test_doctor_registered_in_cli():
    import typer.main

    app = cli.build_app(cli.build_registry(), lambda: None)  # type: ignore[arg-type, return-value]
    assert "doctor" in typer.main.get_command(app).commands  # type: ignore[attr-defined]


def test_table_lists_hints_of_failed_checks_once():
    from lingotube.doctor import render_table

    checks = [
        Check("a", False, "x", "сделайте A"),
        Check("b", False, "y", "сделайте A"),
        Check("c", True, "z", None),
        Check("d", False, "w", "общая"),
    ]
    error = AuthError("e", hint="общая")
    text = render_table(checks, error)
    assert text.count("сделайте A") == 1
    assert "общая" not in text
