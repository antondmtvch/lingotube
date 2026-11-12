"""Capability "subtitles": a transcript in the target language.

- no translator configured -> chat mode: the chat translates directly (cached by TranscriptFeature);
- translator configured -> own-model mode: the original is taken first (cached, so a second
  language needs no new YouTube requests), then translated; the translation is cached per
  language. A translation of an incomplete original is never cached: it is redone next time.
"""

from dataclasses import replace

from lingotube.assemble import check_completeness
from lingotube.cache import Cache, CacheKey
from lingotube.errors import ValidationError
from lingotube.features.transcript import TranscriptFeature, TranscriptResult
from lingotube.models import Transcript
from lingotube.prompts import PROMPT_VERSION
from lingotube.translate.base import Translator

KIND = "subtitles"
MODE = "own-model"


def _primary(language: str | None) -> str:
    return (language or "").replace("_", "-").split("-")[0].strip().lower()


class SubtitlesFeature:
    def __init__(self, transcripts: TranscriptFeature, translator: Translator | None, cache: Cache) -> None:
        self._transcripts = transcripts
        self._translator = translator
        self._cache = cache

    async def run(self, video_id: str, language: str, *, use_cache: bool = True) -> TranscriptResult:
        if self._translator is None:
            return await self._transcripts.run(video_id, language, use_cache=use_cache)

        key = CacheKey(video_id, KIND, language, MODE, PROMPT_VERSION)
        if use_cache:
            cached = _load(await self._cache.get(key))
            if cached is not None:
                return cached

        original = await self._transcripts.run(video_id, None, use_cache=use_cache)
        source = original.transcript
        if _primary(source.language) == _primary(language):
            cues = source.cues
        else:
            cues = tuple(await self._translator.translate(source.cues, language))
        transcript = replace(source, language=language, cues=cues)
        result = TranscriptResult(transcript, original.completeness, original.warnings)
        if original.completeness.complete:
            await self._cache.put(
                key,
                {"complete": True, "warnings": list(result.warnings), "transcript": transcript.to_dict()},
            )
        return result


def _load(data: dict | None) -> TranscriptResult | None:
    if data is None or data.get("complete") is not True:
        return None
    warnings = data.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
        return None
    try:
        transcript = Transcript.from_dict(data.get("transcript"))  # type: ignore[arg-type]
    except ValidationError:
        return None
    return TranscriptResult(
        transcript, check_completeness(transcript.cues, transcript.duration), tuple(warnings)
    )
