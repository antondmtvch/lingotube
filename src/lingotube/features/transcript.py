"""Transcript feature: a full timed transcript from the YouTube chat, range by range.

Flow:
- a complete cached result is served without opening the chat;
- otherwise one chat is opened per run, and the video is asked in planned ranges;
- a range whose answer stops early is asked again from the last timecode received
  (at most MAX_REREQUESTS times, and not again once a repeat brings nothing new);
- every finished range is cached at once, so a failed or cancelled run resumes from
  the first missing range; a range that stayed truncated is cached as such and
  continued on the next run, unless the chat already had nothing more to add;
- the final result is cached with a ``complete`` flag; an incomplete one is never
  served as ready.
"""

import math
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from lingotube.ask.client import AskClient, AskSession
from lingotube.assemble import (
    Completeness,
    check_completeness,
    fix_ends,
    is_truncated,
    merge,
    plan_ranges,
)
from lingotube.cache import Cache, CacheKey, put_best_effort
from lingotube.config import Settings
from lingotube.errors import ChatUnavailableError, ValidationError
from lingotube.models import Transcript, VideoInfo
from lingotube.parsing import ParsedLine, parse_answer
from lingotube.prompts import PROMPT_VERSION, load_prompt

MAX_REREQUESTS = 3  # per range
GAP_REREQUEST = 45.0  # an inner silence longer than this is asked for once more
MAX_GAP_REREQUESTS = 4  # per range
MODE = "chat"
KIND_PART = "transcript-part"
KIND_FINAL = "transcript"


@dataclass(frozen=True)
class TranscriptResult:
    """A transcript with its completeness and the warnings for the person.

    Attributes:
        transcript: The transcript.
        completeness: Result of the completeness check.
        warnings: Warnings that explain gaps or an incomplete result.
    """

    transcript: Transcript
    completeness: Completeness
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _Part:
    lines: tuple[ParsedLine, ...]
    truncated: bool
    exhausted: bool = False  # the chat had nothing more to add: never re-asked on later runs
    gaps_checked: bool = False  # inner silences were already asked for once


def transcript_key(
    video_id: str,
    lang_key: str = "orig",
) -> CacheKey:
    """Return the cache key of the final transcript.

    Args:
        video_id: YouTube video id.
        lang_key: Language code, or ``orig`` for the original language.

    Returns:
        The cache key.
    """
    return CacheKey(
        video_id=video_id,
        kind=KIND_FINAL,
        language=lang_key,
        mode=MODE,
        prompt_version=PROMPT_VERSION,
    )


async def load_cached_transcript(
    cache: Cache,
    video_id: str,
    lang_key: str = "orig",
    *,
    require_complete: bool,
) -> Transcript | None:
    """Load the cached final transcript.

    Args:
        cache: Cache to read from.
        video_id: YouTube video id.
        lang_key: Language code, or ``orig`` for the original language.
        require_complete: If True, an incomplete transcript counts as missing.

    Returns:
        The transcript, or None if it is absent, malformed or (when required) incomplete.
    """
    return _parse_final(
        data=await cache.get(
            key=transcript_key(
                video_id=video_id,
                lang_key=lang_key,
            )
        ),
        require_complete=require_complete,
    )


def _parse_final(
    data: dict | None,
    require_complete: bool,
) -> Transcript | None:
    """Parse a cached final result. Malformed data gives None.

    Args:
        data: Cached payload, or None.
        require_complete: If True, an incomplete result counts as missing.

    Returns:
        The transcript, or None.
    """
    if data is None or (require_complete and data.get("complete") is not True):
        return None
    try:
        return Transcript.from_dict(d=data.get("transcript"))  # type: ignore[arg-type]
    except ValidationError:
        return None


def format_time(
    seconds: float,
    *,
    ceil: bool = False,
) -> str:
    """Format seconds as ``m:ss``, or as ``h:mm:ss`` from one hour.

    Args:
        seconds: Time in seconds.
        ceil: If True, round up to a whole second; otherwise round down.

    Returns:
        The formatted time.
    """
    total = math.ceil(seconds) if ceil else math.floor(seconds)
    hours, rest = divmod(
        max(
            total,
            0,
        ),
        3600,
    )
    minutes, secs = divmod(
        rest,
        60,
    )
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


