"""Tests of the build feature: checking an agent's translation against the original."""

import pytest

from lingotube.cache import Cache, CacheKey
from lingotube.errors import ValidationError
from lingotube.features.build import BuildFeature, validate_translation
from lingotube.models import Cue, Transcript
from lingotube.prompts import PROMPT_VERSION

VID = "vid123"


def original(n=8) -> Transcript:
    """Build an original transcript with eight cues.

    Args:
        n: Number of cues.

    Returns:
        The transcript.
    """
    cues = tuple(
        Cue(
            id=i,
            start=float(i * 10),
            end=float(i * 10 + 9),
            text=f"orig {i}",
        )
        for i in range(
            1,
            n + 1,
        )
    )
    return Transcript(
        video_id=VID,
        duration=100.0,
        language="en",
        prompt_version=PROMPT_VERSION,
        cues=cues,
    )


def translated(
    t: Transcript | None = None,
    **changes,
) -> dict:
    """Build a translation in the transcript JSON format, based on the original.

    Args:
        t: Transcript to translate. Defaults to the test original.
        **changes: Fields of the JSON to override.

    Returns:
        The translation as a dict.
    """
    d = (t or original()).to_dict()
    for c in d["cues"]:
        c["text"] = f"перевод {c['id']}"
    d.update(changes)
    return d


def test_validate_ok_keeps_original_times():
    """Check that a valid translation keeps the times of the original."""
    d = translated()
    d["cues"][0]["start"] = 555.0
    d["cues"][0]["end"] = 999.0
    result = validate_translation(
        original=original(),
        translated=d,
        language="ru",
    )
    assert result.language == "ru"
    assert result.cues[0] == Cue(
        id=1,
        start=10.0,
        end=19.0,
        text="перевод 1",
    )
    assert result.duration == 100.0
    assert result.video_id == VID


def test_validate_missing_ids_lists_them():
    """Check that missing cue ids are listed in the error."""
    d = translated()
    d["cues"] = [c for c in d["cues"] if c["id"] not in (3, 7)]
    with pytest.raises(expected_exception=ValidationError) as e:
        validate_translation(
            original=original(),
            translated=d,
            language="ru",
        )
    assert "отсутствуют id: 3, 7" in e.value.message


def test_validate_extra_or_duplicate_ids():
    """Check that extra and duplicate cue ids are reported."""
    d = translated()
    d["cues"].append({"id": 42, "start": 1, "end": 2, "text": "x"})
    d["cues"].append({"id": 2, "start": 1, "end": 2, "text": "x"})
    with pytest.raises(expected_exception=ValidationError) as e:
        validate_translation(
            original=original(),
            translated=d,
            language="ru",
        )
    assert "лишние id: 42" in e.value.message
    assert "повторяются id: 2" in e.value.message


def test_validate_empty_text():
    """Check that a cue with empty text is reported."""
    d = translated()
    d["cues"][4]["text"] = "  "
    with pytest.raises(expected_exception=ValidationError) as e:
        validate_translation(
            original=original(),
            translated=d,
            language="ru",
        )
    assert "пустой текст у id: 5" in e.value.message


def test_validate_collects_all_problems_sorted():
    """Check that all problems are reported together, in sorted order."""
    d = translated()
    d["cues"] = [c for c in d["cues"] if c["id"] not in (7, 3)]
    d["cues"][0]["text"] = ""
    with pytest.raises(expected_exception=ValidationError) as e:
        validate_translation(
            original=original(),
            translated=d,
            language="ru",
        )
    msg = e.value.message
    assert "отсутствуют id: 3, 7" in msg
    assert "пустой текст у id: 1" in msg


def test_validate_wrong_video_id():
    """Check that a translation of another video is rejected."""
    with pytest.raises(expected_exception=ValidationError):
        validate_translation(
            original=original(),
            translated=translated(video_id="other"),
            language="ru",
        )


def test_validate_malformed_propagates():
    """Check that a malformed translation raises ValidationError."""
    with pytest.raises(expected_exception=ValidationError):
        validate_translation(
            original=original(),
            translated={"cues": 1},
            language="ru",
        )


