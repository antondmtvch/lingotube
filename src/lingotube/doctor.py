"""`doctor`: is everything ready? Cookie sources, sign-in, chat on a test video.

The chat is checked with `AskClient.open()` only — never `ask()` — so no message
lands in the user's chat history. Checks carry only our own messages: never cookie
values, tokens or exception texts.
"""

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace

from lingotube.ask.client import AskClient
from lingotube.auth.base import EXPORT_HINT, LOGIN_HINT, CookieSource, Credentials
from lingotube.errors import (
    YOUTUBE_CHANGED_HINT,
    AuthError,
    ChatUnavailableError,
    LingotubeError,
    NetworkError,
    YouTubeChangedError,
)

DEFAULT_TEST_VIDEO = "-n5MqamatXE"  # public video with the chat confirmed by the probe
FILE_SOURCE = "cookies file"
LOGIN_PROFILE_SOURCE = "login profile"
LOGIN = "account sign-in"
CHAT = "chat on the test video"
NETWORK = "connection to YouTube"

CHAT_HINT = (
    "The chat is not available in every country (for example, not in Russia or most of the EU), only "
    "accounts aged 13+ and, as far as is known, not brand accounts. If the problem is the video, "
    "try another one: lingotube doctor --video <link>."
)
NETWORK_HINT = "Check the internet connection and try again later."


def browser_source_name(browser: str) -> str:
    """Return the name of the cookie source for a browser.

    Args:
        browser: Browser name.

    Returns:
        The name shown in the doctor table.
    """
    return f"browser {browser}"


@dataclass(frozen=True)
class Check:
    """One row of the doctor table.

    Attributes:
        name: Name of the check.
        ok: True if the check passed.
        detail: Short result text. It never contains secrets.
        hint: Advice on how to fix a failure, or None.
        critical: False if the check failed but another source works, so it is not an error.
        unexpected: True if the check itself crashed. That is a bug, not a user problem.
        soft_verdict: Word shown for a failure that is not critical.
    """

    name: str
    ok: bool
    detail: str
    hint: str | None
    critical: bool = True  # False: failed, but another source works, so not an error
    unexpected: bool = False  # the check itself crashed (a bug, not a user problem)
    structural: bool = False  # YouTube changed the page or response (exit 8, not exit 3)
    soft_verdict: str = "not read"  # the word shown when a failure is not critical


def _crashed(
    name: str,
    error: Exception,
) -> Check:
    return Check(
        name=name,
        ok=False,
        detail=f"the check failed with an unexpected error ({type(error).__name__})",
        hint=None,
        unexpected=True,
    )


class UnsetCookieFile:
    """The file source when no cookies file is configured."""

    async def load(self) -> Credentials:
        """Fail, because no cookies file is configured.

        Raises:
            AuthError: Always.
        """
        raise AuthError(
            message="The cookies file is not set.",
            hint=EXPORT_HINT,
        )


class UnsetLoginProfile:
    """The login-profile source when `lingotube login` was never run."""

    async def load(self) -> Credentials:
        """Fail, because ``lingotube login`` was never run.

        Raises:
            AuthError: Always.
        """
        raise AuthError(
            message="lingotube login was not run.",
            hint=LOGIN_HINT,
        )


class _Loaded:
    """Credentials already read: the chat check does not read the source again."""

    def __init__(self, creds: Credentials) -> None:
        """Wrap credentials that were already read.

        Args:
            creds: Credentials to return.
        """
        self._creds = creds

    async def load(self) -> Credentials:
        """Return the stored credentials without reading the source again.

        Returns:
            The stored credentials.
        """
        return self._creds


