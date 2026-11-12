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
_RANGE = re.compile(pattern=r"с (\d+(?::\d\d)+) по (\d+(?::\d\d)+)")


def secs(stamp: str) -> int:
    total = 0
    for part in stamp.split(":"):
        total = total * 60 + int(part)
    return total


def stamp(t: int) -> str:
    h, rest = divmod(
        t,
        3600,
    )
    m, s = divmod(
        rest,
        60,
    )
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def requested(prompt: str) -> tuple[int, int]:
    match = _RANGE.search(string=prompt)
    assert match, prompt
    return secs(stamp=match.group(1)), secs(stamp=match.group(2))


def body(
    start: int,
    end: int,
    step: int = 10,
) -> str:
    """Только строки реплик каждые step секунд в [start, end)."""
    return "\n".join(
        f"({stamp(t=t)}) реплика {t}"
        for t in range(
            start,
            end,
            step,
        )
    )


def lines(
    start: int,
    end: int,
    step: int = 10,
) -> str:
    """Чат-ответ: вступление, реплики каждые step секунд в [start, end), заключение."""
    text = body(
        start=start,
        end=end,
        step=step,
    )
    return f"Вот транскрипция:\n\n{text}\n\nНадеюсь, помогло!"


def full(prompt: str) -> str:
    return lines(*requested(prompt=prompt))


def info(
    duration: float,
    language: str | None = "ru",
) -> VideoInfo:
    return VideoInfo(
        video_id=VID,
        duration=duration,
        title="Title",
        language=language,
    )


def feature(
    client,
    tmp_path,
    chunk: int = 300,
    progress=None,
) -> TranscriptFeature:
    settings = Settings(chunk_seconds=chunk)
    if progress is None:
        return TranscriptFeature(
            ask=client,
            cache=Cache(root=tmp_path / "cache"),
            settings=settings,
        )
    return TranscriptFeature(
        ask=client,
        cache=Cache(root=tmp_path / "cache"),
        settings=settings,
        progress=progress,
    )


