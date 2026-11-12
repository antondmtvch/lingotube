import pytest

from lingotube.cache import Cache, CacheKey
from lingotube.errors import ValidationError
from lingotube.features.build import BuildFeature, validate_translation
from lingotube.models import Cue, Transcript
from lingotube.prompts import PROMPT_VERSION

VID = "vid123"


def original(n=8) -> Transcript:
    cues = tuple(Cue(i, float(i * 10), float(i * 10 + 9), f"orig {i}") for i in range(1, n + 1))
    return Transcript(VID, 100.0, "en", PROMPT_VERSION, cues)


def translated(t: Transcript | None = None, **changes) -> dict:
    d = (t or original()).to_dict()
    for c in d["cues"]:
        c["text"] = f"перевод {c['id']}"
    d.update(changes)
    return d


def test_validate_ok_keeps_original_times():
    d = translated()
    d["cues"][0]["start"] = 555.0
    d["cues"][0]["end"] = 999.0
    result = validate_translation(original(), d, "ru")
    assert result.language == "ru"
    assert result.cues[0] == Cue(1, 10.0, 19.0, "перевод 1")
    assert result.duration == 100.0
    assert result.video_id == VID


def test_validate_missing_ids_lists_them():
    d = translated()
    d["cues"] = [c for c in d["cues"] if c["id"] not in (3, 7)]
    with pytest.raises(ValidationError) as e:
        validate_translation(original(), d, "ru")
    assert "3" in e.value.message and "7" in e.value.message


def test_validate_extra_or_duplicate_ids():
    d = translated()
    d["cues"].append({"id": 42, "start": 1, "end": 2, "text": "x"})
    d["cues"].append({"id": 2, "start": 1, "end": 2, "text": "x"})
    with pytest.raises(ValidationError) as e:
        validate_translation(original(), d, "ru")
    assert "42" in e.value.message and "2" in e.value.message


def test_validate_empty_text():
    d = translated()
    d["cues"][4]["text"] = "  "
    with pytest.raises(ValidationError) as e:
        validate_translation(original(), d, "ru")
    assert "5" in e.value.message


def test_validate_collects_all_problems_sorted():
    d = translated()
    d["cues"] = [c for c in d["cues"] if c["id"] not in (7, 3)]
    d["cues"][0]["text"] = ""
    with pytest.raises(ValidationError) as e:
        validate_translation(original(), d, "ru")
    msg = e.value.message
    assert "3, 7" in msg and "1" in msg


def test_validate_wrong_video_id():
    with pytest.raises(ValidationError):
        validate_translation(original(), translated(video_id="other"), "ru")


def test_validate_malformed_propagates():
    with pytest.raises(ValidationError):
        validate_translation(original(), {"cues": 1}, "ru")


async def test_build_without_cached_original_hints_transcript(tmp_path):
    feature = BuildFeature(Cache(tmp_path / "cache"))
    with pytest.raises(ValidationError) as e:
        await feature.run(VID, "ru", translated())
    assert "lingotube transcript" in (e.value.hint or "")


async def test_build_stores_translation_in_cache(tmp_path):
    cache = Cache(tmp_path / "cache")
    orig = original()
    await cache.put(
        CacheKey(VID, "transcript", "orig", "chat", PROMPT_VERSION),
        {"complete": True, "warnings": [], "transcript": orig.to_dict()},
    )
    result = await BuildFeature(cache).run(VID, "ru", translated())
    assert result.language == "ru"
    stored = await cache.get(CacheKey(VID, "subtitles", "ru", "agent", PROMPT_VERSION))
    assert stored == result.to_dict()
