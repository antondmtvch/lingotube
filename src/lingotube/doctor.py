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
    AuthError,
    ChatUnavailableError,
    LingotubeError,
    NetworkError,
)

DEFAULT_TEST_VIDEO = "-n5MqamatXE"  # public video with the chat confirmed by the probe
FILE_SOURCE = "файл cookies"
LOGIN_PROFILE_SOURCE = "профиль входа"
LOGIN = "вход в аккаунт"
CHAT = "чат на тестовом видео"
NETWORK = "соединение с YouTube"

CHAT_HINT = (
    "Чат доступен не во всех странах (например, нет в России и большей части ЕС), только "
    "аккаунтам 13+ и, по имеющимся данным, не брендовым аккаунтам. Если дело в видео — "
    "проверьте на другом: lingotube doctor --video <ссылка>."
)
NETWORK_HINT = "Проверьте подключение к интернету и повторите позже."


def browser_source_name(browser: str) -> str:
    return f"браузер {browser}"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    hint: str | None
    critical: bool = True  # False: failed, but another source works, so not an error
    unexpected: bool = False  # the check itself crashed (a bug, not a user problem)
    soft_verdict: str = "не прочитан"  # the word shown when a failure is not critical


def _crashed(
    name: str,
    error: Exception,
) -> Check:
    return Check(
        name=name,
        ok=False,
        detail=f"проверка завершилась неожиданной ошибкой ({type(error).__name__})",
        hint=None,
        unexpected=True,
    )


class UnsetCookieFile:
    """The file source when no cookies file is configured."""

    async def load(self) -> Credentials:
        raise AuthError(
            message="Файл cookies не задан.",
            hint=EXPORT_HINT,
        )


class UnsetLoginProfile:
    """The login-profile source when `lingotube login` was never run."""

    async def load(self) -> Credentials:
        raise AuthError(
            message="Вход через lingotube login не выполнялся.",
            hint=LOGIN_HINT,
        )


class _Loaded:
    """Credentials already read: the chat check does not read the source again."""

    def __init__(self, creds: Credentials) -> None:
        self._creds = creds

    async def load(self) -> Credentials:
        return self._creds


async def run_doctor(
    sources: Mapping[str, CookieSource],
    make_ask: Callable[[CookieSource], AskClient],
    test_video_id: str,
) -> list[Check]:
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
                detail="cookies прочитаны",
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
                detail=f"cookies прочитаны, но YouTube их не принял: {e.message}",
                hint=e.hint,
                soft_verdict="не принят",
            )
            continue
        except ChatUnavailableError as e:
            login = Check(
                name=LOGIN,
                ok=True,
                detail=f"вход выполнен ({name})",
                hint=None,
            )
            chat = Check(
                name=CHAT,
                ok=False,
                detail=e.message,
                hint=e.hint or CHAT_HINT,
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
                detail="не проверен: нет соединения с YouTube",
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
                detail="cookies прочитаны, вход выполнен",
                hint=None,
            )
            login = Check(
                name=LOGIN,
                ok=True,
                detail=f"вход выполнен ({name})",
                hint=None,
            )
            chat = Check(
                name=CHAT,
                ok=True,
                detail=f"чат доступен на видео {test_video_id}",
                hint=None,
            )
        break

    if login is None:
        detail = (
            "cookies прочитаны, но YouTube не видит вход: они устарели или выгружены без входа"
            if loaded
            else "нет ни одного рабочего источника cookies"
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
            detail=("не проверен: нет соединения с YouTube" if network_down else "не проверен: нет входа в аккаунт"),
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
    """None when ready; otherwise the error whose exit code `doctor` ends with."""
    if _passed(
        checks=checks,
        name=CHAT,
    ):
        return None  # a source works and the chat is reachable: a crashed row is not fatal
    if any(c.unexpected for c in checks):
        return LingotubeError(
            message="Одна из проверок завершилась неожиданной ошибкой.",
            hint="Повторите команду; если ошибка повторяется — сообщите о ней.",
        )
    if _failed(
        checks=checks,
        name=NETWORK,
    ):
        return NetworkError(
            message="Не удалось связаться с YouTube.",
            hint=NETWORK_HINT,
        )
    if _passed(
        checks=checks,
        name=LOGIN,
    ):
        return ChatUnavailableError(
            message="Вход выполнен, но чат YouTube на тестовом видео недоступен.",
            hint=CHAT_HINT,
        )
    return AuthError(
        message="Ни один источник cookies не дал входа в YouTube.",
        hint=EXPORT_HINT,
    )


def doctor_exit_code(checks: list[Check]) -> int:
    error = doctor_error(checks=checks)
    return 0 if error is None else error.exit_code


def _verdict(check: Check) -> str:
    if check.ok:
        return "ок"
    return "ошибка" if check.critical else check.soft_verdict


def render_table(
    checks: list[Check],
    error: LingotubeError | None = None,
) -> str:
    """The checks as a table, then the distinct hints of failed checks (the final
    error's own hint is printed with the error)."""
    rows = [("ПРОВЕРКА", "ИТОГ", "ПОДРОБНОСТИ")] + [(c.name, _verdict(check=c), c.detail) for c in checks]
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
        lines += ["", "Подсказки:", *(f"- {hint}" for hint in hints)]
    return "\n".join(lines) + "\n"


def register(
    app,
    get_context,
) -> None:
    """Adds the `doctor` command: a table of checks; exit 0 / 3 (chat) / 4 (cookies) / 6 (network)."""
    from typing import Annotated

    import typer

    from lingotube import commands as c

    VideoOpt = Annotated[
        str,
        typer.Option(
            default="--video",
            help="Видео для проверки чата (ссылка или идентификатор).",
        ),
    ]

    @app.command(
        name="doctor",
        help="Проверка готовности: cookies, вход в аккаунт, чат на тестовом видео.",
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
