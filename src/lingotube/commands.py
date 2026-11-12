"""CLI plumbing shared by the feature commands.

Every command is a thin synchronous wrapper: it parses its options, then `execute`
runs the async body under `asyncio.run`, turns errors into exit codes and messages
(or one `--json` envelope) and always shuts the container's resources down.
"""

import asyncio
import inspect
import json
import math
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, TextIO

import typer
from dependency_injector import providers

from lingotube.auth.browser import BROWSERS
from lingotube.config import FORMATS, Settings, remember_cookies_file
from lingotube.errors import IncompleteError, LingotubeError, UsageError
from lingotube.features.transcript import TranscriptResult
from lingotube.models import Transcript
from lingotube.video import parse_video_id

if TYPE_CHECKING:
    from lingotube.container import Container

INTERRUPTED = 130


@dataclass
class AppContext:
    container: "Container"
    out: TextIO
    err: TextIO
    cwd: Path  # where default output files go and relative paths resolve
    settings_path: (
        Path | None
    )  # where --cookies-file is remembered (None: not remembered)
    json_mode: bool = False

    @property
    def settings(self) -> Settings:
        return self.container.settings()

    def use_settings(self, settings: Settings) -> None:
        self.container.settings.override(provider=providers.Object(settings))

    async def provide(self, provider: Callable[[], Any]) -> Any:
        """Resolves a provider; ones depending on async resources return awaitables."""
        value = provider()
        return await value if inspect.isawaitable(object=value) else value

    async def close(self) -> None:
        result = self.container.shutdown_resources()
        if inspect.isawaitable(object=result):
            await result

    def path(self, value: str | Path) -> Path:
        return self.cwd / Path(value)


@dataclass(frozen=True)
class Common:
    json: bool = False
    cookies_file: Path | None = None
    browser: str | None = None
    no_cache: bool = False

    @property
    def use_cache(self) -> bool:
        return not self.no_cache


@dataclass(frozen=True)
class Outcome:
    result: Any
    text: str | None = None  # what goes to `out` without --json
    warnings: tuple[str, ...] = ()
    error: LingotubeError | None = (
        None  # a result delivered with a problem (e.g. incomplete)
    )


Body = Callable[[AppContext, str | None], Awaitable[Outcome]]

# --- options shared by the commands (spec §6) ---

VideoArg = Annotated[
    str,
    typer.Argument(
        metavar="URL",
        help="Ссылка на видео YouTube или его идентификатор.",
        show_default=False,
    ),
]
LangOpt = Annotated[
    str | None,
    typer.Option(
        default="--lang",
        help="Язык результата (ru, en, es…); по умолчанию — из настроек.",
    ),
]
FormatOpt = Annotated[
    str | None,
    typer.Option(
        default="--format",
        help="Формат: srt, vtt или json.",
    ),
]
OutputOpt = Annotated[
    str | None,
    typer.Option(
        "-o",
        "--output",
        help="Куда писать; по умолчанию файл <id>.<язык>.<формат>; «-» — в stdout.",
    ),
]
OffsetOpt = Annotated[
    float,
    typer.Option(
        default="--offset",
        help="Сдвиг всех субтитров в секундах (можно дробный и отрицательный).",
    ),
]
CookiesFileOpt = Annotated[
    Path | None,
    typer.Option(
        default="--cookies-file",
        help="Файл cookies.txt (путь запоминается в настройках).",
    ),
]
BrowserOpt = Annotated[
    str | None,
    typer.Option(
        default="--browser",
        help=f"Браузер для cookies: {', '.join(BROWSERS)}.",
    ),
]
NoCacheOpt = Annotated[
    bool,
    typer.Option(
        default="--no-cache",
        help="Не использовать сохранённые результаты.",
    ),
]
JsonOpt = Annotated[
    bool,
    typer.Option(
        default="--json",
        help="Машинный вывод: один JSON-документ в stdout.",
    ),
]


# --- running a command ---


def execute(
    get_context: Callable[[], AppContext],
    common: Common,
    video: str | None,
    body: Body,
) -> None:
    ctx = get_context()
    ctx.json_mode = common.json
    try:
        code = asyncio.run(
            main=_execute(
                ctx=ctx,
                common=common,
                video=video,
                body=body,
            )
        )
    except KeyboardInterrupt:
        report(
            out=ctx.out,
            err=ctx.err,
            json_mode=ctx.json_mode,
            error=LingotubeError(message="Прервано."),
        )
        code = INTERRUPTED
    raise typer.Exit(code=code)


async def _execute(
    ctx: AppContext,
    common: Common,
    video: str | None,
    body: Body,
) -> int:
    try:
        try:
            video_id = (
                parse_video_id(value=video) if video is not None else None
            )  # before any network
            await _configure(
                ctx=ctx,
                common=common,
            )
            outcome = await body(
                ctx,
                video_id,
            )
        finally:
            await ctx.close()
    except LingotubeError as e:
        return report(
            out=ctx.out,
            err=ctx.err,
            json_mode=ctx.json_mode,
            error=e,
        )
    except (
        Exception
    ) as e:  # never a traceback, never the exception text (may hold secrets)
        error = LingotubeError(
            message=f"Внутренняя ошибка ({type(e).__name__}).",
            hint="Повторите команду; если ошибка повторяется — сообщите о ней.",
        )
        return report(
            out=ctx.out,
            err=ctx.err,
            json_mode=ctx.json_mode,
            error=error,
        )
    return report(
        out=ctx.out,
        err=ctx.err,
        json_mode=ctx.json_mode,
        result=outcome.result,
        text=outcome.text,
        warnings=outcome.warnings,
        error=outcome.error,
    )


