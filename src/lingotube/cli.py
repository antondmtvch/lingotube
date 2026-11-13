"""Command line: a thin layer that parses parameters and calls the features.

`build_registry()` is the single list of connected features; a new feature is a
new module with `register(app, get_context)` plus one line there.
"""

import contextlib
import io
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

import typer
import typer.main

from lingotube import doctor, login_commands
from lingotube.commands import AppContext, report
from lingotube.config import default_login_paths, default_paths, load_settings
from lingotube.errors import LingotubeError, UsageError
from lingotube.features import build, subtitles, summary, transcript
from lingotube.features.registry import FeatureRegistry

ContextFactory = Callable[[TextIO, TextIO], AppContext]

_DASH_ID = re.compile(pattern=r"-[A-Za-z0-9_-]{10}")
PROG = "lingotube"


def build_registry() -> FeatureRegistry:
    registry = FeatureRegistry()
    registry.add(register=transcript.register)
    registry.add(register=subtitles.register)
    registry.add(register=summary.register)
    registry.add(register=build.register)
    registry.add(register=doctor.register)
    registry.add(register=login_commands.register)
    return registry


def default_context(
    out: TextIO,
    err: TextIO,
) -> AppContext:
    """Real wiring: settings file + environment, platform cache dir, current directory."""
    from lingotube.container import build_container  # composition root, used only here

    settings_path, cache_dir = default_paths()
    settings = load_settings(
        path=settings_path,
        env=os.environ,
    )  # sync, before asyncio.run
    container = build_container(
        settings=settings,
        env=os.environ,
        cache_dir=cache_dir,
        login_paths=default_login_paths(),
        err=err,
    )
    return AppContext(
        container=container,
        out=out,
        err=err,
        cwd=Path.cwd(),
        settings_path=settings_path,
    )


def build_app(
    registry: FeatureRegistry,
    get_context: Callable[[], AppContext],
) -> typer.Typer:
    app = typer.Typer(
        name=PROG,
        add_completion=False,
        no_args_is_help=True,
        pretty_exceptions_enable=False,
        help="Субтитры, транскрипция и краткое содержание видео YouTube через чат YouTube.",
    )

    @app.callback()
    def _root() -> None:
        """Субтитры, транскрипция и краткое содержание видео YouTube через чат YouTube."""

    registry.apply(
        app=app,
        get_context=get_context,
    )
    return app


class _ReplacingStream(io.TextIOBase):
    """For a stream that cannot be reconfigured: unencodable characters become '?'."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._encoding = (
            getattr(
                stream,
                "encoding",
                None,
            )
            or "utf-8"
        )

    def write(self, s: str) -> int:
        try:
            return self._stream.write(s)
        except UnicodeEncodeError:
            return self._stream.write(
                s.encode(
                    self._encoding,
                    "replace",
                ).decode(self._encoding)
            )

    def flush(self) -> None:
        self._stream.flush()


def _utf8(stream: TextIO) -> TextIO:
    reconfigure = getattr(
        stream,
        "reconfigure",
        None,
    )
    if reconfigure is not None:
        try:
            reconfigure(
                encoding="utf-8",
                errors="replace",
            )
            return stream
        except OSError, ValueError, io.UnsupportedOperation:
            pass
    if (
        getattr(
            stream,
            "encoding",
            None,
        )
        is None
    ):  # e.g. StringIO: any text is fine
        return stream
    return _ReplacingStream(stream=stream)  # type: ignore[return-value]


def _move_dash_ids(
    argv: list[str],
    command: Any,
) -> list[str]:
    """`subs -n5MqamatXE --lang ru`: a bare token shaped like a video id that starts
    with '-' would be parsed as options; move it after `--` so it stays the URL argument.
    """
    if "--" in argv:
        return argv
    index = next(
        (i for i, t in enumerate(argv) if not t.startswith("-")),
        None,
    )
    if index is None or argv[index] not in getattr(
        command,
        "commands",
        {},
    ):
        return argv
    sub = command.commands[argv[index]]
    known: set[str] = set()
    takes_value: set[str] = set()
    for param in sub.params:
        if param.param_type_name != "option":
            continue
        names = [*param.opts, *param.secondary_opts]
        known.update(names)
        if not param.is_flag and not getattr(
            param,
            "count",
            False,
        ):
            takes_value.update(names)
    head, rest, moved = argv[: index + 1], [], []
    skip = False
    for token in argv[index + 1 :]:
        if skip:
            rest.append(token)
            skip = False
        elif token in takes_value:
            rest.append(token)
            skip = True
        elif _DASH_ID.fullmatch(string=token) and token not in known:
            moved.append(token)
        else:
            rest.append(token)
    return argv if not moved else [*head, *rest, "--", *moved]


def _json_requested(argv: list[str]) -> bool:
    return "--json" in (argv[: argv.index("--")] if "--" in argv else argv)


def run(
    argv: list[str],
    *,
    out: TextIO,
    err: TextIO,
    context_factory: ContextFactory = default_context,
    registry: FeatureRegistry | None = None,
) -> int:
    """Runs one invocation and returns its exit code (parser usage errors → 2)."""
    out, err = _utf8(stream=out), _utf8(stream=err)
    json_mode = _json_requested(argv=argv)
    built: list[AppContext] = []

    def get_context() -> AppContext:
        """Built lazily (help never needs settings) and once per invocation."""
        if not built:
            built.append(
                context_factory(
                    out,
                    err,
                )
            )
        return built[0]

    app = build_app(
        registry=registry if registry is not None else build_registry(),
        get_context=get_context,
    )
    try:
        command = typer.main.get_command(typer_instance=app)
        args = _move_dash_ids(
            argv=list(argv),
            command=command,
        )
        rv = command.main(
            args=args,
            prog_name=PROG,
            standalone_mode=False,
        )
    except typer.Exit as e:
        return e.exit_code
    except typer.Abort:
        return _report_safely(
            out=out,
            err=err,
            json_mode=json_mode,
            error=LingotubeError(message="Прервано."),
            code=1,
        )
    except typer.TyperException as e:
        # parser errors: unknown option, missing argument…
        message = e.format_message().strip()
        # no arguments at all: the help is already shown
        if not message and not json_mode:
            return e.exit_code
        error = UsageError(
            message=message or "Не указана команда.",
            hint=f"Справка: {PROG} --help",
        )
        return _report_safely(
            out=out,
            err=err,
            json_mode=json_mode,
            error=error,
            code=e.exit_code,
        )
    except LingotubeError as e:
        # e.g. a broken settings file while building the context
        return _report_safely(
            out=out,
            err=err,
            json_mode=json_mode,
            error=e,
            code=e.exit_code,
        )
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        # never a traceback, never the exception text (may hold secrets)
        error = LingotubeError(
            message=f"Внутренняя ошибка ({type(e).__name__}).",
            hint="Повторите команду; если ошибка повторяется — сообщите о ней.",
        )
        return _report_safely(
            out=out,
            err=err,
            json_mode=json_mode,
            error=error,
            code=1,
        )
    return (
        rv
        if isinstance(
            rv,
            int,
        )
        else 0
    )


def _report_safely(
    out: TextIO,
    err: TextIO,
    json_mode: bool,
    error: LingotubeError,
    code: int,
) -> int:
    """Reports an error; if the streams themselves fail, only the exit code remains."""
    with contextlib.suppress(Exception):
        report(
            out=out,
            err=err,
            json_mode=json_mode,
            error=error,
        )
    return code


def main() -> None:
    sys.exit(
        run(
            argv=sys.argv[1:],
            out=sys.stdout,
            err=sys.stderr,
        )
    )