async def run_doctor(
    sources: Mapping[str, CookieSource],
    make_ask: Callable[[CookieSource], AskClient],
    test_video_id: str,
) -> list[Check]:
    """Run every check and return the rows of the table.

    Each source is loaded first. Then the chat is tried with the sources in turn, and the
    first source that works is used. The chat check only opens the chat and never sends a
    question.

    Args:
        sources: Cookie sources by check name.
        make_ask: Function that builds a chat client for a cookie source.
        test_video_id: Video used for the chat check.

    Returns:
        The check rows, in order.
    """
    checks: list[Check] = []
    loaded: list[tuple[int, str, Credentials]] = []
    for name, source in sources.items():
        try:
            creds = await source.load()
        except AuthError as e:
            checks.append(
                Check(
                    name=name,
                    ok=False,
                    detail=e.message,
                    hint=e.hint,
                )
            )
            continue
        except Exception as e:  # never the text: it may hold secrets
            checks.append(
                _crashed(
                    name=name,
                    error=e,
                )
            )
            continue
        checks.append(
            Check(
                name=name,
                ok=True,
                detail="cookies read",
                hint=None,
            )
        )
        loaded.append((len(checks) - 1, name, creds))

    login: Check | None = None
    chat: Check | None = None
    network_down = False
    for index, name, creds in loaded:
        try:
            await make_ask(_Loaded(creds=creds)).open(video_id=test_video_id)
        except AuthError as e:  # stale cookies: try the next source
            checks[index] = Check(
                name=name,
                ok=False,
                detail=f"cookies read, but YouTube did not accept them: {e.message}",
                hint=e.hint,
                soft_verdict="not accepted",
            )
            continue
        except ChatUnavailableError as e:
            login = Check(
                name=LOGIN,
                ok=True,
                detail=f"signed in ({name})",
                hint=None,
            )
            chat = Check(
                name=CHAT,
                ok=False,
                detail=e.message,
                hint=e.hint or CHAT_HINT,
            )
        except YouTubeChangedError as e:
            login = Check(
                name=LOGIN,
                ok=True,
                detail=f"signed in ({name})",
                hint=None,
            )
            chat = Check(
                name=CHAT,
                ok=False,
                detail=e.message,
                hint=e.hint,
                structural=True,
            )
        except NetworkError as e:
            network_down = True
            checks.append(
                Check(
                    name=NETWORK,
                    ok=False,
                    detail=e.message,
                    hint=e.hint or NETWORK_HINT,
                )
            )
            login = Check(
                name=LOGIN,
                ok=False,
                detail="not checked: no connection to YouTube",
                hint=None,
            )
        except Exception as e:  # unexpected: record it and try the next source
            checks[index] = _crashed(
                name=name,
                error=e,
            )
            continue
        else:
            checks[index] = Check(
                name=name,
                ok=True,
                detail="cookies read, sign-in successful",
                hint=None,
            )
            login = Check(
                name=LOGIN,
                ok=True,
                detail=f"signed in ({name})",
                hint=None,
            )
            chat = Check(
                name=CHAT,
                ok=True,
                detail=f"chat available on the video {test_video_id}",
                hint=None,
            )
        break

    if login is None:
        detail = (
            "cookies read, but YouTube does not see a sign-in: they are stale or were exported without signing in"
            if loaded
            else "no working cookies source"
        )
        login = Check(
            name=LOGIN,
            ok=False,
            detail=detail,
            hint=EXPORT_HINT,
        )
    checks.append(login)
    checks.append(
        chat
        or Check(
            name=CHAT,
            ok=False,
            detail=("not checked: no connection to YouTube" if network_down else "not checked: not signed in"),
            hint=None,
        )
    )
    if login.ok:  # some source works: the other sources failing is not an error
        checks = [
            (
                replace(
                    c,
                    critical=False,
                )
                if c.name in sources and not c.ok and not c.unexpected
                else c
            )
            for c in checks
        ]
    return checks


def _failed(
    checks: list[Check],
    name: str,
) -> bool:
    return any(c.name == name and not c.ok for c in checks)


def _passed(
    checks: list[Check],
    name: str,
) -> bool:
    return any(c.name == name and c.ok for c in checks)


