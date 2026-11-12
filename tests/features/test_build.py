import pytest

from lingotube.cache import Cache, CacheKey
from lingotube.errors import ValidationError
from lingotube.features.build import BuildFeature, validate_translation
from lingotube.models import Cue, Transcript
from lingotube.prompts import PROMPT_VERSION

VID = "vid123"


def original(n=8) -> Transcript:
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
    d = (t or original()).to_dict()
    for c in d["cues"]:
        c["text"] = f"перевод {c['id']}"
    d.update(changes)
    return d


def test_validate_ok_keeps_original_times():
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
    with pytest.raises(expected_exception=ValidationError):
        validate_translation(
            original=original(),
            translated=translated(video_id="other"),
            language="ru",
        )


def test_validate_malformed_propagates():
    with pytest.raises(expected_exception=ValidationError):
        validate_translation(
            original=original(),
            translated={"cues": 1},
            language="ru",
        )


async def test_build_without_cached_original_hints_transcript(tmp_path):
    feature = BuildFeature(cache=Cache(root=tmp_path / "cache"))
    with pytest.raises(expected_exception=ValidationError) as e:
        await feature.run(
            video_id=VID,
            language="ru",
            translated=translated(),
        )
    assert "lingotube transcript" in (e.value.hint or "")


async def test_build_stores_translation_in_cache(tmp_path):
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
    assert result.language == "ru"
    stored = await cache.get(
        key=CacheKey(
            video_id=VID,
            kind="subtitles",
            language="ru",
            mode="agent",
            prompt_version=PROMPT_VERSION,
        )
    )
    assert stored == result.to_dict()


def test_validate_many_missing_ids_is_capped():
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
    assert result.language == "ru"


async def test_build_malformed_cached_original_is_missing(tmp_path):
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
