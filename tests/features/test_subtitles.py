from collections.abc import Sequence
from dataclasses import replace

from lingotube.assemble import Completeness
from lingotube.cache import Cache
from lingotube.features.subtitles import SubtitlesFeature
from lingotube.features.transcript import TranscriptResult
from lingotube.models import Cue, Transcript

VID = "vid123"
OK = Completeness(True, 10.0, ())


def make_transcript(language: str | None) -> Transcript:
    return Transcript(
        VID, 10.0, language, "1", (Cue(1, 0.0, 5.0, "hello"), Cue(2, 5.0, 10.0, "bye"))
    )


class FakeTranscripts:
    def __init__(
        self,
        original_language: str | None = "en",
        result: TranscriptResult | None = None,
    ):
        self.calls: list[tuple[str, str | None]] = []
        self.original_language = original_language
        self.result = result

    async def run(self, video_id, language=None, *, use_cache=True):
        self.calls.append((video_id, language))
        if self.result is not None:
            return self.result
        lang = language if language is not None else self.original_language
        return TranscriptResult(make_transcript(lang), OK, ())


class FakeTranslator:
    def __init__(self):
        self.calls: list[str] = []

    async def translate(self, cues: Sequence[Cue], target_language: str) -> list[Cue]:
        self.calls.append(target_language)
        return [replace(c, text=f"[{target_language}] {c.text}") for c in cues]


async def test_chat_mode_requests_translated_transcript(tmp_path):
    tr = FakeTranscripts()
    res = await SubtitlesFeature(tr, None, Cache(tmp_path)).run(VID, "ru")
    assert tr.calls == [(VID, "ru")]
    assert res.transcript.language == "ru"


async def test_own_model_mode_requests_original_then_translates(tmp_path):
    tr, tl = FakeTranscripts(), FakeTranslator()
    res = await SubtitlesFeature(tr, tl, Cache(tmp_path)).run(VID, "ru")
    assert tr.calls == [(VID, None)]
    assert tl.calls == ["ru"]
    assert res.transcript.language == "ru"
    assert [c.text for c in res.transcript.cues] == ["[ru] hello", "[ru] bye"]
    assert [(c.id, c.start, c.end) for c in res.transcript.cues] == [
        (1, 0.0, 5.0),
        (2, 5.0, 10.0),
    ]
    assert res.completeness.complete


async def test_same_language_skips_translation(tmp_path):
    tr, tl = FakeTranscripts("ru-RU"), FakeTranslator()
    res = await SubtitlesFeature(tr, tl, Cache(tmp_path)).run(VID, "ru")
    assert tl.calls == []
    assert res.transcript.language == "ru"
    assert res.transcript.cues[0].text == "hello"


async def test_second_language_reuses_cached_original(tmp_path):
    # the original is cached by TranscriptFeature itself; both languages ask only for it
    tr, tl = FakeTranscripts(), FakeTranslator()
    feature = SubtitlesFeature(tr, tl, Cache(tmp_path))
    await feature.run(VID, "ru")
    await feature.run(VID, "es")
    assert tr.calls == [(VID, None), (VID, None)]
    assert tl.calls == ["ru", "es"]


async def test_translation_cached_per_language_and_mode(tmp_path):
    tr, tl = FakeTranscripts(), FakeTranslator()
    feature = SubtitlesFeature(tr, tl, Cache(tmp_path))
    first = await feature.run(VID, "ru")
    again = await feature.run(VID, "ru")
    assert tl.calls == ["ru"] and len(tr.calls) == 1
    assert again.transcript == first.transcript
    await feature.run(VID, "es")
    assert tl.calls == ["ru", "es"]
    await feature.run(VID, "ru", use_cache=False)
    assert tl.calls == ["ru", "es", "ru"]


async def test_incomplete_original_propagates_completeness(tmp_path):
    incomplete = Completeness(False, 5.0, ())
    tr = FakeTranscripts(
        result=TranscriptResult(make_transcript("en"), incomplete, ("обрыв",))
    )
    tl = FakeTranslator()
    feature = SubtitlesFeature(tr, tl, Cache(tmp_path))
    res = await feature.run(VID, "ru")
    assert not res.completeness.complete
    assert res.warnings == ("обрыв",)
    await feature.run(VID, "ru")
    assert tl.calls == [
        "ru",
        "ru",
    ]  # an incomplete translation is never served as ready


async def test_unknown_original_language_is_translated(tmp_path):
    tr, tl = FakeTranscripts(original_language=None), FakeTranslator()
    res = await SubtitlesFeature(tr, tl, Cache(tmp_path)).run(VID, "ru")
    assert tl.calls == ["ru"]
    assert res.transcript.cues[0].text == "[ru] hello"
