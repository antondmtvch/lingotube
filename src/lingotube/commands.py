"""CLI plumbing shared by the feature commands.

Every command is a thin synchronous wrapper: it parses its options, then `execute`
runs the async body under `asyncio.run`, turns errors into exit codes and messages
(or one `--json` envelope) and always shuts the container's resources down.
"""

import asyncio
import contextlib
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
    """Shared state of one command run: the container, the streams and the paths.

    Attributes:
        container: Dependency container of the run.
        out: Stream for the result.
        err: Stream for messages.
        cwd: Folder where default output files go and relative paths are resolved.
        settings_path: Settings file where ``--cookies-file`` is remembered, or None if
            it is not remembered.
        json_mode: True if the result is printed as one JSON document.
    """

    container: Container
    out: TextIO
    err: TextIO
    cwd: Path  # where default output files go and relative paths resolve
    # where --cookies-file is remembered (None: not remembered)
    settings_path: Path | None
    json_mode: bool = False

    @property
    def settings(self) -> Settings:
        """Return the effective settings of the run.

        Returns:
            The current settings.
        """
        return self.container.settings()

    def use_settings(self, settings: Settings) -> None:
        """Replace the settings of the run.

        Args:
            settings: Settings to use from now on.
        """
        self.container.settings.override(provider=providers.Object(settings))

    async def provide(self, provider: Callable[[], Any]) -> Any:
        """Resolve a provider, and await the result if it is awaitable.

        Args:
            provider: Provider to call.

        Returns:
            The provided value.
        """
        value = provider()
        return await value if inspect.isawaitable(object=value) else value

    async def close(self) -> None:
        """Release the resources of the container, such as HTTP clients."""
        result = self.container.shutdown_resources()
        if inspect.isawaitable(object=result):
            await result

    def path(self, value: str | Path) -> Path:
        """Resolve a path against the current folder.

        Args:
            value: Absolute or relative path.

        Returns:
            The path. A relative path is joined to the current folder; an absolute path is kept.
        """
        return self.cwd / Path(value)


@dataclass(frozen=True)
class Common:
    """Options shared by the commands.

    Attributes:
        json: True if the result is printed as one JSON document.
        cookies_file: Cookies file given on the command line, or None.
        browser: Browser given on the command line, or None.
        no_cache: True if saved results must not be used.
    """

    json: bool = False
    cookies_file: Path | None = None
    browser: str | None = None
    no_cache: bool = False

    @property
    def use_cache(self) -> bool:
        """Return True unless the person asked not to use saved results.

        Returns:
            True if saved results may be used.
        """
        return not self.no_cache


@dataclass(frozen=True)
class Outcome:
    """What a command produced: the result, its text, the warnings and an optional error.

    Attributes:
        result: Data for the ``--json`` output.
        text: Text for the normal output, or None.
        warnings: Warnings to show to the person.
        error: Problem with a result that was still delivered, or None.
    """

    result: Any
    text: str | None = None  # what goes to `out` without --json
    warnings: tuple[str, ...] = ()
    error: LingotubeError | None = None  # a result delivered with a problem (e.g. incomplete)


Body = Callable[[AppContext, str | None], Awaitable[Outcome]]

# --- options shared by the commands (spec §6) ---

VideoArg = Annotated[
    str,
    typer.Argument(
        metavar="URL",
        help="A YouTube video link or video id.",
        show_default=False,
    ),
]
LangOpt = Annotated[
    str | None,
    typer.Option(
        default="--lang",
        help="Language of the result (ru, en, es…); by default taken from the settings.",
    ),
]
FormatOpt = Annotated[
    str | None,
    typer.Option(
        default="--format",
        help="Format: srt, vtt or json.",
    ),
]
OutputOpt = Annotated[
    str | None,
    typer.Option(
        "-o",
        "--output",
        help="Where to write; by default the file <id>.<language>.<format>; '-' means standard output.",
    ),
]
OffsetOpt = Annotated[
    float,
    typer.Option(
        default="--offset",
        help="Shift all subtitles by this many seconds (fractional and negative values are allowed).",
    ),
]
CookiesFileOpt = Annotated[
    Path | None,
    typer.Option(
        default="--cookies-file",
        help="Cookies file cookies.txt (the path is remembered in the settings).",
    ),
]
BrowserOpt = Annotated[
    str | None,
    typer.Option(
        default="--browser",
        help=f"Browser to read the cookies from: {', '.join(BROWSERS)}.",
    ),
]
NoCacheOpt = Annotated[
    bool,
    typer.Option(
        default="--no-cache",
        help="Do not use saved results.",
    ),
]
JsonOpt = Annotated[
    bool,
    typer.Option(
        default="--json",
        help="Machine-readable output: one JSON document on standard output.",
    ),
]


# --- running a command ---


