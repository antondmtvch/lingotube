"""`doctor`: is everything ready? Cookie sources, sign-in, chat on a test video.

The chat is checked with `AskClient.open()` only — never `ask()` — so no message
lands in the user's chat history. Checks carry only our own messages: never cookie
values, tokens or exception texts.
"""

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass

from lingotube.ask.client import AskClient
from lingotube.auth.base import EXPORT_HINT, CookieSource, Credentials
from lingotube.errors import AuthError, ChatUnavailableError, LingotubeError, NetworkError

DEFAULT_TEST_VIDEO = "-n5MqamatXE"  # public video with the chat confirmed by the probe
FILE_SOURCE = "файл cookies"
LOGIN = "вход в аккаунт"
CHAT = "чат на тестовом видео"
NETWORK = "соединение с YouTube"

CHAT_HINT = (
    "Чат доступен не во всех странах (например, нет в России и большей части ЕС), только "
    "аккаунтам 13+ и, по имеющимся данным, не брендовым аккаунтам. Если дело в видео — "
    "проверьте на другом: lingotube doctor --video <ссылка>."
)
COOKIES_FILE_HINT = "Надёжный путь — файл cookies.txt. " + EXPORT_HINT
NETWORK_HINT = "Проверьте подключение к интернету и повторите позже."


def browser_source_name(browser: str) -> str:
    return f"браузер {browser}"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    hint: str | None


class UnsetCookieFile:
    """The file source when no cookies file is configured."""

    async def load(self) -> Credentials:
        raise AuthError("Файл cookies не задан.", EXPORT_HINT)


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
            checks.append(Check(name, False, e.message, e.hint))
            continue
        checks.append(Check(name, True, "cookies прочитаны", None))
        loaded.append((len(checks) - 1, name, creds))

    login: Check | None = None
    chat: Check | None = None
    for index, name, creds in loaded:
        try:
            await make_ask(_Loaded(creds)).open(test_video_id)
        except AuthError as e:  # stale cookies: try the next source
            checks[index] = Check(name, False, f"cookies прочитаны, но YouTube их не принял: {e.message}", e.hint)
            continue
        except ChatUnavailableError as e:
            login = Check(LOGIN, True, f"вход выполнен ({name})", None)
            chat = Check(CHAT, False, e.message, e.hint or CHAT_HINT)
        except NetworkError as e:
            checks.append(Check(NETWORK, False, e.message, e.hint or NETWORK_HINT))
            login = Check(LOGIN, False, "не проверен: нет соединения с YouTube", None)
        else:
            checks[index] = Check(name, True, "cookies прочитаны, вход выполнен", None)
            login = Check(LOGIN, True, f"вход выполнен ({name})", None)
            chat = Check(CHAT, True, f"чат доступен на видео {test_video_id}", None)
        break

    if login is None:
        detail = (
            "cookies прочитаны, но YouTube не видит вход: они устарели или выгружены без входа"
            if loaded
            else "нет ни одного рабочего источника cookies"
        )
        login = Check(LOGIN, False, detail, EXPORT_HINT)
    checks.append(login)
    checks.append(chat or Check(CHAT, False, "не проверен: нет входа в аккаунт", None))
    return checks


def _failed(checks: list[Check], name: str) -> bool:
    return any(c.name == name and not c.ok for c in checks)


def _passed(checks: list[Check], name: str) -> bool:
    return any(c.name == name and c.ok for c in checks)


def doctor_error(checks: list[Check]) -> LingotubeError | None:
    """None when ready; otherwise the error whose exit code `doctor` ends with."""
    if _passed(checks, CHAT):
        return None
    if _failed(checks, NETWORK):
        return NetworkError("Не удалось связаться с YouTube.", hint=NETWORK_HINT)
    if _passed(checks, LOGIN):
        return ChatUnavailableError("Вход выполнен, но чат YouTube на тестовом видео недоступен.", hint=CHAT_HINT)
    return AuthError("Ни один источник cookies не дал входа в YouTube.", hint=COOKIES_FILE_HINT)


def doctor_exit_code(checks: list[Check]) -> int:
    error = doctor_error(checks)
    return 0 if error is None else error.exit_code


def render_table(checks: list[Check], error: LingotubeError | None = None) -> str:
    """The checks as a table, then the distinct hints of failed checks (the final
    error's own hint is printed with the error)."""
    rows = [("ПРОВЕРКА", "ИТОГ", "ПОДРОБНОСТИ")] + [
        (c.name, "ок" if c.ok else "ошибка", c.detail) for c in checks
    ]
    w0 = max(len(r[0]) for r in rows)
    w1 = max(len(r[1]) for r in rows)
    lines = [f"{a.ljust(w0)}  {b.ljust(w1)}  {c}".rstrip() for a, b, c in rows]
    hints: list[str] = []
    for check in checks:
        if not check.ok and check.hint and check.hint not in hints and (error is None or check.hint != error.hint):
            hints.append(check.hint)
    if hints:
        lines += ["", "Подсказки:", *(f"- {hint}" for hint in hints)]
    return "\n".join(lines) + "\n"


def register(app, get_context) -> None:
    """Adds the `doctor` command: a table of checks; exit 0 / 3 (chat) / 4 (cookies) / 6 (network)."""
    from typing import Annotated

    import typer

    from lingotube import commands as c

    VideoOpt = Annotated[
        str,
        typer.Option("--video", help="Видео для проверки чата (ссылка или идентификатор)."),
    ]

    @app.command("doctor", help="Проверка готовности: cookies, вход в аккаунт, чат на тестовом видео.")
    def doctor(
        video: VideoOpt = DEFAULT_TEST_VIDEO,
        cookies_file: c.CookiesFileOpt = None,
        browser: c.BrowserOpt = None,
        json_: c.JsonOpt = False,
    ) -> None:
        common = c.Common(json_, cookies_file, browser)

        async def body(ctx: c.AppContext, video_id: str | None) -> c.Outcome:
            assert video_id is not None  # parsed by `execute` before any network
            sources = await ctx.provide(ctx.container.doctor_sources)
            make_ask = await ctx.provide(ctx.container.ask_factory)
            checks = await run_doctor(sources, make_ask, video_id)
            result = {"video_id": video_id, "checks": [asdict(check) for check in checks]}
            error = doctor_error(checks)
            return c.Outcome(result, text=render_table(checks, error), error=error)

        c.execute(get_context, common, video, body)
