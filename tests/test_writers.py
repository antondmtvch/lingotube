import json

import pytest

from lingotube.errors import ValidationError
from lingotube.models import Cue, Transcript
from lingotube.writers import render

T = Transcript(
    video_id="vid",
    duration=100.0,
    language="ru",
    prompt_version="1",
    cues=(
        Cue(
            id=1,
            start=2.0,
            end=4.0,
            text="Помогите!",
        ),
        Cue(
            id=2,
            start=3723.0,
            end=3727.5,
            text="b",
        ),
    ),
)


def test_srt():
    assert render(
        transcript=T,
        fmt="srt",
    ) == (
        "1\n00:00:02,000 --> 00:00:04,000\nПомогите!\n\n"
        "2\n01:02:03,000 --> 01:02:07,500\nb\n"
    )


def test_vtt():
    assert render(
        transcript=T,
        fmt="vtt",
    ).startswith("WEBVTT\n\n00:00:02.000 --> 00:00:04.000\nПомогите!\n")


def test_json_roundtrip():
    assert (
        Transcript.from_dict(
            d=json.loads(
                s=render(
                    transcript=T,
                    fmt="json",
                )
            )
        )
        == T
    )


def test_offset_shifts_and_clamps_at_zero():
    assert "00:00:02,500 --> 00:00:04,500" in render(
        transcript=T,
        fmt="srt",
        offset=0.5,
    )
    assert "00:00:00,000 --> 00:00:01,000" in render(
        transcript=T,
        fmt="srt",
        offset=-3.0,
    )


def test_offset_applies_to_json():
    data = json.loads(
        s=render(
            transcript=T,
            fmt="json",
            offset=-3.0,
        )
    )
    assert (data["cues"][0]["start"], data["cues"][0]["end"]) == (0.0, 1.0)


def test_text_with_arrow_or_blank_line_is_sanitized():
    t = Transcript(
        video_id="v",
        duration=10,
        language="ru",
        prompt_version="1",
        cues=(
            Cue(
                id=1,
                start=0,
                end=1,
                text="a\n\nb --> c",
            ),
        ),
    )
    for fmt in ("srt", "vtt"):
        out = render(
            transcript=t,
            fmt=fmt,
        )
        assert "\n\nb" not in out and out.count("-->") == 1


def test_unknown_format_raises():
    with pytest.raises(expected_exception=ValidationError):
        render(
            transcript=T,
            fmt="xml",
        )  # type: ignore[arg-type]


def test_missing_end_raises():
    t = Transcript(
        video_id="v",
        duration=10,
        language=None,
        prompt_version="1",
        cues=(
            Cue(
                id=1,
                start=0,
                end=None,
                text="a",
            ),
        ),
    )
    with pytest.raises(expected_exception=ValidationError):
        render(
            transcript=t,
            fmt="srt",
        )


def _t(*texts):
    return Transcript(
        video_id="v",
        duration=10,
        language="ru",
        prompt_version="1",
        cues=tuple(
            Cue(
                id=i + 7,
                start=i,
                end=i + 1,
                text=x,
            )
            for i, x in enumerate(texts)
        ),
    )


@pytest.mark.parametrize(
    argnames="empty",
    argvalues=["  ", "\n\n", "\r"],
)
def test_empty_text_cues_are_skipped_and_srt_renumbered(empty):
    t = _t(
        "a",
        empty,
        "b",
    )
    srt = render(
        transcript=t,
        fmt="srt",
    )
    assert (
        srt
        == "1\n00:00:00,000 --> 00:00:01,000\na\n\n2\n00:00:02,000 --> 00:00:03,000\nb\n"
    )
    vtt = render(
        transcript=t,
        fmt="vtt",
    )
    assert (
        vtt
        == "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\na\n\n00:00:02.000 --> 00:00:03.000\nb\n"
    )
    assert (
        len(
            json.loads(
                s=render(
                    transcript=t,
                    fmt="json",
                )
            )["cues"]
        )
        == 3
    )


@pytest.mark.parametrize(
    argnames="arrow",
    argvalues=["--->", "---->", "-->"],
)
def test_arrow_variants_neutralized(arrow):
    for fmt in ("srt", "vtt"):
        assert (
            render(
                transcript=_t(f"a {arrow} b"),
                fmt=fmt,
            ).count("-->")
            == 1
        )


def test_lone_cr_is_a_line_break():
    assert "a\nb\n" in render(
        transcript=_t("a\rb"),
        fmt="srt",
    )
    assert "a\nb\n" in render(
        transcript=_t("a\r\nb"),
        fmt="srt",
    )


def test_cue_entirely_before_negative_offset_is_dropped():
    out = render(
        transcript=T,
        fmt="srt",
        offset=-4.0,
    )
    assert out == "1\n01:01:59,000 --> 01:02:03,500\nb\n"
    data = json.loads(
        s=render(
            transcript=T,
            fmt="json",
            offset=-4.0,
        )
    )
    assert [c["id"] for c in data["cues"]] == [2]


@pytest.mark.parametrize(
    argnames="offset",
    argvalues=[float("nan"), float("inf"), float("-inf")],
)
def test_non_finite_offset_is_rejected(offset):
    with pytest.raises(expected_exception=ValidationError) as ei:
        render(
            transcript=T,
            fmt="srt",
            offset=offset,
        )
    assert ei.value.exit_code == 7


def test_millisecond_rounding_carries_into_seconds():
    t = Transcript(
        video_id="vid",
        duration=100.0,
        language=None,
        prompt_version="1",
        cues=(
            Cue(
                id=1,
                start=0.9996,
                end=59.9996,
                text="a",
            ),
        ),
    )
    assert "00:00:01,000 --> 00:01:00,000" in render(
        transcript=t,
        fmt="srt",
    )


def test_hours_of_100_or_more_keep_all_digits():
    t = Transcript(
        video_id="vid",
        duration=400000.0,
        language=None,
        prompt_version="1",
        cues=(
            Cue(
                id=1,
                start=360000.0,
                end=360001.5,
                text="a",
            ),
        ),
    )
    assert "100:00:00.000 --> 100:00:01.500" in render(
        transcript=t,
        fmt="vtt",
    )