async def test_build_without_cached_original_hints_transcript(tmp_path):
    """Check that building without a cached original suggests running the transcript command."""
    feature = BuildFeature(cache=Cache(root=tmp_path / "cache"))
    with pytest.raises(expected_exception=ValidationError) as e:
        await feature.run(
            video_id=VID,
            language="ru",
            translated=translated(),
        )
    assert "lingotube transcript" in (e.value.hint or "")


async def test_build_stores_translation_in_cache(tmp_path):
    """Check that the built translation is stored in the cache."""
    cache = Cache(root=tmp_path / "cache")
    orig = original()
    await cache.put(
        key=CacheKey(
            video_id=VID,
            kind="transcript",
            language="orig",
            mode="chat",
            prompt_version=PROMPT_VERSION,
        ),
        value={"complete": True, "warnings": [], "transcript": orig.to_dict()},
    )
    result = await BuildFeature(cache=cache).run(
        video_id=VID,
        language="ru",
        translated=translated(),
    )
    assert result.transcript.language == "ru"
    assert result.warnings == ()
    stored = await cache.get(
        key=CacheKey(
            video_id=VID,
            kind="subtitles",
            language="ru",
            mode="agent",
            prompt_version=PROMPT_VERSION,
        )
    )
    assert stored == result.transcript.to_dict()


def test_validate_many_missing_ids_is_capped():
    """Check that a long list of missing ids is cut short in the error."""
    big = original(n=2000)
    d = translated(t=big)
    d["cues"] = []
    with pytest.raises(expected_exception=ValidationError) as e:
        validate_translation(
            original=big,
            translated=d,
            language="ru",
        )
    assert len(e.value.message) < 300
    assert "… и ещё 1980" in e.value.message


async def test_build_accepts_incomplete_cached_original(tmp_path):
    """Check that an incomplete cached original is accepted for building."""
    cache = Cache(root=tmp_path / "cache")
    await cache.put(
        key=CacheKey(
            video_id=VID,
            kind="transcript",
            language="orig",
            mode="chat",
            prompt_version=PROMPT_VERSION,
        ),
        value={"complete": False, "warnings": [], "transcript": original().to_dict()},
    )
    result = await BuildFeature(cache=cache).run(
        video_id=VID,
        language="ru",
        translated=translated(),
    )
    assert result.transcript.language == "ru"


async def test_build_malformed_cached_original_is_missing(tmp_path):
    """Check that a malformed cached original counts as missing."""
    cache = Cache(root=tmp_path / "cache")
    await cache.put(
        key=CacheKey(
            video_id=VID,
            kind="transcript",
            language="orig",
            mode="chat",
            prompt_version=PROMPT_VERSION,
        ),
        value={"complete": True, "transcript": {"cues": 1}},
    )
    with pytest.raises(expected_exception=ValidationError) as e:
        await BuildFeature(cache=cache).run(
            video_id=VID,
            language="ru",
            translated=translated(),
        )
    assert "lingotube transcript" in (e.value.hint or "")


async def test_build_cached_payload_without_transcript_key_is_missing(tmp_path):
    """Check that a cached payload without the transcript key counts as missing."""
    cache = Cache(root=tmp_path / "cache")
    await cache.put(
        key=CacheKey(
            video_id=VID,
            kind="transcript",
            language="orig",
            mode="chat",
            prompt_version=PROMPT_VERSION,
        ),
        value={"complete": True},
    )
    with pytest.raises(expected_exception=ValidationError) as e:
        await BuildFeature(cache=cache).run(
            video_id=VID,
            language="ru",
            translated=translated(),
        )
    assert "lingotube transcript" in (e.value.hint or "")


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


async def test_build_cache_write_failure_keeps_result_and_warns(tmp_path):
    """Check that a failed cache write keeps the result and adds a warning."""
    good = Cache(root=tmp_path / "cache")
    await good.put(
        key=CacheKey(
            video_id=VID,
            kind="transcript",
            language="orig",
            mode="chat",
            prompt_version=PROMPT_VERSION,
        ),
        value={"complete": True, "warnings": [], "transcript": original().to_dict()},
    )
    result = await BuildFeature(cache=FailingWriteCache(root=tmp_path / "cache")).run(
        video_id=VID,
        language="ru",
        translated=translated(),
    )
    assert result.transcript.language == "ru"
    assert result.warnings == ("не удалось сохранить в кэш: PermissionError",)
    assert all("secret" not in w for w in result.warnings)
