"""Capability "subtitles": a transcript in the target language.

- no translator configured -> chat mode: the chat translates directly (cached by TranscriptFeature);
- translator configured -> own-model mode: the original is taken first (cached, so a second
  language needs no new YouTube requests), then translated; the translation is cached per
  language. A translation of an incomplete original is never cached: it is redone next time.
"""

from dataclasses import replace

from lingotube.assemble import check_completeness
from lingotube.cache import Cache, CacheKey, put_best_effort
from lingotube.errors import ValidationError
from lingotube.features.transcript import TranscriptFeature, TranscriptResult
from lingotube.models import Transcript
from lingotube.prompts import PROMPT_VERSION
from lingotube.translate.base import Translator

KIND = "subtitles"
MODE = "own-model"


def _primary(language: str | None) -> str:
    return (
        (language or "")
        .replace(
            "_",
            "-",
        )
        .split("-")[0]
        .strip()
        .lower()
    )


class SubtitlesFeature:
    def __init__(
        self,
        transcripts: TranscriptFeature,
        translator: Translator | None,
        cache: Cache,
    ) -> None:
        self._transcripts = transcripts
        self._translator = translator
        self._cache = cache

    async def run(
        self,
        video_id: str,
        language: str,
        *,
        use_cache: bool = True,
    ) -> TranscriptResult:
        if self._translator is None:
            return await self._transcripts.run(
                video_id=video_id,
                language=language,
                use_cache=use_cache,
            )

        key = CacheKey(
            video_id=video_id,
            kind=KIND,
            language=language,
            mode=MODE,
            prompt_version=PROMPT_VERSION,
        )
        if use_cache:
            cached = _load(data=await self._cache.get(key=key))
            if cached is not None:
                return cached

        original = await self._transcripts.run(
            video_id=video_id,
            language=None,
            use_cache=use_cache,
        )
        source = original.transcript
        if _primary(language=source.language) == _primary(language=language):
            cues = source.cues
        else:
            cues = tuple(
                await self._translator.translate(
                    cues=source.cues,
                    target_language=language,
                )
            )
        transcript = replace(
            source,
            language=language,
            cues=cues,
        )
        result = TranscriptResult(
            transcript=transcript,
            completeness=original.completeness,
            warnings=original.warnings,
        )
        if original.completeness.complete:
            failed = await put_best_effort(
                cache=self._cache,
                key=key,
                value={
                    "complete": True,
                    "warnings": list(result.warnings),
                    "transcript": transcript.to_dict(),
                },
            )
            if failed is not None:
                result = replace(
                    result,
                    warnings=result.warnings + (failed,),
                )
        return result


def _load(data: dict | None) -> TranscriptResult | None:
    if data is None or data.get("complete") is not True:
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
    try:
        transcript = Transcript.from_dict(d=data.get("transcript"))  # type: ignore[arg-type]
    except ValidationError:
        return None
    return TranscriptResult(
        transcript=transcript,
        completeness=check_completeness(
            cues=transcript.cues,
            duration=transcript.duration,
        ),
        warnings=tuple(warnings),
    )


def register(
    app,
    get_context,
) -> None:
    """Adds the `subs` command (CLI layer; imported lazily to keep the feature core light)."""
    from lingotube import commands as c
    from lingotube.writers import render

    @app.command(
        name="subs",
        help="Файл субтитров на выбранном языке.",
    )
    def subs(
        video: c.VideoArg,
        lang: c.LangOpt = None,
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
            language = c.require_lang(
                lang=lang,
                settings=ctx.settings,
            )
            fmt_ = c.require_format(
                fmt=fmt,
                settings=ctx.settings,
            )
            shift = c.require_offset(offset=offset)
            feature = await ctx.provide(provider=ctx.container.subtitles_feature)
            result = await feature.run(
                video_id=video_id,
                language=language,
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