def keep_second_of_identical(lines: Sequence[ParsedLine]) -> list[ParsedLine]:
    """Keep one line from each pair of identical timed lines.

    The chat sometimes puts the original and the translation under the same timecode. Of
    two consecutive lines with the same start and end, only the second one is kept.

    Args:
        lines: Parsed lines in order.

    Returns:
        The lines with the duplicates removed.
    """
    out: list[ParsedLine] = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines) and (lines[i].start, lines[i].end) == (
            lines[i + 1].start,
            lines[i + 1].end,
        ):
            out.append(lines[i + 1])
            i += 2
        else:
            out.append(lines[i])
            i += 1
    return out


class TranscriptFeature:
    """Get the full timed transcript of a video from the YouTube chat.

    The video is asked range by range. Finished ranges are cached, so an interrupted run
    resumes where it stopped.
    """

    def __init__(
        self,
        ask: AskClient,
        cache: Cache,
        settings: Settings,
        progress: Callable[[int, int], None] = lambda done, total: None,
    ) -> None:
        """Create the feature.

        Args:
            ask: Client of the YouTube chat.
            cache: Cache of the results.
            settings: Effective settings; the range length comes from them.
            progress: Function that receives the number of ranges done and the total.
        """
        self._ask = ask
        self._cache = cache
        self._settings = settings
        self._progress = progress

    async def run(
        self,
        video_id: str,
        language: str | None = None,
        *,
        use_cache: bool = True,
        on_opened: Callable[[VideoInfo], Awaitable[None]] | None = None,
    ) -> TranscriptResult:
        """Get the transcript of a video.

        ``language=None`` means the original language. Otherwise the chat translates the text
        directly.

        ``on_opened`` is awaited once the chat is open, so the language of the video is known,
        and before any question is asked. It is not called when a cached result is served. An
        exception from it stops the run before any chat request.

        ``use_cache=False`` does not read or serve cached parts and results, but the fresh parts
        and the fresh result are still written.

        Args:
            video_id: YouTube video id.
            language: Language code of the translation, or None for the original language.
            use_cache: Whether saved parts and results may be used.
            on_opened: Optional coroutine function that is called with the video facts once the
                chat is open.

        Returns:
            The transcript with its completeness and warnings.
        """
        lang_key = language or "orig"
        final_key = transcript_key(
            video_id=video_id,
            lang_key=lang_key,
        )
        if use_cache:
            cached = _load_final(data=await self._cache.get(key=final_key))
            if cached is not None:
                return cached

        session = await self._ask.open(video_id=video_id)
        info = session.info
        if on_opened is not None:
            await on_opened(info)
        ranges = plan_ranges(
            duration=info.duration,
            chunk_seconds=self._settings.chunk_seconds,
        )
        chunks: list[Sequence[ParsedLine]] = []
        warnings: list[str] = []
        cache_warnings: list[str] = []
        for index, (start, end) in enumerate(ranges):
            is_last = index == len(ranges) - 1
            part_key = CacheKey(
                video_id=video_id,
                kind=KIND_PART,
                language=lang_key,
                mode=MODE,
                prompt_version=PROMPT_VERSION,
                part=f"{start}-{end}",
            )
            prior = _load_part(data=await self._cache.get(key=part_key)) if use_cache else None
            if (
                prior is None
                or (prior.truncated and not prior.exhausted)
                or (not prior.truncated and not prior.gaps_checked)
            ):
                prior = await self._collect(
                    session=session,
                    start=start,
                    end=end,
                    language=language,
                    prior=prior,
                    is_last=is_last,
                )
                failed = await put_best_effort(
                    cache=self._cache,
                    key=part_key,
                    value=_dump_part(part=prior),
                )
                if failed is not None and failed not in cache_warnings:
                    cache_warnings.append(failed)
            if prior.truncated and not prior.exhausted:
                # re-request budget ran out while the chat was still progressing; an exhausted
                # part (no further speech from the chat) is left to the completeness warnings
                reached = prior.lines[-1].start if prior.lines else start
                range_end = format_time(
                    seconds=end,
                    ceil=True,
                )
                warnings.append(
                    f"отрезок {format_time(seconds=start)}–{range_end} остался оборванным: "
                    f"ответ чата дошёл только до {format_time(seconds=reached)}"
                )
            elif prior.truncated and not is_last:
                # the chat gave nothing more for a range in the middle of the video: name
                # it (the last range is described by the completeness warnings)
                reached = prior.lines[-1].start if prior.lines else start
                range_end = format_time(
                    seconds=end,
                    ceil=True,
                )
                warnings.append(
                    f"отрезок {format_time(seconds=start)}–{range_end}: чат перестал отвечать "
                    f"на {format_time(seconds=reached)}, остаток отрезка не получен"
                )
            chunks.append(prior.lines)
            self._progress(
                index + 1,
                len(ranges),
            )

        cues = fix_ends(
            cues=merge(chunks=chunks),
            duration=info.duration,
        )
        completeness = check_completeness(
            cues=cues,
            duration=info.duration,
        )
        warnings = (
            _completeness_warnings(
                completeness=completeness,
                duration=info.duration,
            )
            + warnings
        )
        transcript = Transcript(
            video_id=video_id,
            duration=info.duration,
            language=language if language is not None else info.language,
            prompt_version=PROMPT_VERSION,
            cues=tuple(cues),
        )
        result = TranscriptResult(
            transcript=transcript,
            completeness=completeness,
            warnings=tuple(warnings),
        )
        failed = await put_best_effort(
            cache=self._cache,
            key=final_key,
            value={
                "complete": completeness.complete,
                "warnings": list(result.warnings),
                "transcript": transcript.to_dict(),
            },
        )
        if failed is not None and failed not in cache_warnings:
            cache_warnings.append(failed)
        if cache_warnings:
            result = replace(
                result,
                warnings=result.warnings + tuple(cache_warnings),
            )
        return result

    async def _collect(
        self,
        session: AskSession,
        start: float,
        end: float,
        language: str | None,
        prior: _Part | None,
        is_last: bool,
    ) -> _Part:
        """Asks one range (or continues a truncated cached one) with bounded re-requests."""
        if prior is None:
            lines = await self._ask_range(
                session=session,
                start=start,
                end=end,
                language=language,
            )
            if not lines:
                range_end = format_time(
                    seconds=end,
                    ceil=True,
                )
                raise ChatUnavailableError(
                    message=f"Чат не вернул транскрипцию отрезка {format_time(seconds=start)}–"
                    f"{range_end}: в ответе нет ни одного тайм-кода.",
                    hint="Возможно, чат отказался отвечать по этому видео. Повторите позже.",
                )
        else:
            lines = list(prior.lines)

        exhausted = False
        for _ in range(MAX_REREQUESTS):
            if not is_truncated(
                lines=lines,
                range_end=end,
            ):
                break
            resume_at = lines[-1].start if lines else start
            more = [
                x
                for x in await self._ask_range(
                    session=session,
                    start=resume_at,
                    end=end,
                    language=language,
                )
                if x.start >= resume_at
            ]
            if more and more[0].start == resume_at and lines and lines[-1].start == resume_at:
                lines.pop()  # the line at the cut may be incomplete: the continuation re-delivers it
            lines.extend(more)
            if not more or max(x.start for x in more) <= resume_at:
                exhausted = True  # no progress: asking again would not help
                break

        truncated = is_truncated(
            lines=lines,
            range_end=end,
        )
        if not is_last:
            lines = [x for x in lines if x.start < end]  # overshoot belongs to the next range
        if not truncated:
            lines = await self._fill_gaps(
                session=session,
                lines=lines,
                start=start,
                end=end,
                language=language,
            )
        return _Part(
            lines=tuple(lines),
            truncated=truncated,
            exhausted=exhausted and truncated,
            gaps_checked=not truncated,
        )

    async def _fill_gaps(
        self,
        session: AskSession,
        lines: list[ParsedLine],
        start: float,
        end: float,
        language: str | None,
    ) -> list[ParsedLine]:
        """Asks once for each long inner silence (the chat sometimes skips speech inside a range)."""
        bounds = [start] + [x.start for x in lines] + [end]
        gaps = [
            (a, b)
            for a, b in zip(
                bounds,
                bounds[1:],
                strict=False,
            )
            if b - a > GAP_REREQUEST
        ]
        gaps = sorted(
            sorted(
                gaps,
                key=lambda g: g[0] - g[1],
            )[:MAX_GAP_REREQUESTS]
        )
        found: list[ParsedLine] = []
        seen: set[tuple[float, str]] = set()
        for a, b in gaps:
            for x in await self._ask_range(
                session=session,
                start=a,
                end=b,
                language=language,
            ):
                if a < x.start < b and (x.start, x.text) not in seen:
                    seen.add((x.start, x.text))
                    found.append(x)
        if not found:
            return lines
        return sorted(
            lines + found,
            key=lambda x: x.start,
        )

    async def _ask_range(
        self,
        session: AskSession,
        start: float,
        end: float,
        language: str | None,
    ) -> list[ParsedLine]:
        variables = {
            "start": format_time(seconds=start),
            "end": format_time(
                seconds=end,
                ceil=True,
            ),
        }
        if language is None:
            prompt = load_prompt(
                name="transcript",
                **variables,
            )
        else:
            prompt = load_prompt(
                name="transcript_translated",
                language=language,
                **variables,
            )
        lines = parse_answer(text=await session.ask(prompt=prompt))
        return keep_second_of_identical(lines=lines) if language is not None else lines