async def _configure(
    ctx: AppContext,
    common: Common,
) -> None:
    """Applies --cookies-file / --browser over the settings; remembers a given cookies file."""
    if common.cookies_file is not None and common.browser is not None:
        raise UsageError(message="Укажите что-то одно: --cookies-file или --browser.")
    settings = ctx.settings
    cookies_file, browser = settings.cookies_file, settings.browser
    if common.cookies_file is not None:
        cookies_file, browser = ctx.path(value=common.cookies_file), None
    elif common.browser is not None:
        cookies_file, browser = None, common.browser
    elif cookies_file is not None:
        cookies_file = ctx.path(value=cookies_file)
    if browser is not None and browser not in BROWSERS:
        raise UsageError(
            message=f"Неизвестный браузер: {browser}.",
            hint=f"Доступны: {', '.join(BROWSERS)}.",
        )
    ctx.use_settings(
        settings=replace(
            settings,
            cookies_file=cookies_file,
            browser=browser,
        )
    )
    if (
        common.cookies_file is not None
        and cookies_file is not None
        and ctx.settings_path is not None
    ):
        if await asyncio.to_thread(cookies_file.is_file):
            await remember_cookies_file(
                path=cookies_file,
                settings_path=ctx.settings_path,
            )


def report(
    out: TextIO,
    err: TextIO,
    json_mode: bool,
    *,
    result: Any = None,
    text: str | None = None,
    warnings: tuple[str, ...] = (),
    error: LingotubeError | None = None,
) -> int:
    """Writes the outcome (one JSON envelope with --json) and returns the exit code."""
    if json_mode:
        envelope = {
            "ok": error is None,
            "result": result,
            "warnings": list(warnings),
            "error": (
                None
                if error is None
                else {"code": error.code, "message": error.message, "hint": error.hint}
            ),
        }
        out.write(
            json.dumps(
                obj=envelope,
                ensure_ascii=False,
            )
            + "\n"
        )
    else:
        if text is not None:
            out.write(text if text.endswith("\n") else text + "\n")
        for warning in warnings:
            err.write(f"Предупреждение: {warning}\n")
        if error is not None:
            err.write(f"Ошибка: {error.message}\n")
            if error.hint:
                err.write(f"Подсказка: {error.hint}\n")
    out.flush()
    err.flush()
    return 0 if error is None else error.exit_code


# --- helpers for the command bodies ---


def require_lang(
    lang: str | None,
    settings: Settings,
) -> str:
    value = (lang or "").strip() or (settings.lang or "").strip()
    if not value:
        raise UsageError(
            message="Не задан язык результата.",
            hint="Укажите --lang <код> (например, --lang ru) или lang в файле настроек.",
        )
    return value


def require_format(
    fmt: str | None,
    settings: Settings | None = None,
    default: str = "srt",
) -> str:
    value = (
        fmt
        if fmt is not None
        else (settings.format if settings is not None else default)
    )
    if value not in FORMATS:
        raise UsageError(
            message=f"Неизвестный формат: {value}.",
            hint=f"Доступны: {', '.join(FORMATS)}.",
        )
    return value


def require_offset(offset: float) -> float:
    if not math.isfinite(offset):
        raise UsageError(message="--offset должен быть конечным числом секунд.")
    return offset


def _write_utf8(
    path: Path,
    text: str,
) -> None:
    """Atomic: a temp file next to the target, then os.replace; a failure leaves the old file."""
    fd, tmp = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".part",
    )
    try:
        with os.fdopen(
            fd=fd,
            mode="w",
            encoding="utf-8",
            newline="",
        ) as f:
            f.write(text)
        os.replace(
            src=tmp,
            dst=path,
        )
    except BaseException:
        try:
            os.unlink(path=tmp)
        except OSError:
            pass
        raise


async def deliver(
    ctx: AppContext,
    text: str,
    output: str | None,
    default_name: str,
) -> Path | None:
    """Writes `text` to a file (UTF-8) and returns its path; `-o -` → None (the caller prints it)."""
    if output == "-":
        return None
    path = ctx.path(value=output if output is not None else default_name)
    try:
        await asyncio.to_thread(
            _write_utf8,
            path,
            text,
        )
    except OSError as e:
        raise LingotubeError(
            message=f"Не удалось записать файл {path}: {e.strerror or type(e).__name__}.",
            hint="Проверьте путь и права на запись или укажите другой через -o.",
        ) from None
    return path


async def transcript_outcome(
    ctx: AppContext,
    result: TranscriptResult | Transcript,
    text: str,
    fmt: str,
    output: str | None,
) -> Outcome:
    """Delivers a rendered transcript; an incomplete one is still delivered, with exit code 5."""
    if isinstance(
        result,
        TranscriptResult,
    ):
        transcript, complete, warnings = (
            result.transcript,
            result.completeness.complete,
            result.warnings,
        )
    else:
        transcript, complete, warnings = result, True, ()
    language = transcript.language or "orig"
    path = await deliver(
        ctx=ctx,
        text=text,
        output=output,
        default_name=f"{transcript.video_id}.{language}.{fmt}",
    )
    payload: dict[str, Any] = {
        "video_id": transcript.video_id,
        "language": transcript.language,
        "format": fmt,
        "path": None if path is None else str(object=path),
        "complete": complete,
        "cues": len(transcript.cues),
    }
    if path is None and ctx.json_mode:
        payload["content"] = text
    error = None
    if not complete:
        where = "файл записан" if path is not None else "результат выведен"
        error = IncompleteError(
            message=f"Результат неполный: {where}, но транскрипция не доходит до конца видео (см. предупреждения).",
            hint="Повторите команду позже: готовые части возьмутся из кэша, недостающие будут дозапрошены.",
        )
    return Outcome(
        result=payload,
        text=text if path is None else None,
        warnings=tuple(warnings),
        error=error,
    )
