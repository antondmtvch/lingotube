"""Tests of the doctor command: cookie sources, the chat check, exit codes and the table."""

import io
import json
from pathlib import Path

import pytest
from dependency_injector import providers

from lingotube import cli
from lingotube.auth.base import LOGIN_HINT, Credentials
from lingotube.auth.browser import BROWSERS
from lingotube.auth.login_source import LoginProfileCookieSource
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
from lingotube.errors import (
    YOUTUBE_CHANGED_HINT,
    AuthError,
    ChatUnavailableError,
    NetworkError,
    YouTubeChangedError,
)
from lingotube.models import VideoInfo

SECRET_SAPISID = "SAPISID_VALUE_DOCTOR_123"
SECRET_SID = "SID_VALUE_DOCTOR_456"


class GoodSource:
    """Cookie source that always loads valid credentials."""

    def __init__(self) -> None:
        """Create the source with a counter of how many times it was loaded."""
        self.loads = 0

    async def load(self) -> Credentials:
        """Return the fixed valid credentials and count the load.

        Returns:
            The credentials with SAPISID and SID cookies.
        """
        self.loads += 1
        return Credentials(cookies={"SAPISID": SECRET_SAPISID, "SID": SECRET_SID})


class BadSource:
    """Cookie source that always fails with AuthError."""

    def __init__(self, message: str = "The browser chrome has no sign-in to YouTube.") -> None:
        """Create the source that fails with the given message.

        Args:
            message: Message of the AuthError that the source raises.
        """
        self.message = message

    async def load(self) -> Credentials:
        """Raise the AuthError of this source, with a fixed hint.

        Raises:
            AuthError: Always.
        """
        raise AuthError(
            message=self.message,
            hint="выгрузите cookies.txt и запустите с --cookies-file",
        )


class FakeSession:
    """Chat session that returns a fixed answer."""

    def __init__(self, video_id: str) -> None:
        """Create the session for a video.

        Args:
            video_id: YouTube video id of the session.
        """
        self.info = VideoInfo(
            video_id=video_id,
            duration=60.0,
            title="t",
            language="en",
        )

    async def ask(self, prompt: str) -> str:  # doctor must never ask
        """Fail if doctor sends a chat message, because doctor must never ask a question.

        Args:
            prompt: Prompt that must not be sent.

        Raises:
            AssertionError: Always.
        """
        raise AssertionError("doctor must not send chat messages")


class FakeAsk:
    """`outcome`: None → chat opens; an exception → raised by open()."""

    def __init__(
        self,
        source,
        outcome,
        log: list,
    ) -> None:
        """Create the fake chat client.

        Args:
            source: Cookie source that the client was created for.
            outcome: Exception that ``open`` raises, or None if the chat opens.
            log: List where the video ids of the opened chats are recorded.
        """
        self.source = source
        self.outcome = outcome
        self.log = log

    async def open(self, video_id: str) -> FakeSession:
        """Open the fake chat, or raise the configured outcome.

        Args:
            video_id: YouTube video id.

        Returns:
            A session on the fake chat.
        """
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
    """Build a function that returns a fake chat client for a cookie source.

    Args:
        outcome: Exception that the clients raise on open, or None.
        log: List where the opened video ids are recorded. A new list is used if None.

    Returns:
        A function that takes a cookie source and returns a fake chat client.
    """
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
    """Find the check with the given name.

    Args:
        checks: Check rows of a run.
        name: Name of the check.

    Returns:
        The check with that name.
    """
    return next(c for c in checks if c.name == name)


