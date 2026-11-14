"""Tests of the summary feature."""

import pytest
from fakes import FakeAskClient

from lingotube.cache import Cache, CacheKey
from lingotube.errors import ChatUnavailableError
from lingotube.features.summary import SummaryFeature
from lingotube.models import VideoInfo
from lingotube.prompts import PROMPT_VERSION

VID = "vid123"
INFO = VideoInfo(
    video_id=VID,
    duration=100.0,
    title="t",
    language="en",
)


def make(
    tmp_path,
    answer,
):
    """Build a fake chat client and a summary feature with a temporary cache.

    Args:
        tmp_path: Temporary folder of the test.
        answer: Function that returns the answer to a prompt.

    Returns:
        The fake client and the summary feature.
    """
    client = FakeAskClient(
        info=INFO,
        answer=answer,
    )
    return client, SummaryFeature(
        ask=client,
        cache=Cache(root=tmp_path / "cache"),
    )


async def test_summary_single_request_in_language(tmp_path):
    """Check that a summary takes one chat request in the requested language."""
    client, feature = make(
        tmp_path=tmp_path,
        answer=lambda p: "# Итог\n- мысль",
    )
    assert (
        await feature.run(
            video_id=VID,
            language="русский",
        )
        == "# Итог\n- мысль"
    )
    assert len(client.prompts) == 1
    assert "русский" in client.prompts[0]


async def test_summary_cached_per_language(tmp_path):
    """Check that summaries are cached separately for each language."""
    client, feature = make(
        tmp_path=tmp_path,
        answer=lambda p: "текст " + ("ru" if "русский" in p else "de"),
    )
    assert (
        await feature.run(
            video_id=VID,
            language="русский",
        )
        == "текст ru"
    )
    assert (
        await feature.run(
            video_id=VID,
            language="русский",
        )
        == "текст ru"
    )
    assert len(client.prompts) == 1
    assert (
        await feature.run(
            video_id=VID,
            language="немецкий",
        )
        == "текст de"
    )
    assert len(client.prompts) == 2
    assert (
        await feature.run(
            video_id=VID,
            language="русский",
            use_cache=False,
        )
        == "текст ru"
    )
    assert len(client.prompts) == 3
    stored = await Cache(root=tmp_path / "cache").get(
        key=CacheKey(
            video_id=VID,
            kind="summary",
            language="русский",
            mode="chat",
            prompt_version=PROMPT_VERSION,
        )
    )
    assert stored == {"text": "текст ru"}


@pytest.mark.parametrize(
    argnames="answer",
    argvalues=["", "  \n "],
)
async def test_summary_empty_answer_is_error(
    tmp_path,
    answer,
):
    """Check that an empty answer raises ChatUnavailableError."""
    _, feature = make(
        tmp_path=tmp_path,
        answer=lambda p: answer,
    )
    with pytest.raises(expected_exception=ChatUnavailableError):
        await feature.run(
            video_id=VID,
            language="русский",
        )
    key = CacheKey(
        video_id=VID,
        kind="summary",
        language="русский",
        mode="chat",
        prompt_version=PROMPT_VERSION,
    )
    assert await Cache(root=tmp_path / "cache").get(key=key) is None


async def test_cache_write_failure_keeps_text_and_warns(tmp_path):
    """Check that a failed cache write keeps the summary and adds a warning."""

    class FailingWriteCache(Cache):
        async def put(
            self,
            key,
            value,
        ) -> None:
            raise OSError("disk full /secret")

    warnings: list[str] = []
    feature = SummaryFeature(
        ask=FakeAskClient(
            info=INFO,
            answer=lambda p: "итог",
        ),
        cache=FailingWriteCache(root=tmp_path / "cache"),
        warn=warnings.append,
    )
    assert (
        await feature.run(
            video_id=VID,
            language="русский",
        )
        == "итог"
    )
    assert warnings == ["не удалось сохранить в кэш: OSError"]