def execute(
    get_context: Callable[[], AppContext],
    common: Common,
    video: str | None,
    body: Body,
) -> None:
    """Run the body of a command and print its outcome.

    Args:
        get_context: Function that builds the context of the run.
        common: Options shared by the commands.
        video: Video link or id, or None if the command takes no video.
        body: Async function that does the work of the command.

    Raises:
        typer.Exit: Always, with the exit code of the run.
    """
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
            error=LingotubeError(message="Interrupted."),
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
            # before any network
            video_id = parse_video_id(value=video) if video is not None else None
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
    except Exception as e:
        # never a traceback, never the exception text (may hold secrets)
        error = LingotubeError(
            message=f"Internal error ({type(e).__name__}).",
            hint="Run the command again; if the error repeats, report it.",
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
        raise UsageError(message="Give only one of --cookies-file and --browser.")
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
            message=f"Unknown browser: {browser}.",
            hint=f"Available: {', '.join(BROWSERS)}.",
        )
    ctx.use_settings(
        settings=replace(
            settings,
            cookies_file=cookies_file,
            browser=browser,
        )
    )
    if (
        common.cookies_file is not None and cookies_file is not None and ctx.settings_path is not None
    ) and await asyncio.to_thread(cookies_file.is_file):
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
    """Write the outcome, as one JSON document with ``--json``, and return the exit code.

    Args:
        out: Stream for the result.
        err: Stream for messages.
        json_mode: True if the result is printed as one JSON document.
        result: Data for the JSON output.
        text: Text for the normal output.
        warnings: Warnings to show.
        error: Error to show, or None.

    Returns:
        The exit code: 0 if there is no error, otherwise the exit code of the error.
    """
    if json_mode:
        envelope = {
            "ok": error is None,
            "result": result,
            "warnings": list(warnings),
            "error": (None if error is None else {"code": error.code, "message": error.message, "hint": error.hint}),
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
            err.write(f"Warning: {warning}\n")
        if error is not None:
            err.write(f"Error: {error.message}\n")
            if error.hint:
                err.write(f"Hint: {error.hint}\n")
    out.flush()
    err.flush()
    return 0 if error is None else error.exit_code


# --- helpers for the command bodies ---


def require_lang(
    lang: str | None,
    settings: Settings,
) -> str:
    """Return the output language from the option or from the settings.

    Args:
        lang: Language code from the command line, or None.
        settings: Effective settings.

    Returns:
        The language code.

    Raises:
        UsageError: If neither the option nor the settings give a language.
    """
    value = (lang or "").strip() or (settings.lang or "").strip()
    if not value:
        raise UsageError(
            message="The output language is not set.",
            hint="Give --lang <code> (for example, --lang ru) or set lang in the settings file.",
        )
    return value


def require_format(
    fmt: str | None,
    settings: Settings | None = None,
    default: str = "srt",
) -> str:
    """Return a valid output format.

    Args:
        fmt: Format from the command line, or None.
        settings: Settings that give the default format, if there are any.
        default: Format used when there are no settings.

    Returns:
        The format name.

    Raises:
        UsageError: If the format is unknown.
    """
    value = fmt if fmt is not None else (settings.format if settings is not None else default)
    if value not in FORMATS:
        raise UsageError(
            message=f"Unknown format: {value}.",
            hint=f"Available: {', '.join(FORMATS)}.",
        )
    return value


def require_offset(offset: float) -> float:
    """Check that the offset is a finite number of seconds.

    Args:
        offset: Offset in seconds.

    Returns:
        The same offset.

    Raises:
        UsageError: If the offset is not finite.
    """
    if not math.isfinite(offset):
        raise UsageError(message="--offset must be a finite number of seconds.")
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
        with contextlib.suppress(OSError):
            os.unlink(path=tmp)
        raise


async def deliver(
    ctx: AppContext,
    text: str,
    output: str | None,
    default_name: str,
) -> Path | None:
    """Write the text to a UTF-8 file and return the path.

    Args:
        ctx: Context of the run.
        text: Text to write.
        output: Path from ``-o``, or None to use the default name. ``-`` means standard output.
        default_name: File name used when ``output`` is None.

    Returns:
        The path of the written file, or None if the text goes to standard output.

    Raises:
        LingotubeError: If the file cannot be written.
    """
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
            message=f"Could not write the file {path}: {e.strerror or type(e).__name__}.",
            hint="Check the path and the write permissions, or give another one with -o.",
        ) from None
    return path


async def transcript_outcome(
    ctx: AppContext,
    result: TranscriptResult | Transcript,
    text: str,
    fmt: str,
    output: str | None,
    warnings: tuple[str, ...] = (),
) -> Outcome:
    """Deliver a rendered transcript. An incomplete transcript is still delivered, with exit code 5.

    Args:
        ctx: Context of the run.
        result: Transcript result or a bare transcript.
        text: Rendered transcript text.
        fmt: Output format, used in the default file name.
        output: Path from ``-o``, or None to use the default name.
        warnings: Extra warnings, added to those of the result.

    Returns:
        The outcome of the command.
    """
    if isinstance(
        result,
        TranscriptResult,
    ):
        transcript, complete, warnings = (
            result.transcript,
            result.completeness.complete,
            result.warnings + warnings,
        )
    else:
        transcript, complete = result, True
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
        "path": None if path is None else str(path),
        "complete": complete,
        "cues": len(transcript.cues),
    }
    if path is None and ctx.json_mode:
        payload["content"] = text
    error = None
    if not complete:
        where = "file written" if path is not None else "result printed"
        error = IncompleteError(
            message=f"The result is incomplete: {where}, but the transcript does not reach the end of the video (see the warnings).",
            hint="Run the command again later: the parts that are ready will come from the cache, and the missing ones will be requested.",
        )
    return Outcome(
        result=payload,
        text=text if path is None else None,
        warnings=tuple(warnings),
        error=error,
    )
