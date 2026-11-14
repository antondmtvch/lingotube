"""Tests of the transcript feature: ranges, re-requests, gaps, caching and resuming."""

import asyncio
import re

import pytest
from fakes import FakeAskClient

from lingotube.cache import Cache, CacheKey
from lingotube.config import Settings
from lingotube.errors import ChatUnavailableError, NetworkError
from lingotube.features.transcript import (
    MAX_GAP_REREQUESTS,
    TranscriptFeature,
    TranscriptResult,
)
from lingotube.models import VideoInfo
from lingotube.parsing import ParsedLine
from lingotube.prompts import PROMPT_VERSION

VID = "vid123"
_RANGE = re.compile(pattern=r"с (\d+(?::\d\d)+) по (\d+(?::\d\d)+)")


def secs(stamp: str) -> int:
    """Convert a timecode in m:ss or h:mm:ss form to seconds.

    Args:
        stamp: Timecode text.

    Returns:
        The number of seconds.
    """
    total = 0
    for part in stamp.split(":"):
        total = total * 60 + int(part)
    return total


def stamp(t: int) -> str:
    """Format a number of seconds as a timecode.

    Args:
        t: Time in seconds.

    Returns:
        The timecode, as m:ss or h:mm:ss.
    """
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
    """Read the range that a prompt asks for.

    Args:
        prompt: Prompt text.

    Returns:
        The start and the end of the range, in seconds.
    """
    match = _RANGE.search(string=prompt)
    assert match, prompt
    return secs(stamp=match.group(1)), secs(stamp=match.group(2))


def body(
    start: int,
    end: int,
    step: int = 10,
) -> str:
    """Build the timed lines of a chat answer, one every ``step`` seconds.

    Args:
        start: Start of the range in seconds.
        end: End of the range in seconds, not included.
        step: Distance between the lines in seconds.

    Returns:
        The timed lines, one per line of text.
    """
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
    """Build a full chat answer: an introduction, the timed lines and a closing sentence.

    Args:
        start: Start of the range in seconds.
        end: End of the range in seconds, not included.
        step: Distance between the lines in seconds.

    Returns:
        The chat answer text.
    """
    text = body(
        start=start,
        end=end,
        step=step,
    )
    return f"Вот транскрипция:\n\n{text}\n\nНадеюсь, помогло!"


def full(prompt: str) -> str:
    """Answer a prompt with the complete range that it asks for.

    Args:
        prompt: Prompt text.

    Returns:
        The chat answer text.
    """
    return lines(*requested(prompt=prompt))


def info(
    duration: float,
    language: str | None = "ru",
) -> VideoInfo:
    """Build the facts about the test video.

    Args:
        duration: Length of the video in seconds.
        language: Language code of the captions, or None.

    Returns:
        The video facts.
    """
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
    """Build a transcript feature with a temporary cache.

    Args:
        client: Fake chat client.
        tmp_path: Temporary folder of the test.
        chunk: Length of one range in seconds.
        progress: Optional progress function.

    Returns:
        The transcript feature.
    """
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
    """Check that a short video takes a single chat request."""
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
    """Check that a long video is asked range by range, in order."""
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
    """Check that timecodes of an hour-long video use the h:mm:ss format."""
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
    """Check that the progress function is called for every range."""
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
    """Check that a truncated range is asked again from the last timecode received."""

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
    """Answer a prompt the way a chat that always stops early does.

    The first answer ends at one minute, and every re-request moves the end by only 30 seconds.

    Args:
        prompt: Prompt text.

    Returns:
        The chat answer text.
    """
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
    """Check that the number of re-requests for a truncated range is limited."""
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
    """Check that a re-request without progress stops, and the part is not asked again."""
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
    assert not any("оборван" in w for w in result.warnings)  # обрыв описан проверкой полноты
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
    """Check that a line cut at the resume point is replaced, and earlier lines are ignored."""

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
    """Check that replacing a cut line keeps the earlier lines with the same timecode."""

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
    """Check that an answer without timecodes is an error, not an empty transcript."""
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
    """Check that an empty continuation stops the re-requests."""
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
    """Check that finished parts are cached and a run resumes after a failure."""

    def failing(prompt: str) -> str | Exception:
        return NetworkError(message="сеть упала") if requested(prompt=prompt)[0] == 300 else full(prompt=prompt)

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
    """Check that cached parts are counted in the progress of a resumed run."""
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
    """Check that a complete result is served from the cache without a chat request."""
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
    """Check that an incomplete result is not served from the cache as ready."""
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
    """Check that ``use_cache=False`` ignores the cached results."""
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
    """Check that a cancelled run leaves the cache readable."""

    def cancelling(prompt: str) -> str | BaseException:
        return asyncio.CancelledError() if requested(prompt=prompt)[0] == 300 else full(prompt=prompt)

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
    """Check that a language uses the translation prompt and is stored with the transcript."""
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
    """Check that the transcript may have no language when the original language is unknown."""
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
    """Check that the translated mode keeps the second of two lines with identical timecodes."""
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
    """Check that the original mode keeps all lines with identical timecodes."""
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
    """Check that lines that run past the end of their range are dropped."""

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
    """Check that long gaps are reported as warnings."""

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
    assert any(w.startswith("пропуск 4:5") and w.endswith("8:20") for w in result.warnings)


