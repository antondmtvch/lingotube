import json

import pytest

from lingotube.errors import ValidationError
from lingotube.models import Cue, Transcript
from lingotube.writers import render

T = Transcript(
    "vid",
    100.0,
    "ru",
    "1",
    (Cue(1, 2.0, 4.0, "Помогите!"), Cue(2, 3723.0, 3727.5, "b")),
)


def test_srt():
    assert render(T, "srt") == (
        "1\n00:00:02,000 --> 00:00:04,000\nПомогите!\n\n"
        "2\n01:02:03,000 --> 01:02:07,500\nb\n"
    )


def test_vtt():
    assert render(T, "vtt").startswith(
        "WEBVTT\n\n00:00:02.000 --> 00:00:04.000\nПомогите!\n"
    )


def test_json_roundtrip():
    assert Transcript.from_dict(json.loads(render(T, "json"))) == T


def test_offset_shifts_and_clamps_at_zero():
    assert "00:00:02,500 --> 00:00:04,500" in render(T, "srt", offset=0.5)
    assert "00:00:00,000 --> 00:00:01,000" in render(T, "srt", offset=-3.0)


def test_offset_applies_to_json():
    data = json.loads(render(T, "json", offset=-3.0))
    assert (data["cues"][0]["start"], data["cues"][0]["end"]) == (0.0, 1.0)


def test_text_with_arrow_or_blank_line_is_sanitized():
    t = Transcript("v", 10, "ru", "1", (Cue(1, 0, 1, "a\n\nb --> c"),))
    for fmt in ("srt", "vtt"):
        out = render(t, fmt)
        assert "\n\nb" not in out and out.count("-->") == 1


def test_unknown_format_raises():
    with pytest.raises(ValidationError):
        render(T, "xml")  # type: ignore[arg-type]


def test_missing_end_raises():
    t = Transcript("v", 10, None, "1", (Cue(1, 0, None, "a"),))
    with pytest.raises(ValidationError):
        render(t, "srt")


def _t(*texts):
    return Transcript(
        "v", 10, "ru", "1", tuple(Cue(i + 7, i, i + 1, x) for i, x in enumerate(texts))
    )


@pytest.mark.parametrize("empty", ["  ", "\n\n", "\r"])
def test_empty_text_cues_are_skipped_and_srt_renumbered(empty):
    t = _t("a", empty, "b")
    srt = render(t, "srt")
    assert (
        srt
        == "1\n00:00:00,000 --> 00:00:01,000\na\n\n2\n00:00:02,000 --> 00:00:03,000\nb\n"
    )
    vtt = render(t, "vtt")
    assert (
        vtt
        == "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\na\n\n00:00:02.000 --> 00:00:03.000\nb\n"
    )
    assert len(json.loads(render(t, "json"))["cues"]) == 3


@pytest.mark.parametrize("arrow", ["--->", "---->", "-->"])
def test_arrow_variants_neutralized(arrow):
    for fmt in ("srt", "vtt"):
        assert render(_t(f"a {arrow} b"), fmt).count("-->") == 1


def test_lone_cr_is_a_line_break():
    assert "a\nb\n" in render(_t("a\rb"), "srt")
    assert "a\nb\n" in render(_t("a\r\nb"), "srt")
