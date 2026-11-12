"""Agent mode: validate an externally translated transcript against the cached original and cache it."""

from dataclasses import replace
from typing import Any

from lingotube.cache import Cache, CacheKey
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


def validate_translation(original: Transcript, translated: dict[str, Any], language: str) -> Transcript:
    """Checks `translated` against `original`; original times always win.

    All problems are collected into one ValidationError listing the offending ids.
    """
    parsed = Transcript.from_dict(translated)
    if parsed.video_id != original.video_id:
        raise ValidationError(
            f"video_id перевода ({parsed.video_id}) не совпадает с видео оригинала ({original.video_id})."
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
        problems.append(f"отсутствуют id: {_ids(list(missing))}")
    if extra := seen - expected:
        problems.append(f"лишние id: {_ids(list(extra))}")
    if duplicate:
        problems.append(f"повторяются id: {_ids(list(duplicate))}")
    if empty:
        problems.append(f"пустой текст у id: {_ids(list(empty))}")
    if problems:
        raise ValidationError(
            "Перевод не совпадает с оригиналом: " + "; ".join(problems) + ".",
            hint="Верните все реплики оригинала, по одной на id, с непустым текстом.",
        )
    cues = tuple(Cue(c.id, c.start, c.end, texts[c.id]) for c in original.cues)
    return replace(original, language=language, cues=cues)


class BuildFeature:
    def __init__(self, cache: Cache) -> None:
        self._cache = cache

    async def run(self, video_id: str, language: str, translated: dict[str, Any]) -> Transcript:
        original = await load_cached_transcript(self._cache, video_id, require_complete=False)
        if original is None:
            raise ValidationError(
                "Оригинальная транскрипция этого видео не найдена в кэше.",
                hint="Сначала выполните `lingotube transcript <url>`.",
            )
        result = validate_translation(original, translated, language)
        await self._cache.put(
            CacheKey(video_id, "subtitles", language, "agent", PROMPT_VERSION), result.to_dict()
        )
        return result
