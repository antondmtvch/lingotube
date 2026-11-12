"""Capability «транскрипция»: full timed transcript from the YouTube chat, chunk by chunk.

Flow (spec §6, §7, §16):
- a complete cached result is served without opening the chat;
- otherwise one chat is opened per run and the video is asked in planned ranges;
- a range whose answer stops early is re-asked from the last received timecode
  (at most MAX_REREQUESTS times, and no further once a re-request brings nothing new);
- every finished range is cached at once, so a failed or cancelled run resumes
  from the first missing range; a range that stayed truncated is cached as such
  and continued on the next run, unless the chat already had nothing more to add;
- the final result is cached with a `complete` flag; an incomplete one is never
  served as ready.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
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
from lingotube.cache import Cache, CacheKey
from lingotube.config import Settings
from lingotube.errors import ChatUnavailableError, ValidationError
from lingotube.models import Transcript
from lingotube.parsing import ParsedLine, parse_answer
from lingotube.prompts import PROMPT_VERSION, load_prompt

MAX_REREQUESTS = 3  # per range
MODE = "chat"
KIND_PART = "transcript-part"
KIND_FINAL = "transcript"


@dataclass(frozen=True)
class TranscriptResult:
    transcript: Transcript
    completeness: Completeness
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _Part:
    lines: tuple[ParsedLine, ...]
    truncated: bool
    exhausted: bool = False  # the chat had nothing more to add: never re-asked on later runs


def transcript_key(video_id: str, lang_key: str = "orig") -> CacheKey:
    """Cache key of the final transcript (`lang_key` "orig" = original language)."""
    return CacheKey(video_id, KIND_FINAL, lang_key, MODE, PROMPT_VERSION)


async def load_cached_transcript(
    cache: Cache, video_id: str, lang_key: str = "orig", *, require_complete: bool
) -> Transcript | None:
    """Cached final transcript, or None if absent/malformed (or incomplete when required)."""
    return _parse_final(await cache.get(transcript_key(video_id, lang_key)), require_complete)


def _parse_final(data: dict | None, require_complete: bool) -> Transcript | None:
    """The one place a cached final payload is parsed; malformed → None."""
    if data is None or (require_complete and data.get("complete") is not True):
        return None
    try:
        return Transcript.from_dict(data.get("transcript"))  # type: ignore[arg-type]
    except ValidationError:
        return None


def format_time(seconds: float, *, ceil: bool = False) -> str:
    """`m:ss` below one hour, `h:mm:ss` from one hour."""
    total = math.ceil(seconds) if ceil else math.floor(seconds)
    hours, rest = divmod(max(total, 0), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


def keep_second_of_identical(lines: Sequence[ParsedLine]) -> list[ParsedLine]:
    """Chat translation sometimes interleaves original + translation under the same timecode:
    of two consecutive lines with identical start and end only the second is kept."""
    out: list[ParsedLine] = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines) and (lines[i].start, lines[i].end) == (lines[i + 1].start, lines[i + 1].end):
            out.append(lines[i + 1])
            i += 2
        else:
            out.append(lines[i])
            i += 1
    return out


class TranscriptFeature:
    def __init__(
        self,
        ask: AskClient,
        cache: Cache,
        settings: Settings,
        progress: Callable[[int, int], None] = lambda done, total: None,
    ) -> None:
        self._ask = ask
        self._cache = cache
        self._settings = settings
        self._progress = progress

    async def run(
        self, video_id: str, language: str | None = None, *, use_cache: bool = True
    ) -> TranscriptResult:
        """`language=None` → original language; otherwise the chat translates directly.

        `use_cache=False` neither reads nor serves cached parts/results, but fresh
        parts and the fresh result are still written.
        """
        lang_key = language or "orig"
        final_key = transcript_key(video_id, lang_key)
        if use_cache:
            cached = _load_final(await self._cache.get(final_key))
            if cached is not None:
                return cached

        session = await self._ask.open(video_id)
        info = session.info
        ranges = plan_ranges(info.duration, self._settings.chunk_seconds)
        chunks: list[Sequence[ParsedLine]] = []
        warnings: list[str] = []
        for index, (start, end) in enumerate(ranges):
            is_last = index == len(ranges) - 1
            part_key = CacheKey(
                video_id, KIND_PART, lang_key, MODE, PROMPT_VERSION, part=f"{start}-{end}"
            )
            prior = _load_part(await self._cache.get(part_key)) if use_cache else None
            if prior is None or (prior.truncated and not prior.exhausted):
                prior = await self._collect(session, start, end, language, prior, is_last)
                await self._cache.put(part_key, _dump_part(prior))
            if prior.truncated and not prior.exhausted:
                # re-request budget ran out while the chat was still progressing; an exhausted
                # part (no further speech from the chat) is left to the completeness warnings
                reached = prior.lines[-1].start if prior.lines else start
                warnings.append(
                    f"отрезок {format_time(start)}–{format_time(end, ceil=True)} остался оборванным: "
                    f"ответ чата дошёл только до {format_time(reached)}"
                )
            chunks.append(prior.lines)
            self._progress(index + 1, len(ranges))

        cues = fix_ends(merge(chunks), info.duration)
        completeness = check_completeness(cues, info.duration)
        warnings = _completeness_warnings(completeness, info.duration) + warnings
        transcript = Transcript(
            video_id=video_id,
            duration=info.duration,
            language=language if language is not None else info.language,
            prompt_version=PROMPT_VERSION,
            cues=tuple(cues),
        )
        result = TranscriptResult(transcript, completeness, tuple(warnings))
        await self._cache.put(
            final_key,
            {
                "complete": completeness.complete,
                "warnings": list(result.warnings),
                "transcript": transcript.to_dict(),
            },
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
            lines = await self._ask_range(session, start, end, language)
            if not lines:
                raise ChatUnavailableError(
                    f"Чат не вернул транскрипцию отрезка {format_time(start)}–"
                    f"{format_time(end, ceil=True)}: в ответе нет ни одного тайм-кода.",
                    hint="Возможно, чат отказался отвечать по этому видео. Повторите позже.",
                )
        else:
            lines = list(prior.lines)

        exhausted = False
        for _ in range(MAX_REREQUESTS):
            if not is_truncated(lines, end):
                break
            resume_at = lines[-1].start if lines else start
            more = [x for x in await self._ask_range(session, resume_at, end, language) if x.start >= resume_at]
            if more and more[0].start == resume_at and lines and lines[-1].start == resume_at:
                lines.pop()  # the line at the cut may be incomplete: the continuation re-delivers it
            lines.extend(more)
            if not more or max(x.start for x in more) <= resume_at:
                exhausted = True  # no progress: asking again would not help
                break

        truncated = is_truncated(lines, end)
        if not is_last:
            lines = [x for x in lines if x.start < end]  # overshoot belongs to the next range
        return _Part(tuple(lines), truncated, exhausted and truncated)

    async def _ask_range(
        self, session: AskSession, start: float, end: float, language: str | None
    ) -> list[ParsedLine]:
        variables = {"start": format_time(start), "end": format_time(end, ceil=True)}
        if language is None:
            prompt = load_prompt("transcript", **variables)
        else:
            prompt = load_prompt("transcript_translated", language=language, **variables)
        lines = parse_answer(await session.ask(prompt))
        return keep_second_of_identical(lines) if language is not None else lines


def _completeness_warnings(completeness: Completeness, duration: float) -> list[str]:
    warnings = [f"пропуск {format_time(a)}–{format_time(b)}" for a, b in completeness.gaps]
    if not completeness.complete:
        warnings.insert(
            0,
            f"транскрипция неполная: обрывается на {format_time(completeness.last_end)} "
            f"из {format_time(duration, ceil=True)}",
        )
    return warnings


def _dump_part(part: _Part) -> dict[str, Any]:
    return {
        "truncated": part.truncated,
        "exhausted": part.exhausted,
        "lines": [[x.start, x.end, x.text] for x in part.lines],
    }


def _is_num(v: object) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _load_part(data: dict | None) -> _Part | None:
    """A malformed cached part is treated as missing."""
    if data is None or not isinstance(data.get("truncated"), bool) or not isinstance(data.get("lines"), list):
        return None
    lines: list[ParsedLine] = []
    for item in data["lines"]:
        if not (isinstance(item, list) and len(item) == 3):
            return None
        start, end, text = item
        if not _is_num(start) or not (end is None or _is_num(end)) or not isinstance(text, str):
            return None
        lines.append(ParsedLine(float(start), None if end is None else float(end), text))
    exhausted = data.get("exhausted", False)
    if not isinstance(exhausted, bool):
        return None
    return _Part(tuple(lines), data["truncated"], exhausted)


def _load_final(data: dict | None) -> TranscriptResult | None:
    """Only a well-formed result marked complete is served; anything else is re-asked."""
    transcript = _parse_final(data, require_complete=True)
    if transcript is None or data is None:
        return None
    warnings = data.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
        return None
    completeness = check_completeness(transcript.cues, transcript.duration)
    return TranscriptResult(transcript, completeness, tuple(warnings))


def register(app, get_context) -> None:
    """Adds the `transcript` command: the original-language transcript (JSON by default, spec §8)."""
    from lingotube import commands as c
    from lingotube.writers import render

    @app.command("transcript", help="Транскрипция на языке оригинала с тайм-кодами (по умолчанию JSON).")
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
        common = c.Common(json_, cookies_file, browser, no_cache)

        async def body(ctx: c.AppContext, video_id: str | None) -> c.Outcome:
            assert video_id is not None
            fmt_ = c.require_format(fmt, default="json")
            shift = c.require_offset(offset)
            feature = await ctx.provide(ctx.container.transcript_feature)
            result = await feature.run(video_id, None, use_cache=common.use_cache)
            return await c.transcript_outcome(ctx, result, render(result.transcript, fmt_, shift), fmt_, output)

        c.execute(get_context, common, video, body)