async def test_ends_fixed_and_ids_sequential(tmp_path):
    """Check that the end times are fixed and the cue ids are sequential."""
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


def holey(
    gaps: list[tuple[int, int]],
    reply=None,
):
    """Answer the first request with lines that skip the gaps, and the gap requests with a reply.

    Args:
        gaps: Ranges that the first answer leaves out.
        reply: Function that answers the gap requests, or None.

    Returns:
        The answer function for the fake chat.
    """

    def answer(prompt: str) -> str:
        start, end = requested(prompt=prompt)
        if (start, end) == (0, 300):
            return "\n".join(
                f"({stamp(t=t)}) реплика {t}"
                for t in range(
                    0,
                    300,
                    10,
                )
                if not any(a < t < b for a, b in gaps)
            )
        return reply(
            start,
            end,
        )

    return answer


async def test_inner_gap_is_asked_again_with_gap_bounds(tmp_path):
    """Check that a long gap inside a range is asked again with the bounds of the gap."""
    client = FakeAskClient(
        info=info(duration=300),
        answer=holey(
            gaps=[(90, 200)],
            reply=lambda a, b: body(
                start=a,
                end=b + 1,
                step=20,
            ),
        ),
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert len(client.prompts) == 2
    assert requested(prompt=client.prompts[1]) == (90, 200)
    starts = [c.start for c in result.transcript.cues]
    assert starts == sorted(starts)
    assert len(starts) == len(set(starts))
    assert 110 in starts and 190 in starts
    assert starts.count(90) == 1 and starts.count(200) == 1


async def test_inner_gap_stays_when_second_request_brings_nothing(tmp_path):
    """Check that a gap stays open when the repeated request brings nothing new."""
    client = FakeAskClient(
        info=info(duration=300),
        answer=holey(
            gaps=[(90, 200)],
            reply=lambda a, b: "Нет речи.",
        ),
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert len(client.prompts) == 2
    assert result.completeness.gaps


async def test_gap_requests_are_limited_per_range(tmp_path):
    """Check that the number of gap requests is limited per range."""
    gaps = [(a, a + 50) for a in range(10, 290, 60)]  # 5 пустот по 60 с
    client = FakeAskClient(
        info=info(duration=300),
        answer=holey(
            gaps=gaps,
            reply=lambda a, b: "",
        ),
    )
    await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert len(gaps) > MAX_GAP_REREQUESTS
    assert len(client.prompts) == 1 + MAX_GAP_REREQUESTS


async def test_small_gap_is_not_asked_again(tmp_path):
    """Check that a short gap is not asked again."""
    client = FakeAskClient(
        info=info(duration=300),
        answer=holey(
            gaps=[(90, 130)],
            reply=lambda a, b: "",
        ),
    )
    await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert len(client.prompts) == 1


def part_key() -> CacheKey:
    """Return the cache key of the test part.

    Returns:
        The cache key.
    """
    return CacheKey(
        video_id=VID,
        kind="transcript-part",
        language="orig",
        mode="chat",
        prompt_version=PROMPT_VERSION,
        part="0.0-300.0",
    )


async def cached_part(
    tmp_path,
    checked: bool | None,
) -> None:
    """Store a cached part with three lines, optionally marked as checked for gaps.

    Args:
        tmp_path: Temporary folder of the test.
        checked: Value of the ``gaps_checked`` flag, or None to leave it out.
    """
    data = {
        "truncated": False,
        "exhausted": False,
        "lines": [[0, None, "a"], [100, None, "b"], [290, None, "c"]],
    }
    if checked is not None:
        data["gaps_checked"] = checked
    await Cache(root=tmp_path / "cache").put(
        key=part_key(),
        value=data,
    )


async def test_cached_part_without_gaps_checked_is_filled_once(tmp_path):
    """Check that a cached part without the gap check is filled once."""
    await cached_part(
        tmp_path=tmp_path,
        checked=None,
    )
    client = FakeAskClient(
        info=info(duration=300),
        answer=lambda p: "",
    )
    await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert len(client.prompts) == 2  # две пустоты: 0:00–1:40 и 1:40–4:50
    stored = await Cache(root=tmp_path / "cache").get(key=part_key())
    assert stored["gaps_checked"] is True
    again = FakeAskClient(
        info=info(duration=300),
        answer=lambda p: "",
    )
    await feature(
        client=again,
        tmp_path=tmp_path,
    ).run(
        video_id=VID,
        language=None,
    )
    assert len(again.prompts) == 0  # итог закэширован; часть тоже проверена


async def test_cached_part_with_gaps_checked_is_not_asked(tmp_path):
    """Check that a cached part with the gap check done is not asked again."""
    await cached_part(
        tmp_path=tmp_path,
        checked=True,
    )
    client = FakeAskClient(
        info=info(duration=300),
        answer=lambda p: "",
    )
    await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert client.prompts == []


@pytest.mark.parametrize(
    argnames=("resume", "gaps"),
    argvalues=[
        (163, ((101.5, 163.0),)),  # 61.5 s of silence after the 1.5 s cue: reported
        (161, ()),  # 59.5 s: below the 60 s warning threshold
    ],
)
async def test_remaining_gap_over_60s_is_reported(
    tmp_path,
    resume,
    gaps,
):
    """Check that a gap longer than 60 seconds that remains is reported."""
    starts = [*range(0, 101, 10), *range(resume, 300, 10)]

    def answer(prompt: str) -> str:
        if requested(prompt=prompt) == (0, 300):
            return "\n".join(f"({stamp(t=t)}) реплика {t}" for t in starts)
        return ""

    client = FakeAskClient(
        info=info(duration=300),
        answer=answer,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    assert result.completeness.gaps == gaps


async def test_largest_gaps_are_chosen_when_over_the_limit(tmp_path):
    """Check that the largest gaps are chosen when there are more gaps than the limit."""
    starts = [0, 50, 110, 180, 260, 350, *range(360, 600, 10)]
    # gaps 50, 60, 70, 80, 90: all above GAP_REREQUEST, the smallest is (0, 50)

    def answer(prompt: str) -> str:
        if requested(prompt=prompt) == (0, 600):
            return "\n".join(f"({stamp(t=t)}) реплика {t}" for t in starts)
        return ""

    client = FakeAskClient(
        info=info(duration=600),
        answer=answer,
    )
    await feature(
        client=client,
        tmp_path=tmp_path,
        chunk=600,
    ).run(video_id=VID)
    asked = sorted(requested(prompt=p) for p in client.prompts[1:])
    assert MAX_GAP_REREQUESTS == 4
    assert asked == [(50, 110), (110, 180), (180, 260), (260, 350)]


async def test_fill_gaps_dedupes_found_lines_by_start_and_text(tmp_path):
    """Check that the lines found in gaps are removed as duplicates by start and text."""
    client = FakeAskClient(
        info=info(duration=300),
        answer=lambda p: "(0:50) a\n(0:50) a\n(0:50) b",
    )
    session = await client.open(video_id=VID)
    parsed = [
        ParsedLine(
            start=0.0,
            end=None,
            text="x",
        ),
        ParsedLine(
            start=100.0,
            end=None,
            text="y",
        ),
    ]
    out = await feature(
        client=client,
        tmp_path=tmp_path,
    )._fill_gaps(
        session=session,
        lines=parsed,
        start=0.0,
        end=150.0,
        language=None,
    )
    assert [(x.start, x.text) for x in out if x.start == 50.0] == [
        (50.0, "a"),
        (50.0, "b"),
    ]


class FailingWriteCache(Cache):
    """Cache whose writes always fail."""

    async def put(
        self,
        key,
        value,
    ) -> None:
        """Fail the write with an OS error.

        Args:
            key: Key to store the value under. Not used.
            value: Value to store. Not used.

        Raises:
            OSError: Always.
        """
        raise PermissionError("denied: /secret/path")


async def test_cache_write_failure_keeps_result_and_warns(tmp_path):
    """Check that a failed cache write keeps the result and adds a warning."""
    client = FakeAskClient(
        info=info(duration=300),
        answer=full,
    )
    result = await TranscriptFeature(
        ask=client,
        cache=FailingWriteCache(root=tmp_path / "cache"),
        settings=Settings(),
    ).run(video_id=VID)
    assert len(result.transcript.cues) == 30
    assert "не удалось сохранить в кэш: PermissionError" in result.warnings
    assert all("secret" not in w for w in result.warnings)


async def test_exhausted_mid_video_part_adds_warning_naming_the_range(tmp_path):
    """Check that an exhausted part in the middle of the video adds a warning that names the range."""

    def answer(prompt: str) -> str:
        start, end = requested(prompt=prompt)
        if start < 300:
            return lines(
                start=0,
                end=61,
            )  # the chat stops at 1:00 whatever is asked
        return lines(
            start=start,
            end=end,
        )

    client = FakeAskClient(
        info=info(duration=900),
        answer=answer,
    )
    result = await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(video_id=VID)
    ranged = [w for w in result.warnings if "0:00–5:00" in w]
    assert len(ranged) == 1
    assert "1:00" in ranged[0] and "оборван" not in ranged[0]
    assert not any("5:00–10:00" in w or "10:00–15:00" in w for w in result.warnings)


async def test_on_opened_runs_after_open_before_any_chat_request(tmp_path):
    """Check that the on-opened callback runs after the chat opens and before any question."""
    client = FakeAskClient(
        info=info(duration=300),
        answer=full,
    )
    seen: list[tuple[str | None, int]] = []

    async def on_opened(opened: VideoInfo) -> None:
        seen.append((opened.language, len(client.prompts)))

    await feature(
        client=client,
        tmp_path=tmp_path,
    ).run(
        video_id=VID,
        on_opened=on_opened,
    )
    assert seen == [("ru", 0)]
    assert client.opened == [VID]


async def test_on_opened_error_stops_before_any_chat_request(tmp_path):
    """Check that an error in the on-opened callback stops the run before any question."""
    client = FakeAskClient(
        info=info(duration=300),
        answer=full,
    )

    async def on_opened(opened: VideoInfo) -> None:
        raise RuntimeError("stop")

    with pytest.raises(expected_exception=RuntimeError):
        await feature(
            client=client,
            tmp_path=tmp_path,
        ).run(
            video_id=VID,
            on_opened=on_opened,
        )
    assert client.prompts == []


async def test_on_opened_not_called_when_result_is_cached(tmp_path):
    """Check that the on-opened callback is not called when the result is cached."""
    client = FakeAskClient(
        info=info(duration=300),
        answer=full,
    )
    feat = feature(
        client=client,
        tmp_path=tmp_path,
    )
    await feat.run(video_id=VID)
    called: list[VideoInfo] = []

    async def on_opened(opened: VideoInfo) -> None:
        called.append(opened)

    await feat.run(
        video_id=VID,
        on_opened=on_opened,
    )
    assert called == []