async def test_file_ok_browser_fails_is_success():
    """Check that a working file source is success even when a browser source fails."""
    opened: list[str] = []
    checks = await run_doctor(
        sources={"cookies file": GoodSource(), "browser chrome": BadSource()},
        make_ask=ask_factory(log=opened),
        test_video_id="abcdefghijk",
    )
    sources = [c for c in checks if c.name not in (LOGIN, CHAT, NETWORK)]
    assert [(c.name, c.ok) for c in sources] == [
        ("cookies file", True),
        ("browser chrome", False),
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
    """Check that when every source fails the exit code is 4 and the export hint is shown."""
    checks = await run_doctor(
        sources={
            "cookies file": BadSource(message="The cookies file is not set."),
            "browser edge": BadSource(),
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
    """Check that signing in without a working chat gives exit code 3."""
    checks = await run_doctor(
        sources={"cookies file": GoodSource()},
        make_ask=ask_factory(outcome=ChatUnavailableError(message="Чат недоступен для этого видео.")),
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
    """Check that a stale first source is skipped in favour of the next one."""

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
        sources={"cookies file": Stale(), "browser firefox": GoodSource()},
        make_ask=StaleAware,
        test_video_id="abcdefghijk",
    )
    assert not by_name(
        checks=checks,
        name="cookies file",
    ).ok
    assert by_name(
        checks=checks,
        name="browser firefox",
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
    """Check that when every loaded source is stale the exit code is 4."""
    checks = await run_doctor(
        sources={"cookies file": GoodSource()},
        make_ask=ask_factory(outcome=AuthError(message="cookies устарели")),
        test_video_id="abcdefghijk",
    )
    assert not by_name(
        checks=checks,
        name=LOGIN,
    ).ok
    assert doctor_exit_code(checks=checks) == 4


async def test_network_failure_is_exit_6():
    """Check that a network failure gives exit code 6."""
    checks = await run_doctor(
        sources={"cookies file": GoodSource()},
        make_ask=ask_factory(outcome=NetworkError(message="сеть")),
        test_video_id="abcdefghijk",
    )
    assert not by_name(
        checks=checks,
        name=NETWORK,
    ).ok
    assert doctor_exit_code(checks=checks) == 6


async def test_source_read_once():
    """Check that each cookie source is read only once."""
    source = GoodSource()
    await run_doctor(
        sources={"cookies file": source},
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    assert source.loads == 1


async def test_checks_never_contain_cookie_values():
    """Check that the check rows never contain cookie values."""
    for outcome in (
        None,
        ChatUnavailableError(message="нет чата"),
        AuthError(message="нет входа"),
        NetworkError(message="сеть"),
    ):
        checks = await run_doctor(
            sources={"cookies file": GoodSource(), "browser chrome": BadSource()},
            make_ask=ask_factory(outcome=outcome),
            test_video_id="abcdefghijk",
        )
        text = repr(checks)
        assert SECRET_SAPISID not in text and SECRET_SID not in text


# --- command ---


class Harness:
    """Test harness that runs the doctor command with fake sources and a fake chat."""

    def __init__(
        self,
        tmp_path: Path,
        sources: dict,
        outcome=None,
        settings: Settings | None = None,
    ) -> None:
        """Create the harness with the given sources and chat outcome.

        Args:
            tmp_path: Temporary folder of the test.
            sources: Cookie sources by name.
            outcome: Exception that the fake chat raises on open, or None.
            settings: Settings to use, or None for the defaults.
        """
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
        """Build the application context for one run with the fakes.

        Args:
            out: Stream for the result.
            err: Stream for messages.

        Returns:
            The application context.
        """
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
        """Run the doctor command with the harness wiring.

        Args:
            *argv: Command-line arguments after ``doctor``.

        Returns:
            The exit code, the result text and the message text.
        """
        out, err = io.StringIO(), io.StringIO()
        code = cli.run(
            argv=["doctor", *argv],
            out=out,
            err=err,
            context_factory=self.factory,
        )
        return code, out.getvalue(), err.getvalue()


def test_doctor_command_success_prints_table(tmp_path):
    """Check that the doctor command prints the table when everything is ready."""
    h = Harness(
        tmp_path=tmp_path,
        sources={"cookies file": GoodSource(), "browser chrome": BadSource()},
    )
    code, out, err = h.run()
    assert code == 0, err
    assert "cookies file" in out and "browser chrome" in out and LOGIN in out and CHAT in out
    assert h.opened == [DEFAULT_TEST_VIDEO]
    assert SECRET_SAPISID not in out + err and SECRET_SID not in out + err


def test_doctor_command_all_sources_fail_exit_4(tmp_path):
    """Check that the doctor command exits with code 4 when all sources fail."""
    h = Harness(
        tmp_path=tmp_path,
        sources={
            "cookies file": BadSource(message="The cookies file is not set."),
            "browser chrome": BadSource(),
        },
    )
    code, out, err = h.run()
    assert code == 4
    assert "--cookies-file" in err
    assert "lingotube login" in err
    assert h.opened == []


def test_doctor_command_chat_unavailable_exit_3(tmp_path):
    """Check that the doctor command exits with code 3 when the chat is unavailable."""
    h = Harness(
        tmp_path=tmp_path,
        sources={"cookies file": GoodSource()},
        outcome=ChatUnavailableError(message="Чат недоступен."),
    )
    code, out, err = h.run()
    assert code == 3
    assert "Чат недоступен." in out
    assert "--video" in err


def test_doctor_command_json(tmp_path):
    """Check the JSON output of the doctor command."""
    h = Harness(
        tmp_path=tmp_path,
        sources={"cookies file": GoodSource()},
        outcome=ChatUnavailableError(message="Чат недоступен."),
    )
    code, out, _ = h.run("--json")
    assert code == 3
    doc = json.loads(s=out)
    assert doc["ok"] is False and doc["error"]["code"] == "chat_unavailable"
    assert doc["result"]["video_id"] == DEFAULT_TEST_VIDEO
    names = [c["name"] for c in doc["result"]["checks"]]
    assert names == ["cookies file", LOGIN, CHAT]
    assert SECRET_SAPISID not in out and SECRET_SID not in out


def test_doctor_command_json_unexpected_source_row_is_neutral_for_exit(tmp_path):
    """Check that an unexpected failure in one source does not change the exit code in JSON output."""
    h = Harness(
        tmp_path=tmp_path,
        sources={"cookies file": CrashingSource(), "browser chrome": GoodSource()},
    )
    code, out, _ = h.run("--json")
    assert code == 0
    doc = json.loads(s=out)
    assert doc["ok"] is True and doc.get("error") is None
    row = doc["result"]["checks"][0]
    assert row["name"] == "cookies file" and row["ok"] is False
    assert "RuntimeError" in row["detail"] and SECRET_SAPISID not in out


@pytest.mark.parametrize(
    argnames="arg",
    argvalues=["-n5MqamatXE", "https://youtu.be/-n5MqamatXE", "abcdefghijk"],
)
def test_doctor_video_option(
    tmp_path,
    arg,
):
    """Check that the video option chooses the video for the chat check."""
    h = Harness(
        tmp_path=tmp_path,
        sources={"cookies file": GoodSource()},
    )
    code, _, err = h.run(
        "--video",
        arg,
    )
    assert code == 0, err
    assert h.opened == [arg[-11:]]


def test_doctor_bad_video_option_fails_before_network(tmp_path):
    """Check that an invalid video option fails before any network request."""
    h = Harness(
        tmp_path=tmp_path,
        sources={"cookies file": GoodSource()},
    )
    code, _, _ = h.run(
        "--video",
        "https://example.com/x",
    )
    assert code == 7
    assert h.opened == []


async def test_container_doctor_sources(tmp_path):
    """Check the cookie sources that the container gives to doctor."""

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
        "cookies file",
        "login profile",
        *[f"browser {b}" for b in BROWSERS],
    ]
    with pytest.raises(expected_exception=AuthError) as unset_login:
        await plain["login profile"].load()
    assert unset_login.value.hint == LOGIN_HINT
    with pytest.raises(expected_exception=AuthError) as info:
        await plain["cookies file"].load()
    assert "--cookies-file" in (info.value.hint or "")

    chosen = make(
        settings=Settings(
            cookies_file=tmp_path / "c.txt",
            browser="firefox",
        )
    ).doctor_sources()
    assert list(chosen) == ["cookies file", "login profile", "browser firefox"]

    loaded: list[str] = []

    def loader(browser):
        loaded.append(browser)
        return {"SAPISID": "x"}

    container = make(settings=Settings(browser="edge"))
    container.browser_loader.override(provider=providers.Object(loader))
    creds = await container.doctor_sources()["browser edge"].load()
    assert creds.sapisid() == "x" and loaded == ["edge"]


async def test_container_ask_factory_builds_youtube_clients(tmp_path):
    """Check that the container's factory builds YouTube chat clients."""
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
    """Check that the doctor command is registered in the CLI."""
    import typer.main

    app = cli.build_app(
        registry=cli.build_registry(),
        get_context=lambda: None,
    )  # type: ignore[arg-type, return-value]
    assert "doctor" in typer.main.get_command(typer_instance=app).commands  # type: ignore[attr-defined]


def test_table_lists_hints_of_failed_checks_once():
    """Check that the table lists the hint of each failed check once."""
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
    """Check that failed browser checks are not critical when another source works."""
    from lingotube.doctor import render_table

    checks = await run_doctor(
        sources={"cookies file": GoodSource(), "browser chrome": BadSource()},
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    chrome = by_name(
        checks=checks,
        name="browser chrome",
    )
    assert not chrome.ok and not chrome.critical
    text = render_table(
        checks=checks,
        error=None,
    )
    assert "error" not in text
    chrome_row = next(line for line in text.splitlines() if line.startswith("browser chrome"))
    assert chrome_row.split()[2:5] == ["not", "read", "The"]
    assert "Hints" not in text and "cookies.txt" not in text
    assert doctor_exit_code(checks=checks) == 0


async def test_stale_source_is_reported_as_not_accepted_not_as_unread():
    """Check that a stale source is reported as not accepted, not as unread."""
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
        sources={"cookies file": Stale(), "browser firefox": GoodSource()},
        make_ask=StaleAware,
        test_video_id="abcdefghijk",
    )
    text = render_table(checks=checks, error=None)
    row = next(line for line in text.splitlines() if line.startswith("cookies file"))
    assert "not accepted" in row and "not read" not in row


async def test_failed_sources_stay_critical_when_none_works():
    """Check that failed sources stay critical when no source works."""
    from lingotube.doctor import doctor_error, render_table

    checks = await run_doctor(
        sources={"cookies file": BadSource(), "browser edge": BadSource()},
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    assert all(c.critical for c in checks)
    text = render_table(
        checks=checks,
        error=doctor_error(checks=checks),
    )
    assert "error" in text and "Hints" in text
    assert doctor_exit_code(checks=checks) == 4


async def test_network_error_does_not_claim_missing_login():
    """Check that a network error does not claim the sign-in is missing."""
    from lingotube.doctor import NETWORK_HINT

    checks = await run_doctor(
        sources={"cookies file": GoodSource()},
        make_ask=ask_factory(outcome=NetworkError(message="сеть")),
        test_video_id="abcdefghijk",
    )
    for name in (LOGIN, CHAT):
        detail = by_name(
            checks=checks,
            name=name,
        ).detail
        assert "not signed in" not in detail
        assert "connection" in detail
    assert NETWORK_HINT in (
        by_name(
            checks=checks,
            name=NETWORK,
        ).hint
        or ""
    )
    assert doctor_exit_code(checks=checks) == 6


class CrashingSource:
    """Cookie source whose load raises an unexpected error."""

    async def load(self) -> Credentials:
        """Raise an unexpected error.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError(f"boom {SECRET_SAPISID}")


async def test_unexpected_error_in_source_keeps_row_failed_but_exit_0_when_another_works():
    """Check that an unexpected error in a source keeps its row failed, but exit code is 0 when another source works."""
    checks = await run_doctor(
        sources={"cookies file": CrashingSource(), "browser chrome": GoodSource()},
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    row = by_name(
        checks=checks,
        name="cookies file",
    )
    assert not row.ok and row.critical
    assert "RuntimeError" in row.detail
    assert SECRET_SAPISID not in repr(checks)
    assert by_name(
        checks=checks,
        name="browser chrome",
    ).ok
    assert doctor_exit_code(checks=checks) == 0
    from lingotube.doctor import render_table

    assert "error" in render_table(checks=checks)


async def test_unexpected_error_without_a_working_source_still_exits_1():
    """Check that an unexpected error without a working source gives exit code 1."""
    checks = await run_doctor(
        sources={"cookies file": CrashingSource()},
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    assert doctor_exit_code(checks=checks) == 1


async def test_unexpected_error_in_chat_open_marks_row_failed_and_exit_1():
    """Check that an unexpected error while opening the chat marks the row failed and gives exit code 1."""
    checks = await run_doctor(
        sources={"cookies file": GoodSource()},
        make_ask=ask_factory(outcome=KeyError(SECRET_SID)),
        test_video_id="abcdefghijk",
    )
    row = by_name(
        checks=checks,
        name="cookies file",
    )
    assert not row.ok and "KeyError" in row.detail
    assert SECRET_SID not in repr(checks)
    assert doctor_exit_code(checks=checks) == 1


def test_doctor_command_unexpected_error_still_prints_table(tmp_path):
    """Check that the table is still printed after an unexpected error."""
    h = Harness(
        tmp_path=tmp_path,
        sources={"cookies file": CrashingSource(), "browser chrome": GoodSource()},
    )
    code, out, err = h.run()
    assert code == 0
    assert "cookies file" in out and "RuntimeError" in out and LOGIN in out
    assert SECRET_SAPISID not in out + err


async def test_doctor_lists_login_profile_row_after_file(tmp_path):
    """Check that the login profile row comes after the file row."""
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
    assert list(sources)[:2] == ["cookies file", "login profile"]
    assert (await sources["login profile"].load()).sapisid() == SECRET_SAPISID


async def test_doctor_never_refreshes_the_login_profile(tmp_path, monkeypatch):
    """Check that doctor never refreshes the login profile."""
    await LoginCookieStore(cookies_file=tmp_path / "login-cookies.json").write(
        saved=SavedLogin(browser="chrome", cookies={"SAPISID": SECRET_SAPISID})
    )

    async def refresh_is_forbidden(self):
        raise AssertionError("doctor must not start the login browser")

    monkeypatch.setattr(LoginProfileCookieSource, "refresh_from_profile", refresh_is_forbidden)
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
    checks = await run_doctor(
        sources={"login profile": container.doctor_sources()["login profile"]},
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    assert by_name(checks=checks, name="login profile").ok


async def test_doctor_login_profile_works_marks_others_non_critical():
    """Check that when the login profile works, the other failed sources are not critical."""
    checks = await run_doctor(
        sources={
            "cookies file": BadSource(),
            "login profile": GoodSource(),
            "browser chrome": BadSource(),
        },
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    assert by_name(checks=checks, name="login profile").ok
    assert not by_name(checks=checks, name="cookies file").critical
    assert not by_name(checks=checks, name="browser chrome").critical
    assert doctor_exit_code(checks=checks) == 0


async def test_final_error_hint_starts_with_login_hint():
    """Check that the hint of the final error starts with the login hint."""
    from lingotube.doctor import doctor_error

    checks = await run_doctor(
        sources={"cookies file": BadSource(), "login profile": BadSource()},
        make_ask=ask_factory(),
        test_video_id="abcdefghijk",
    )
    error = doctor_error(checks=checks)
    assert isinstance(error, AuthError)
    assert (error.hint or "").startswith(LOGIN_HINT)
    assert "--cookies-file" in (error.hint or "")


async def test_signed_in_but_youtube_changed_is_structural_chat_failure():
    """Check that a changed YouTube page is flagged as structural, not as an ordinary chat failure."""
    checks = await run_doctor(
        sources={"cookies file": GoodSource()},
        make_ask=ask_factory(outcome=YouTubeChangedError(message="Could not read the YouTube watch page.")),
        test_video_id="abcdefghijk",
    )
    chat = by_name(checks=checks, name=CHAT)
    assert not chat.ok
    assert chat.structural
    assert chat.hint == YOUTUBE_CHANGED_HINT


def test_doctor_command_youtube_changed_exit_8(tmp_path):
    """Check that the doctor command exits with code 8 and the update hint when YouTube changed."""
    h = Harness(
        tmp_path=tmp_path,
        sources={"cookies file": GoodSource()},
        outcome=YouTubeChangedError(message="Could not read the YouTube watch page."),
    )
    code, out, err = h.run()
    assert code == 8
    assert YOUTUBE_CHANGED_HINT in out + err