def _completeness_warnings(
    completeness: Completeness,
    duration: float,
) -> list[str]:
    warnings = [f"пропуск {format_time(seconds=a)}–{format_time(seconds=b)}" for a, b in completeness.gaps]
    if not completeness.complete:
        total = format_time(
            seconds=duration,
            ceil=True,
        )
        warnings.insert(
            0,
            f"транскрипция неполная: обрывается на {format_time(seconds=completeness.last_end)} из {total}",
        )
    return warnings


def _dump_part(part: _Part) -> dict[str, Any]:
    return {
        "truncated": part.truncated,
        "exhausted": part.exhausted,
        "gaps_checked": part.gaps_checked,
        "lines": [[x.start, x.end, x.text] for x in part.lines],
    }


def _is_num(v: object) -> bool:
    return isinstance(
        v,
        int | float,
    ) and not isinstance(
        v,
        bool,
    )


def _load_part(data: dict | None) -> _Part | None:
    """A malformed cached part is treated as missing."""
    if (
        data is None
        or not isinstance(
            data.get("truncated"),
            bool,
        )
        or not isinstance(
            data.get("lines"),
            list,
        )
    ):
        return None
    lines: list[ParsedLine] = []
    for item in data["lines"]:
        if not (
            isinstance(
                item,
                list,
            )
            and len(item) == 3
        ):
            return None
        start, end, text = item
        if (
            not _is_num(v=start)
            or not (end is None or _is_num(v=end))
            or not isinstance(
                text,
                str,
            )
        ):
            return None
        lines.append(
            ParsedLine(
                start=float(start),
                end=None if end is None else float(end),
                text=text,
            )
        )
    exhausted = data.get(
        "exhausted",
        False,
    )
    if not isinstance(
        exhausted,
        bool,
    ):
        return None
    gaps_checked = data.get(
        "gaps_checked",
        False,
    )
    if not isinstance(
        gaps_checked,
        bool,
    ):
        return None
    return _Part(
        lines=tuple(lines),
        truncated=data["truncated"],
        exhausted=exhausted,
        gaps_checked=gaps_checked,
    )


