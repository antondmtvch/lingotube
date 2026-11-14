"""Agent mode: check an external translation against the cached original and cache it."""

from dataclasses import dataclass, replace
from typing import Any

from lingotube.cache import Cache, CacheKey, put_best_effort
from lingotube.errors import ValidationError
from lingotube.features.transcript import load_cached_transcript
from lingotube.models import Cue, Transcript
from lingotube.prompts import PROMPT_VERSION

MAX_IDS = 20


def _ids(ids: list[int]) -> str:
    ordered = sorted(ids)
    text = ", ".join(str(i) for i in ordered[:MAX_IDS])
    if len(ordered) > MAX_IDS:
        text += f" … и ещё {len(ordered) - MAX_IDS}"
    return text


def validate_translation(
    original: Transcript,
    translated: dict[str, Any],
    language: str,
) -> Transcript:
    """Check a translation against the original. The times of the original always win.

    All problems are collected into one error that lists the ids concerned.

    Args:
        original: The original transcript.
        translated: The translation in the transcript JSON format.
        language: Language code of the translation.

    Returns:
        The transcript with the original times and the translated text.

    Raises:
        ValidationError: If the translation does not match the original.
    """
    parsed = Transcript.from_dict(d=translated)
    if parsed.video_id != original.video_id:
        raise ValidationError(
            message=f"video_id перевода ({parsed.video_id}) не совпадает с видео оригинала ({original.video_id})."
        )
    expected = {c.id for c in original.cues}
    seen: set[int] = set()
    duplicate: set[int] = set()
    empty: set[int] = set()
    texts: dict[int, str] = {}
    for cue in parsed.cues:
        if cue.id in seen:
            duplicate.add(cue.id)
            continue
        seen.add(cue.id)
        texts[cue.id] = cue.text
        if not cue.text.strip():
            empty.add(cue.id)
    problems: list[str] = []
    if missing := expected - seen:
        problems.append(f"отсутствуют id: {_ids(ids=list(missing))}")
    if extra := seen - expected:
        problems.append(f"лишние id: {_ids(ids=list(extra))}")
    if duplicate:
        problems.append(f"повторяются id: {_ids(ids=list(duplicate))}")
    if empty:
        problems.append(f"пустой текст у id: {_ids(ids=list(empty))}")
    if problems:
        raise ValidationError(
            message="Перевод не совпадает с оригиналом: " + "; ".join(problems) + ".",
            hint="Верните все реплики оригинала, по одной на id, с непустым текстом.",
        )
    cues = tuple(
        Cue(
            id=c.id,
            start=c.start,
            end=c.end,
            text=texts[c.id],
        )
        for c in original.cues
    )
    return replace(
        original,
        language=language,
        cues=cues,
    )


@dataclass(frozen=True)
class BuildResult:
    """Result of the build command.

    Attributes:
        transcript: The validated transcript.
        warnings: Warnings, for example about the cache.
    """

    transcript: Transcript
    warnings: tuple[str, ...] = ()


class BuildFeature:
    """Check a translation made by an agent and cache it as subtitles."""

    def __init__(self, cache: Cache) -> None:
        """Create the feature.

        Args:
            cache: Cache that holds the original transcript and the result.
        """
        self._cache = cache

    async def run(
        self,
        video_id: str,
        language: str,
        translated: dict[str, Any],
    ) -> BuildResult:
        """Check the translation of a video against its cached original.

        Args:
            video_id: YouTube video id.
            language: Language code of the translation.
            translated: The translation in the transcript JSON format.

        Returns:
            The build result.

        Raises:
            ValidationError: If the original is not cached or the translation does not match it.
        """
        original = await load_cached_transcript(
            cache=self._cache,
            video_id=video_id,
            require_complete=False,
        )
        if original is None:
            raise ValidationError(
                message="Оригинальная транскрипция этого видео не найдена в кэше.",
                hint="Сначала выполните `lingotube transcript <url>`.",
            )
        result = validate_translation(
            original=original,
            translated=translated,
            language=language,
        )
        failed = await put_best_effort(
            cache=self._cache,
            key=CacheKey(
                video_id=video_id,
                kind="subtitles",
                language=language,
                mode="agent",
                prompt_version=PROMPT_VERSION,
            ),
            value=result.to_dict(),
        )
        return BuildResult(
            transcript=result,
            warnings=(failed,) if failed is not None else (),
        )


def _read_json(path) -> Any:
    import json

    try:
        with open(
            path,
            encoding="utf-8",
        ) as f:
            return json.load(fp=f)
    except FileNotFoundError:
        raise ValidationError(message=f"Файл перевода не найден: {path}") from None
    except (OSError, ValueError) as e:
        raise ValidationError(
            message=f"Не удалось прочитать файл перевода {path} как JSON UTF-8: {type(e).__name__}.",
            hint="Файл должен быть в формате транскрипции (раздел 8): video_id, duration, language, cues.",
        ) from None


def register(
    app,
    get_context,
) -> None:
    """Add the ``build`` command to the CLI application.

    Args:
        app: Typer application.
        get_context: Function that returns the shared context of the command.
    """
    import asyncio
    from pathlib import Path
    from typing import Annotated

    import typer

    from lingotube import commands as c
    from lingotube.writers import render

    FromOpt = Annotated[
        Path,
        typer.Option(
            default="--from",
            help="Файл с переведённой транскрипцией (JSON).",
        ),
    ]

    @app.command(
        name="build",
        help="Сверяет готовый перевод с оригиналом и собирает субтитры.",
    )
    def build(
        video: c.VideoArg,
        source: FromOpt,
        lang: c.LangOpt = None,
        fmt: c.FormatOpt = None,
        output: c.OutputOpt = None,
        offset: c.OffsetOpt = 0.0,
        json_: c.JsonOpt = False,
    ) -> None:
        common = c.Common(json=json_)

        async def body(
            ctx: c.AppContext,
            video_id: str | None,
        ) -> c.Outcome:
            assert video_id is not None
            language = c.require_lang(
                lang=lang,
                settings=ctx.settings,
            )
            fmt_ = c.require_format(
                fmt=fmt,
                settings=ctx.settings,
            )
            shift = c.require_offset(offset=offset)
            translated = await asyncio.to_thread(
                _read_json,
                ctx.path(value=source),
            )
            feature = await ctx.provide(provider=ctx.container.build_feature)
            result = await feature.run(
                video_id=video_id,
                language=language,
                translated=translated,
            )
            return await c.transcript_outcome(
                ctx=ctx,
                result=result.transcript,
                warnings=result.warnings,
                text=render(
                    transcript=result.transcript,
                    fmt=fmt_,
                    offset=shift,
                ),
                fmt=fmt_,
                output=output,
            )

        c.execute(
            get_context=get_context,
            common=common,
            video=video,
            body=body,
        )