def doctor_error(checks: list[Check]) -> LingotubeError | None:
    """Return the error that decides the exit code of ``doctor``.

    Args:
        checks: Check rows of the run.

    Returns:
        None if the chat works. Otherwise the error that the command ends with.
    """
    if _passed(
        checks=checks,
        name=CHAT,
    ):
        return None  # a source works and the chat is reachable: a crashed row is not fatal
    if any(c.unexpected for c in checks):
        return LingotubeError(
            message="One of the checks failed with an unexpected error.",
            hint="Run the command again; if the error repeats, report it.",
        )
    if _failed(
        checks=checks,
        name=NETWORK,
    ):
        return NetworkError(
            message="Could not reach YouTube.",
            hint=NETWORK_HINT,
        )
    if any(c.structural for c in checks):
        return YouTubeChangedError(
            message="YouTube changed the format lingotube reads.",
            hint=YOUTUBE_CHANGED_HINT,
        )
    if _passed(
        checks=checks,
        name=LOGIN,
    ):
        return ChatUnavailableError(
            message="Signed in, but the YouTube chat is unavailable on the test video.",
            hint=CHAT_HINT,
        )
    return AuthError(
        message="No cookies source gave a sign-in to YouTube.",
        hint=EXPORT_HINT,
    )


def doctor_exit_code(checks: list[Check]) -> int:
    """Return the process exit code for the check rows.

    Args:
        checks: Check rows of the run.

    Returns:
        0 if everything is ready, otherwise the exit code of the error.
    """
    error = doctor_error(checks=checks)
    return 0 if error is None else error.exit_code


def _verdict(check: Check) -> str:
    if check.ok:
        return "ok"
    return "error" if check.critical else check.soft_verdict


def render_table(
    checks: list[Check],
    error: LingotubeError | None = None,
) -> str:
    """Render the checks as a text table, followed by the hints of the failed checks.

    The hint of the final error is left out, because the error prints it itself.

    Args:
        checks: Check rows of the run.
        error: The final error, or None.

    Returns:
        The text of the report.
    """
    rows = [("CHECK", "RESULT", "DETAILS")] + [(c.name, _verdict(check=c), c.detail) for c in checks]
    w0 = max(len(r[0]) for r in rows)
    w1 = max(len(r[1]) for r in rows)
    lines = [f"{a.ljust(w0)}  {b.ljust(w1)}  {c}".rstrip() for a, b, c in rows]
    hints: list[str] = []
    for check in checks:
        if (
            not check.ok
            and check.critical
            and check.hint
            and check.hint not in hints
            and (error is None or check.hint != error.hint)
        ):
            hints.append(check.hint)
    if hints:
        lines += ["", "Hints:", *(f"- {hint}" for hint in hints)]
    return "\n".join(lines) + "\n"


def register(
    app,
    get_context,
) -> None:
    """Add the ``doctor`` command to the CLI application.

    The command prints a table of checks. Exit codes: 0 when ready, 3 for the chat,
    4 for the cookies, 6 for the network.

    Args:
        app: Typer application.
        get_context: Function that returns the shared context of the command.
    """
    from typing import Annotated

    import typer

    from lingotube import commands as c

    VideoOpt = Annotated[
        str,
        typer.Option(
            default="--video",
            help="Video to check the chat with (link or id).",
        ),
    ]

    @app.command(
        name="doctor",
        help="Readiness check: cookies, account sign-in, chat on the test video.",
    )
    def doctor(
        video: VideoOpt = DEFAULT_TEST_VIDEO,
        cookies_file: c.CookiesFileOpt = None,
        browser: c.BrowserOpt = None,
        json_: c.JsonOpt = False,
    ) -> None:
        common = c.Common(
            json=json_,
            cookies_file=cookies_file,
            browser=browser,
        )

        async def body(
            ctx: c.AppContext,
            video_id: str | None,
        ) -> c.Outcome:
            assert video_id is not None  # parsed by `execute` before any network
            sources = await ctx.provide(provider=ctx.container.doctor_sources)
            make_ask = await ctx.provide(provider=ctx.container.ask_factory)
            checks = await run_doctor(
                sources=sources,
                make_ask=make_ask,
                test_video_id=video_id,
            )
            result = {
                "video_id": video_id,
                "checks": [asdict(obj=check) for check in checks],
            }
            error = doctor_error(checks=checks)
            return c.Outcome(
                result=result,
                text=render_table(
                    checks=checks,
                    error=error,
                ),
                error=error,
            )

        c.execute(
            get_context=get_context,
            common=common,
            video=video,
            body=body,
        )