def _load_final(data: dict | None) -> TranscriptResult | None:
    """Only a well-formed result marked complete is served; anything else is re-asked."""
    transcript = _parse_final(
        data=data,
        require_complete=True,
    )
    if transcript is None or data is None:
        return None
    warnings = data.get("warnings")
    if not isinstance(
        warnings,
        list,
    ) or not all(
        isinstance(
            w,
            str,
        )
        for w in warnings
    ):
        return None
    completeness = check_completeness(
        cues=transcript.cues,
        duration=transcript.duration,
    )
    return TranscriptResult(
        transcript=transcript,
        completeness=completeness,
        warnings=tuple(warnings),
    )


def register(
    app,
    get_context,
) -> None:
    """Add the ``transcript`` command to the CLI application.

    Args:
        app: Typer application.
        get_context: Function that returns the shared context of the command.
    """
    from lingotube import commands as c
    from lingotube.writers import render

    @app.command(
        name="transcript",
        help="Транскрипция на языке оригинала с тайм-кодами (по умолчанию JSON).",
    )
    def transcript(
        video: c.VideoArg,
        fmt: c.FormatOpt = None,
        output: c.OutputOpt = None,
        offset: c.OffsetOpt = 0.0,
        cookies_file: c.CookiesFileOpt = None,
        browser: c.BrowserOpt = None,
        no_cache: c.NoCacheOpt = False,
        json_: c.JsonOpt = False,
    ) -> None:
        common = c.Common(
            json=json_,
            cookies_file=cookies_file,
            browser=browser,
            no_cache=no_cache,
        )

        async def body(
            ctx: c.AppContext,
            video_id: str | None,
        ) -> c.Outcome:
            assert video_id is not None
            fmt_ = c.require_format(
                fmt=fmt,
                default="json",
            )
            shift = c.require_offset(offset=offset)
            feature = await ctx.provide(provider=ctx.container.transcript_feature)
            result = await feature.run(
                video_id=video_id,
                language=None,
                use_cache=common.use_cache,
            )
            return await c.transcript_outcome(
                ctx=ctx,
                result=result,
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
