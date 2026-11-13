from collections.abc import Sequence
from dataclasses import replace

import pytest

from lingotube.assemble import Completeness
from lingotube.cache import Cache
from lingotube.features.subtitles import SubtitlesFeature
from lingotube.features.transcript import TranscriptResult
from lingotube.models import Cue, Transcript, VideoInfo

VID = "vid123"
OK = Completeness(
    complete=True,
    last_end=10.0,
    gaps=(),
)


def make_transcript(language: str | None) -> Transcript:
    return Transcript(
        video_id=VID,
        duration=10.0,
        language=language,
        prompt_version="1",
        cues=(
            Cue(
                id=1,
                start=0.0,
                end=5.0,
                text="hello",
            ),
            Cue(
                id=2,
                start=5.0,
                end=10.0,
                text="bye",
            ),
        ),
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

    async def run(
        self,
        video_id,
        language=None,
        *,
        use_cache=True,
        on_opened=None,
    ):
        self.calls.append((video_id, language))
        if on_opened is not None:
            await on_opened(
                VideoInfo(
                    video_id=video_id,
                    duration=10.0,
                    title="t",
                    language=self.original_language,
                )
            )
        if self.result is not None:
            return self.result
        lang = language if language is not None else self.original_language
        return TranscriptResult(
            transcript=make_transcript(language=lang),
            completeness=OK,
            warnings=(),
        )


class FakeTranslator:
    def __init__(self, prepare_error: Exception | None = None):
        self.calls: list[str] = []
        self.prepared = 0
        self._prepare_error = prepare_error

    async def prepare(self) -> None:
        self.prepared += 1
        if self._prepare_error is not None:
            raise self._prepare_error

    async def translate(
        self,
        cues: Sequence[Cue],
        target_language: str,
    ) -> list[Cue]:
        self.calls.append(target_language)
        return [
            replace(
                c,
                text=f"[{target_language}] {c.text}",
            )
            for c in cues
        ]


async def test_chat_mode_requests_translated_transcript(tmp_path):
    tr = FakeTranscripts()
    res = await SubtitlesFeature(
        transcripts=tr,
        translator=None,
        cache=Cache(root=tmp_path),
    ).run(
        video_id=VID,
        language="ru",
    )
    assert tr.calls == [(VID, "ru")]
    assert res.transcript.language == "ru"


async def test_own_model_mode_requests_original_then_translates(tmp_path):
    tr, tl = FakeTranscripts(), FakeTranslator()
    res = await SubtitlesFeature(
        transcripts=tr,
        translator=tl,
        cache=Cache(root=tmp_path),
    ).run(
        video_id=VID,
        language="ru",
    )
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
    tr, tl = FakeTranscripts(original_language="ru-RU"), FakeTranslator()
    res = await SubtitlesFeature(
        transcripts=tr,
        translator=tl,
        cache=Cache(root=tmp_path),
    ).run(
        video_id=VID,
        language="ru",
    )
    assert tl.calls == []
    assert res.transcript.language == "ru"
    assert res.transcript.cues[0].text == "hello"


async def test_second_language_reuses_cached_original(tmp_path):
    # the original is cached by TranscriptFeature itself; both languages ask only for it
    tr, tl = FakeTranscripts(), FakeTranslator()
    feature = SubtitlesFeature(
        transcripts=tr,
        translator=tl,
        cache=Cache(root=tmp_path),
    )
    await feature.run(
        video_id=VID,
        language="ru",
    )
    await feature.run(
        video_id=VID,
        language="es",
    )
    assert tr.calls == [(VID, None), (VID, None)]
    assert tl.calls == ["ru", "es"]


async def test_translation_cached_per_language_and_mode(tmp_path):
    tr, tl = FakeTranscripts(), FakeTranslator()
    feature = SubtitlesFeature(
        transcripts=tr,
        translator=tl,
        cache=Cache(root=tmp_path),
    )
    first = await feature.run(
        video_id=VID,
        language="ru",
    )
    again = await feature.run(
        video_id=VID,
        language="ru",
    )
    assert tl.calls == ["ru"] and len(tr.calls) == 1
    assert again.transcript == first.transcript
    await feature.run(
        video_id=VID,
        language="es",
    )
    assert tl.calls == ["ru", "es"]
    await feature.run(
        video_id=VID,
        language="ru",
        use_cache=False,
    )
    assert tl.calls == ["ru", "es", "ru"]


async def test_incomplete_original_propagates_completeness(tmp_path):
    incomplete = Completeness(
        complete=False,
        last_end=5.0,
        gaps=(),
    )
    tr = FakeTranscripts(
        result=TranscriptResult(
            transcript=make_transcript(language="en"),
            completeness=incomplete,
            warnings=("обрыв",),
        )
    )
    tl = FakeTranslator()
    feature = SubtitlesFeature(
        transcripts=tr,
        translator=tl,
        cache=Cache(root=tmp_path),
    )
    res = await feature.run(
        video_id=VID,
        language="ru",
    )
    assert not res.completeness.complete
    assert res.warnings == ("обрыв",)
    await feature.run(
        video_id=VID,
        language="ru",
    )
    assert tl.calls == [
        "ru",
        "ru",
    ]  # an incomplete translation is never served as ready


async def test_unknown_original_language_is_translated(tmp_path):
    tr, tl = FakeTranscripts(original_language=None), FakeTranslator()
    res = await SubtitlesFeature(
        transcripts=tr,
        translator=tl,
        cache=Cache(root=tmp_path),
    ).run(
        video_id=VID,
        language="ru",
    )
    assert tl.calls == ["ru"]
    assert res.transcript.cues[0].text == "[ru] hello"


async def test_cache_write_failure_keeps_result_and_warns(tmp_path):
    class FailingWriteCache(Cache):
        async def put(
            self,
            key,
            value,
        ) -> None:
            raise PermissionError("denied")

    feature = SubtitlesFeature(
        transcripts=FakeTranscripts(),
        translator=FakeTranslator(),
        cache=FailingWriteCache(root=tmp_path / "cache"),
    )
    result = await feature.run(
        video_id=VID,
        language="ru",
    )
    assert "не удалось сохранить в кэш: PermissionError" in result.warnings


async def test_same_cache_warning_from_original_and_subtitles_is_reported_once(
    tmp_path,
):
    class FailingWriteCache(Cache):
        async def put(
            self,
            key,
            value,
        ) -> None:
            raise PermissionError("denied")

    warning = "не удалось сохранить в кэш: PermissionError"
    other = "другое предупреждение"
    feature = SubtitlesFeature(
        transcripts=FakeTranscripts(
            result=TranscriptResult(
                transcript=make_transcript(language="en"),
                completeness=OK,
                warnings=(other, warning),
            )
        ),
        translator=FakeTranslator(),
        cache=FailingWriteCache(root=tmp_path / "cache"),
    )
    result = await feature.run(
        video_id=VID,
        language="ru",
    )
    assert result.warnings == (other, warning)


async def test_missing_key_fails_after_open_before_chat_requests(tmp_path):
    tr = FakeTranscripts(original_language="en")
    tl = FakeTranslator(prepare_error=RuntimeError("no key"))
    with pytest.raises(expected_exception=RuntimeError):
        await SubtitlesFeature(
            transcripts=tr,
            translator=tl,
            cache=Cache(root=tmp_path),
        ).run(
            video_id=VID,
            language="ru",
        )
    assert tl.calls == [] and tl.prepared == 1


async def test_own_language_needs_no_translator_key(tmp_path):
    tr = FakeTranscripts(original_language="en")
    tl = FakeTranslator(prepare_error=RuntimeError("no key"))
    res = await SubtitlesFeature(
        transcripts=tr,
        translator=tl,
        cache=Cache(root=tmp_path),
    ).run(
        video_id=VID,
        language="en-US",
    )
    assert tl.prepared == 0 and tl.calls == []
    assert res.transcript.language == "en-US"
