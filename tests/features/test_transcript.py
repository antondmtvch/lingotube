import asyncio
import re

import pytest
from fakes import FakeAskClient

from lingotube.cache import Cache, CacheKey
from lingotube.config import Settings
from lingotube.errors import ChatUnavailableError, NetworkError
from lingotube.features.transcript import TranscriptFeature, TranscriptResult
from lingotube.models import VideoInfo
from lingotube.prompts import PROMPT_VERSION

VID = "vid123"
_RANGE = re.compile(r"с (\d+(?::\d\d)+) по (\d+(?::\d\d)+)")


def secs(stamp: str) -> int:
    total = 0
    for part in stamp.split(":"):
        total = total * 60 + int(part)
    return total


def stamp(t: int) -> str:
    h, rest = divmod(t, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def requested(prompt: str) -> tuple[int, int]:
    match = _RANGE.search(prompt)
    assert match, prompt
    return secs(match.group(1)), secs(match.group(2))


def lines(start: int, end: int, step: int = 10) -> str:
    """Чат-ответ: вступление, реплики каждые step секунд в [start, end), заключение."""
    body = "\n".join(f"({stamp(t)}) реплика {t}" for t in range(start, end, step))
    return f"Вот транскрипция:\n\n{body}\n\nНадеюсь, помогло!"


def full(prompt: str) -> str:
    return lines(*requested(prompt))


def info(duration: float, language: str | None = "ru") -> VideoInfo:
    return VideoInfo(VID, duration, "Title", language)


def feature(client, tmp_path, chunk: int = 300, progress=None) -> TranscriptFeature:
    settings = Settings(chunk_seconds=chunk)
    if progress is None:
        return TranscriptFeature(client, Cache(tmp_path / "cache"), settings)
    return TranscriptFeature(client, Cache(tmp_path / "cache"), settings, progress)


async def test_short_video_single_request(tmp_path):
    client = FakeAskClient(info(300), full)
    result = await feature(client, tmp_path).run(VID)
    assert isinstance(result, TranscriptResult)
    assert len(client.prompts) == 1
    assert client.opened == [VID]
    assert [c.text for c in result.transcript.cues] == [f"реплика {t}" for t in range(0, 300, 10)]
    assert result.completeness.complete
    assert result.transcript.video_id == VID
    assert result.transcript.duration == 300
    assert result.transcript.language == "ru"
    assert result.transcript.prompt_version == PROMPT_VERSION
    assert result.warnings == ()


async def test_long_video_requests_each_range_in_order(tmp_path):
    client = FakeAskClient(info(1500), full)
    result = await feature(client, tmp_path, chunk=600).run(VID)
    assert len(client.prompts) == 3
    assert "с 0:00 по 10:00" in client.prompts[0]
    assert "с 10:00 по 20:00" in client.prompts[1]
    assert "с 20:00 по 25:00" in client.prompts[2]
    assert client.opened == [VID]  # один чат на видео
    assert [c.start for c in result.transcript.cues] == list(range(0, 1500, 10))
    assert result.completeness.complete


async def test_hour_long_video_uses_hour_format(tmp_path):
    client = FakeAskClient(info(3900), full)
    await feature(client, tmp_path).run(VID)
    assert "с 55:00 по 1:00:00" in client.prompts[11]
    assert "с 1:00:00 по 1:05:00" in client.prompts[12]


async def test_progress_reported(tmp_path):
    calls = []
    client = FakeAskClient(info(1500), full)
    await feature(client, tmp_path, chunk=600, progress=lambda d, t: calls.append((d, t))).run(VID)
    assert calls == [(1, 3), (2, 3), (3, 3)]


async def test_truncated_range_is_requested_again_from_last_timecode(tmp_path):
    def answer(prompt: str) -> str:
        start, end = requested(prompt)
        return lines(0, 241) if start == 0 else lines(start, end)  # 1-й ответ кончается на 4:00

    client = FakeAskClient(info(600), answer)
    result = await feature(client, tmp_path, chunk=600).run(VID)
    assert len(client.prompts) == 2
    assert "с 4:00 по 10:00" in client.prompts[1]
    starts = [c.start for c in result.transcript.cues]
    assert starts == list(range(0, 600, 10))  # дублей на стыке нет
    assert [c.text for c in result.transcript.cues].count("реплика 240") == 1
    assert result.completeness.complete
    assert result.warnings == ()


async def test_truncation_retry_is_bounded(tmp_path):
    client = FakeAskClient(info(300), lambda p: lines(0, 61))  # чат всегда обрывает на 1:00
    result = await feature(client, tmp_path).run(VID)
    assert len(client.prompts) == 4  # 1 запрос + не более 3 дозапросов
    assert all("с 1:00 по 5:00" in p for p in client.prompts[1:])
    assert not result.completeness.complete
    assert any("оборван" in w for w in result.warnings)


async def test_no_timecodes_is_error_not_empty_file(tmp_path):
    client = FakeAskClient(info(300), lambda p: "Извините, не могу помочь с этим.")
    with pytest.raises(ChatUnavailableError) as exc:
        await feature(client, tmp_path).run(VID)
    assert "транскрип" in exc.value.message
    final = CacheKey(VID, "transcript", "orig", "chat", PROMPT_VERSION)
    assert await Cache(tmp_path / "cache").get(final) is None


async def test_empty_continuation_stops_rerequests(tmp_path):
    client = FakeAskClient(info(300), lambda p: lines(0, 61) if "с 0:00" in p else "Больше ничего нет.")
    result = await feature(client, tmp_path).run(VID)
    assert len(client.prompts) == 2
    assert not result.completeness.complete


async def test_parts_cached_and_resume_after_failure(tmp_path):
    def failing(prompt: str) -> str | Exception:
        return NetworkError("сеть упала") if requested(prompt)[0] == 300 else full(prompt)

    first = FakeAskClient(info(900), failing)
    with pytest.raises(NetworkError):
        await feature(first, tmp_path).run(VID)
    second = FakeAskClient(info(900), full)
    result = await feature(second, tmp_path).run(VID)
    assert len(second.prompts) == 2
    assert "с 5:00 по 10:00" in second.prompts[0]
    assert "с 10:00 по 15:00" in second.prompts[1]
    assert [c.start for c in result.transcript.cues] == list(range(0, 900, 10))
    assert result.completeness.complete


async def test_resume_counts_cached_parts_in_progress(tmp_path):
    first = FakeAskClient(info(900), lambda p: NetworkError("x") if "с 5:00" in p else full(p))
    with pytest.raises(NetworkError):
        await feature(first, tmp_path).run(VID)
    calls = []
    second = FakeAskClient(info(900), full)
    await feature(second, tmp_path, progress=lambda d, t: calls.append((d, t))).run(VID)
    assert calls == [(1, 3), (2, 3), (3, 3)]


async def test_complete_result_served_from_cache(tmp_path):
    first = FakeAskClient(info(600), full)
    r1 = await feature(first, tmp_path).run(VID)
    second = FakeAskClient(info(600), full)
    r2 = await feature(second, tmp_path).run(VID)
    assert second.prompts == []
    assert second.opened == []
    assert r2.transcript == r1.transcript
    assert r2.completeness == r1.completeness
    assert r2.warnings == r1.warnings


async def test_incomplete_result_not_served_as_ready(tmp_path):
    first = FakeAskClient(info(300), lambda p: lines(0, 61))
    r1 = await feature(first, tmp_path).run(VID)
    assert not r1.completeness.complete
    final = await Cache(tmp_path / "cache").get(CacheKey(VID, "transcript", "orig", "chat", PROMPT_VERSION))
    assert final is not None and final["complete"] is False
    second = FakeAskClient(info(300), full)
    r2 = await feature(second, tmp_path).run(VID)
    assert second.prompts  # снова обращается в чат
    assert "с 1:00 по 5:00" in second.prompts[0]  # дозапрашивает недостающее
    assert r2.completeness.complete
    assert [c.start for c in r2.transcript.cues] == list(range(0, 300, 10))


async def test_use_cache_false_ignores_cache(tmp_path):
    first = FakeAskClient(info(600), full)
    await feature(first, tmp_path).run(VID)
    second = FakeAskClient(info(600), full)
    result = await feature(second, tmp_path).run(VID, use_cache=False)
    assert len(second.prompts) == 2
    assert second.opened == [VID]
    assert result.completeness.complete


async def test_cancelled_run_leaves_cache_readable(tmp_path):
    def cancelling(prompt: str) -> str | BaseException:
        return asyncio.CancelledError() if requested(prompt)[0] == 300 else full(prompt)

    first = FakeAskClient(info(900), cancelling)
    with pytest.raises(asyncio.CancelledError):
        await feature(first, tmp_path).run(VID)
    part = CacheKey(VID, "transcript-part", "orig", "chat", PROMPT_VERSION, part="0.0-300.0")
    assert await Cache(tmp_path / "cache").get(part) is not None
    second = FakeAskClient(info(900), full)
    await feature(second, tmp_path).run(VID)
    assert len(second.prompts) == 2


async def test_language_set_uses_translated_prompt_and_tags_language(tmp_path):
    client = FakeAskClient(info(300, language="ru"), full)
    result = await feature(client, tmp_path).run(VID, "English")
    assert "переведи" in client.prompts[0]
    assert "English" in client.prompts[0]
    assert result.transcript.language == "English"
    cache = Cache(tmp_path / "cache")
    assert await cache.get(CacheKey(VID, "transcript", "English", "chat", PROMPT_VERSION)) is not None
    assert await cache.get(CacheKey(VID, "transcript", "orig", "chat", PROMPT_VERSION)) is None
    part = CacheKey(VID, "transcript-part", "English", "chat", PROMPT_VERSION, part="0.0-300.0")
    assert await cache.get(part) is not None


async def test_original_language_may_be_unknown(tmp_path):
    client = FakeAskClient(info(300, language=None), full)
    result = await feature(client, tmp_path).run(VID)
    assert result.transcript.language is None
    assert "переведи" not in client.prompts[0]


async def test_translated_mode_keeps_second_of_identical_timecodes(tmp_path):
    answer = "(0:05) Hello\n(0:05) Привет\n(0:09) World\n(0:09) Мир"
    client = FakeAskClient(info(12), lambda p: answer)
    result = await feature(client, tmp_path).run(VID, "Russian")
    assert [c.text for c in result.transcript.cues] == ["Привет", "Мир"]


async def test_original_mode_keeps_lines_with_identical_timecodes(tmp_path):
    client = FakeAskClient(info(12), lambda p: "(0:05) Hello\n(0:05) Привет")
    result = await feature(client, tmp_path).run(VID)
    assert [c.text for c in result.transcript.cues] == ["Hello Привет"]


async def test_overshoot_past_chunk_end_is_dropped(tmp_path):
    def answer(prompt: str) -> str:
        start, end = requested(prompt)
        body = lines(start, end)
        if start == 0:  # чат заходит за конец отрезка 0:00–5:00
            body = body.replace("\n\nНадеюсь", "\n(5:00) чужая реплика\n(5:10) ещё чужая\n\nНадеюсь")
        return body

    client = FakeAskClient(info(600), answer)
    result = await feature(client, tmp_path).run(VID)
    # без отбрасывания merge склеил бы «реплика 300 чужая реплика»
    assert [c.text for c in result.transcript.cues] == [f"реплика {t}" for t in range(0, 600, 10)]


async def test_gaps_reported_as_warnings(tmp_path):
    def answer(prompt: str) -> str:
        start, end = requested(prompt)
        return lines(start, end) if start == 0 else lines(max(start, 500), end)  # тишина 4:51–8:20

    client = FakeAskClient(info(900), answer)
    result = await feature(client, tmp_path).run(VID)
    assert result.completeness.complete
    assert result.completeness.gaps
    assert any(w.startswith("пропуск 4:5") and w.endswith("8:20") for w in result.warnings)


async def test_ends_fixed_and_ids_sequential(tmp_path):
    client = FakeAskClient(info(900), full)
    result = await feature(client, tmp_path).run(VID)
    cues = result.transcript.cues
    assert [c.id for c in cues] == list(range(1, len(cues) + 1))
    for cue, nxt in zip(cues, cues[1:], strict=False):
        assert cue.end is not None and cue.start < cue.end <= nxt.start
    assert cues[-1].end is not None and cues[-1].end <= 900