async def test_short_video_single_request(tmp_path):
    client = FakeAskClient(
        info=info(duration=300),
        answer=full,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert isinstance(
        result,
        TranscriptResult,
    )
    assert len(client.prompts) == 1
    assert client.opened == [VID]
    assert [c.text for c in result.transcript.cues] == [
        f"реплика {t}"
        for t in range(
            0,
            300,
            10,
        )
    ]
    assert result.completeness.complete
    assert result.transcript.video_id == VID
    assert result.transcript.duration == 300
    assert result.transcript.language == "ru"
    assert result.transcript.prompt_version == PROMPT_VERSION
    assert result.warnings == ()


async def test_long_video_requests_each_range_in_order(tmp_path):
    client = FakeAskClient(
        info=info(duration=1500),
        answer=full,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
        chunk=600,
    ).run(video_id=VID)
    assert len(client.prompts) == 3
    assert "с 0:00 по 10:00" in client.prompts[0]
    assert "с 10:00 по 20:00" in client.prompts[1]
    assert "с 20:00 по 25:00" in client.prompts[2]
    assert client.opened == [VID]  # один чат на видео
    assert [c.start for c in result.transcript.cues] == list(
        range(
            0,
            1500,
            10,
        )
    )
    assert result.completeness.complete


async def test_hour_long_video_uses_hour_format(tmp_path):
    client = FakeAskClient(
        info=info(duration=3900),
        answer=full,
    )
    await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert "с 55:00 по 1:00:00" in client.prompts[11]
    assert "с 1:00:00 по 1:05:00" in client.prompts[12]


async def test_progress_reported(tmp_path):
    calls = []
    client = FakeAskClient(
        info=info(duration=1500),
        answer=full,
    )
    await feature(
        client=client,
        tmp_path=tmp_path,
        chunk=600,
        progress=lambda d, t: calls.append((d, t)),
    ).run(video_id=VID)
    assert calls == [(1, 3), (2, 3), (3, 3)]


async def test_truncated_range_is_requested_again_from_last_timecode(tmp_path):
    def answer(prompt: str) -> str:
        start, end = requested(prompt=prompt)
        return (
            lines(
                start=0,
                end=241,
            )
            if start == 0
            else lines(
                start=start,
                end=end,
            )
        )  # 1-й ответ кончается на 4:00

    client = FakeAskClient(
        info=info(duration=600),
        answer=answer,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
        chunk=600,
    ).run(video_id=VID)
    assert len(client.prompts) == 2
    assert "с 4:00 по 10:00" in client.prompts[1]
    starts = [c.start for c in result.transcript.cues]
    assert starts == list(
        range(
            0,
            600,
            10,
        )
    )  # дублей на стыке нет
    assert [c.text for c in result.transcript.cues].count("реплика 240") == 1
    assert result.completeness.complete
    assert result.warnings == ()


def creeping(prompt: str) -> str:
    """Чат всегда обрывает: первый ответ до 1:00, каждый дозапрос продвигается лишь на 30 с."""
    start, _ = requested(prompt=prompt)
    return (
        lines(
            start=0,
            end=61,
        )
        if start == 0
        else lines(
            start=start,
            end=start + 31,
        )
    )


async def test_truncation_retry_is_bounded(tmp_path):
    client = FakeAskClient(
        info=info(duration=300),
        answer=creeping,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert len(client.prompts) == 4  # 1 запрос + не более 3 дозапросов
    assert "с 1:00 по 5:00" in client.prompts[1]
    assert "с 1:30 по 5:00" in client.prompts[2]
    assert "с 2:00 по 5:00" in client.prompts[3]
    assert not result.completeness.complete
    assert any("оборван" in w for w in result.warnings)


async def test_rerequest_without_progress_stops_and_part_is_not_reasked(tmp_path):
    client = FakeAskClient(
        info=info(duration=300),
        answer=lambda p: lines(
            start=0,
            end=61,
        ),
    )  # дозапрос не даёт ничего нового
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    # первый дозапрос без продвижения — дальше не спрашиваем
    assert len(client.prompts) == 2
    assert not result.completeness.complete
    assert not any(
        "оборван" in w for w in result.warnings
    )  # обрыв описан проверкой полноты
    assert any("неполная" in w for w in result.warnings)
    second = FakeAskClient(
        info=info(duration=300),
        answer=full,
    )
    again = await feature(
        client=second,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert second.prompts == []  # исчерпанный отрезок не дозапрашивается снова
    assert again.transcript == result.transcript


async def test_cut_line_replaced_and_lines_before_resume_ignored(tmp_path):
    def answer(prompt: str) -> str:
        start, end = requested(prompt=prompt)
        if start == 0:
            return (
                body(
                    start=0,
                    end=240,
                )
                + "\n(4:00) реп"
            )  # оборвано посреди реплики
        return "(3:50) реплика двести тридцать, другими словами\n" + body(
            start=240,
            end=600,
        )

    client = FakeAskClient(
        info=info(duration=600),
        answer=answer,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
        chunk=600,
    ).run(video_id=VID)
    assert len(client.prompts) == 2
    assert "с 4:00 по 10:00" in client.prompts[1]
    assert [c.text for c in result.transcript.cues] == [
        f"реплика {t}"
        for t in range(
            0,
            600,
            10,
        )
    ]


async def test_cut_line_replacement_keeps_earlier_lines_at_same_timecode(tmp_path):
    def answer(prompt: str) -> str:
        start, end = requested(prompt=prompt)
        if start == 0:
            return (
                body(
                    start=0,
                    end=240,
                )
                + "\n(4:00) первая часть\n(4:00) втор"
            )
        return "(4:00) вторая часть\n" + body(
            start=250,
            end=600,
        )

    client = FakeAskClient(
        info=info(duration=600),
        answer=answer,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
        chunk=600,
    ).run(video_id=VID)
    at_240 = [c.text for c in result.transcript.cues if c.start == 240]
    assert at_240 == ["первая часть вторая часть"]


async def test_no_timecodes_is_error_not_empty_file(tmp_path):
    client = FakeAskClient(
        info=info(duration=300),
        answer=lambda p: "Извините, не могу помочь с этим.",
    )
    with pytest.raises(expected_exception=ChatUnavailableError) as exc:
        await feature(
            client=client,
            tmp_path=tmp_path,
        ).run(video_id=VID)
    assert "транскрип" in exc.value.message
    final = CacheKey(
        video_id=VID,
        kind="transcript",
        language="orig",
        mode="chat",
        prompt_version=PROMPT_VERSION,
    )
    assert await Cache(root=tmp_path / "cache").get(key=final) is None


async def test_empty_continuation_stops_rerequests(tmp_path):
    client = FakeAskClient(
        info=info(duration=300),
        answer=lambda p: (
            lines(
                start=0,
                end=61,
            )
            if "с 0:00" in p
            else "Больше ничего нет."
        ),
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert len(client.prompts) == 2
    assert not result.completeness.complete


async def test_parts_cached_and_resume_after_failure(tmp_path):
    def failing(prompt: str) -> str | Exception:
        return (
            NetworkError(message="сеть упала")
            if requested(prompt=prompt)[0] == 300
            else full(prompt=prompt)
        )

    first = FakeAskClient(
        info=info(duration=900),
        answer=failing,
    )
    with pytest.raises(expected_exception=NetworkError):
        await feature(
            client=first,
            tmp_path=tmp_path,
        ).run(video_id=VID)
    second = FakeAskClient(
        info=info(duration=900),
        answer=full,
    )
    result = await feature(
        client=second,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert len(second.prompts) == 2
    assert "с 5:00 по 10:00" in second.prompts[0]
    assert "с 10:00 по 15:00" in second.prompts[1]
    assert [c.start for c in result.transcript.cues] == list(
        range(
            0,
            900,
            10,
        )
    )
    assert result.completeness.complete


async def test_resume_counts_cached_parts_in_progress(tmp_path):
    first = FakeAskClient(
        info=info(duration=900),
        answer=lambda p: NetworkError(message="x") if "с 5:00" in p else full(prompt=p),
    )
    with pytest.raises(expected_exception=NetworkError):
        await feature(
            client=first,
            tmp_path=tmp_path,
        ).run(video_id=VID)
    calls = []
    second = FakeAskClient(
        info=info(duration=900),
        answer=full,
    )
    await feature(
        client=second,
        tmp_path=tmp_path,
        progress=lambda d, t: calls.append((d, t)),
    ).run(video_id=VID)
    assert calls == [(1, 3), (2, 3), (3, 3)]


async def test_complete_result_served_from_cache(tmp_path):
    first = FakeAskClient(
        info=info(duration=600),
        answer=full,
    )
    r1 = await feature(
        client=first,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    second = FakeAskClient(
        info=info(duration=600),
        answer=full,
    )
    r2 = await feature(
        client=second,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert second.prompts == []
    assert second.opened == []
    assert r2.transcript == r1.transcript
    assert r2.completeness == r1.completeness
    assert r2.warnings == r1.warnings


async def test_incomplete_result_not_served_as_ready(tmp_path):
    first = FakeAskClient(
        info=info(duration=300),
        answer=creeping,
    )  # дозапросы кончились, чат ещё продвигался
    r1 = await feature(
        client=first,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert not r1.completeness.complete
    final = await Cache(root=tmp_path / "cache").get(
        key=CacheKey(
            video_id=VID,
            kind="transcript",
            language="orig",
            mode="chat",
            prompt_version=PROMPT_VERSION,
        )
    )
    assert final is not None and final["complete"] is False
    second = FakeAskClient(
        info=info(duration=300),
        answer=full,
    )
    r2 = await feature(
        client=second,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert second.prompts  # снова обращается в чат
    assert "с 2:30 по 5:00" in second.prompts[0]  # дозапрашивает недостающее
    assert r2.completeness.complete
    assert [c.start for c in r2.transcript.cues] == list(
        range(
            0,
            300,
            10,
        )
    )


async def test_use_cache_false_ignores_cache(tmp_path):
    first = FakeAskClient(
        info=info(duration=600),
        answer=full,
    )
    await feature(
        client=first,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    second = FakeAskClient(
        info=info(duration=600),
        answer=full,
    )
    result = await feature(
        client=second,
        tmp_path=tmp_path,
    ).run(
        video_id=VID,
        use_cache=False,
    )
    assert len(second.prompts) == 2
    assert second.opened == [VID]
    assert result.completeness.complete


async def test_cancelled_run_leaves_cache_readable(tmp_path):
    def cancelling(prompt: str) -> str | BaseException:
        return (
            asyncio.CancelledError()
            if requested(prompt=prompt)[0] == 300
            else full(prompt=prompt)
        )

    first = FakeAskClient(
        info=info(duration=900),
        answer=cancelling,
    )
    with pytest.raises(expected_exception=asyncio.CancelledError):
        await feature(
            client=first,
            tmp_path=tmp_path,
        ).run(video_id=VID)
    part = CacheKey(
        video_id=VID,
        kind="transcript-part",
        language="orig",
        mode="chat",
        prompt_version=PROMPT_VERSION,
        part="0.0-300.0",
    )
    assert await Cache(root=tmp_path / "cache").get(key=part) is not None
    second = FakeAskClient(
        info=info(duration=900),
        answer=full,
    )
    await feature(
        client=second,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert len(second.prompts) == 2


async def test_language_set_uses_translated_prompt_and_tags_language(tmp_path):
    client = FakeAskClient(
        info=info(
            duration=300,
            language="ru",
        ),
        answer=full,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(
        video_id=VID,
        language="English",
    )
    assert "переведи" in client.prompts[0]
    assert "English" in client.prompts[0]
    assert result.transcript.language == "English"
    cache = Cache(root=tmp_path / "cache")
    assert (
        await cache.get(
            key=CacheKey(
                video_id=VID,
                kind="transcript",
                language="English",
                mode="chat",
                prompt_version=PROMPT_VERSION,
            )
        )
        is not None
    )
    assert (
        await cache.get(
            key=CacheKey(
                video_id=VID,
                kind="transcript",
                language="orig",
                mode="chat",
                prompt_version=PROMPT_VERSION,
            )
        )
        is None
    )
    part = CacheKey(
        video_id=VID,
        kind="transcript-part",
        language="English",
        mode="chat",
        prompt_version=PROMPT_VERSION,
        part="0.0-300.0",
    )
    assert await cache.get(key=part) is not None


async def test_original_language_may_be_unknown(tmp_path):
    client = FakeAskClient(
        info=info(
            duration=300,
            language=None,
        ),
        answer=full,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert result.transcript.language is None
    assert "переведи" not in client.prompts[0]


async def test_translated_mode_keeps_second_of_identical_timecodes(tmp_path):
    answer = "(0:05) Hello\n(0:05) Привет\n(0:09) World\n(0:09) Мир"
    client = FakeAskClient(
        info=info(duration=12),
        answer=lambda p: answer,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(
        video_id=VID,
        language="Russian",
    )
    assert [c.text for c in result.transcript.cues] == ["Привет", "Мир"]


async def test_original_mode_keeps_lines_with_identical_timecodes(tmp_path):
    client = FakeAskClient(
        info=info(duration=12),
        answer=lambda p: "(0:05) Hello\n(0:05) Привет",
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert [c.text for c in result.transcript.cues] == ["Hello Привет"]


async def test_overshoot_past_chunk_end_is_dropped(tmp_path):
    def answer(prompt: str) -> str:
        start, end = requested(prompt=prompt)
        body = lines(
            start=start,
            end=end,
        )
        if start == 0:  # чат заходит за конец отрезка 0:00–5:00
            body = body.replace(
                "\n\nНадеюсь",
                "\n(5:00) чужая реплика\n(5:10) ещё чужая\n\nНадеюсь",
            )
        return body

    client = FakeAskClient(
        info=info(duration=600),
        answer=answer,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    # без отбрасывания merge склеил бы «реплика 300 чужая реплика»
    assert [c.text for c in result.transcript.cues] == [
        f"реплика {t}"
        for t in range(
            0,
            600,
            10,
        )
    ]


async def test_gaps_reported_as_warnings(tmp_path):
    def answer(prompt: str) -> str:
        start, end = requested(prompt=prompt)
        return (
            lines(
                start=start,
                end=end,
            )
            if start == 0
            else lines(
                start=max(
                    start,
                    500,
                ),
                end=end,
            )
        )  # тишина 4:51–8:20

    client = FakeAskClient(
        info=info(duration=900),
        answer=answer,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert result.completeness.complete
    assert result.completeness.gaps
    assert any(
        w.startswith("пропуск 4:5") and w.endswith("8:20") for w in result.warnings
    )


async def test_ends_fixed_and_ids_sequential(tmp_path):
    client = FakeAskClient(
        info=info(duration=900),
        answer=full,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    cues = result.transcript.cues
    assert [c.id for c in cues] == list(
        range(
            1,
            len(cues) + 1,
        )
    )
    for cue, nxt in zip(
        cues,
        cues[1:],
        strict=False,
    ):
        assert cue.end is not None and cue.start < cue.end <= nxt.start
    assert cues[-1].end is not None and cues[-1].end <= 900
