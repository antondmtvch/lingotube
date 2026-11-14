"""Tests of the assembly of parsed lines: ranges, joining, end times and completeness."""

from lingotube.assemble import (
    check_completeness,
    fix_ends,
    is_truncated,
    merge,
    plan_ranges,
)
from lingotube.models import Cue
from lingotube.parsing import ParsedLine


def test_plan_ranges():
    """Check that the video is split into ranges of the given length."""
    assert plan_ranges(
        duration=1500,
        chunk_seconds=600,
    ) == [(0, 600), (600, 1200), (1200, 1500)]
    assert plan_ranges(
        duration=300,
        chunk_seconds=600,
    ) == [(0, 300)]


def test_is_truncated():
    """Check that an answer that ends early counts as truncated."""
    lines = [
        ParsedLine(
            start=10,
            end=12,
            text="a",
        ),
        ParsedLine(
            start=400,
            end=402,
            text="b",
        ),
    ]
    assert (
        is_truncated(
            lines=lines,
            range_end=600,
        )
        is True
    )
    assert (
        is_truncated(
            lines=lines,
            range_end=450,
        )
        is False
    )
    assert (
        is_truncated(
            lines=[],
            range_end=600,
        )
        is True
    )


def test_is_truncated_start_only_lines():
    """Check that the truncation check works on lines that have only a start time."""
    lines = [
        ParsedLine(
            start=10,
            end=None,
            text="a",
        ),
        ParsedLine(
            start=400,
            end=None,
            text="b",
        ),
    ]
    assert (
        is_truncated(
            lines=lines,
            range_end=600,
        )
        is True
    )
    assert (
        is_truncated(
            lines=lines,
            range_end=450,
        )
        is False
    )


def test_merge_dedupes_boundary_and_numbers():
    """Check that duplicates at a range boundary are removed and the cues are numbered."""
    a = [
        ParsedLine(
            start=590,
            end=595,
            text="x",
        ),
        ParsedLine(
            start=598,
            end=601,
            text="стык",
        ),
    ]
    b = [
        ParsedLine(
            start=598,
            end=601,
            text="стык",
        ),
        ParsedLine(
            start=605,
            end=608,
            text="y",
        ),
    ]
    cues = merge(chunks=[a, b])
    assert [c.text for c in cues] == ["x", "стык", "y"]
    assert [c.id for c in cues] == [1, 2, 3]


def test_merge_carries_missing_end_and_dedupes_within_2s():
    """Check that a missing end is carried over and duplicates within two seconds are removed."""
    a = [
        ParsedLine(
            start=10,
            end=None,
            text="стык ",
        )
    ]
    b = [
        ParsedLine(
            start=11.5,
            end=None,
            text="стык",
        ),
        ParsedLine(
            start=20,
            end=None,
            text="z",
        ),
    ]
    cues = merge(chunks=[b, a])
    assert [(c.start, c.end, c.text) for c in cues] == [
        (10, None, "стык"),
        (20, None, "z"),
    ]


def test_fix_ends_keeps_valid_chat_end():
    """Check that a valid end time from the chat is kept."""
    assert (
        fix_ends(
            cues=[
                Cue(
                    id=1,
                    start=2,
                    end=4,
                    text="a",
                ),
                Cue(
                    id=2,
                    start=4,
                    end=7,
                    text="b",
                ),
            ],
            duration=100,
        )[0].end
        == 4
    )


def test_fix_ends_repairs_invalid():
    """Check that an invalid end time is repaired."""
    out = fix_ends(
        cues=[
            Cue(
                id=1,
                start=2,
                end=2,
                text="abc",
            ),
            Cue(
                id=2,
                start=3,
                end=50,
                text="b",
            ),
            Cue(
                id=3,
                start=5,
                end=500,
                text="c",
            ),
        ],
        duration=100,
    )
    assert out[0].end == 3
    assert out[1].end == 5
    assert out[2].end <= 100


def test_fix_ends_missing_end_uses_reading_time():
    """Check that a missing end time is estimated from the reading time."""
    out = fix_ends(
        cues=[
            Cue(
                id=1,
                start=0,
                end=None,
                text="x" * 30,
            ),
            Cue(
                id=2,
                start=60,
                end=None,
                text="y",
            ),
        ],
        duration=100,
    )
    assert out[0].end == 2.0
    assert out[1].end == 61.5
    assert (
        fix_ends(
            cues=[
                Cue(
                    id=1,
                    start=0,
                    end=None,
                    text="x" * 300,
                )
            ],
            duration=100,
        )[0].end
        == 7.0
    )


def test_completeness():
    """Check the completeness check on a transcript that reaches the end."""
    full = [
        Cue(
            id=1,
            start=0,
            end=5,
            text="a",
        ),
        Cue(
            id=2,
            start=580,
            end=590,
            text="b",
        ),
    ]
    r = check_completeness(
        cues=full,
        duration=600,
    )
    assert r.complete and r.gaps == ((5, 580),)
    assert (
        check_completeness(
            cues=[
                Cue(
                    id=1,
                    start=0,
                    end=5,
                    text="a",
                )
            ],
            duration=600,
        ).complete
        is False
    )
    assert (
        check_completeness(
            cues=[],
            duration=600,
        ).complete
        is False
    )


def test_merge_joins_same_start_lines():
    """Check that lines with the same start time are joined."""
    cues = merge(
        chunks=[
            [
                ParsedLine(
                    start=10,
                    end=None,
                    text="а",
                ),
                ParsedLine(
                    start=10,
                    end=None,
                    text="б",
                ),
                ParsedLine(
                    start=20,
                    end=None,
                    text="в",
                ),
            ]
        ]
    )
    assert [(c.id, c.start, c.end, c.text) for c in cues] == [
        (1, 10, None, "а б"),
        (2, 20, None, "в"),
    ]


def test_merge_same_start_keeps_max_end():
    """Check that joined lines with the same start keep the latest end."""
    cues = merge(
        chunks=[
            [
                ParsedLine(
                    start=10,
                    end=12,
                    text="а",
                ),
                ParsedLine(
                    start=10,
                    end=None,
                    text="б",
                ),
                ParsedLine(
                    start=10,
                    end=15,
                    text="в",
                ),
            ]
        ]
    )
    assert [(c.end, c.text) for c in cues] == [(15, "а б в")]


def test_fix_ends_drops_cues_past_duration_and_renumbers():
    """Check that cues past the end of the video are dropped and the rest renumbered."""
    out = fix_ends(
        cues=[
            Cue(
                id=1,
                start=5,
                end=None,
                text="a",
            ),
            Cue(
                id=2,
                start=100,
                end=None,
                text="b",
            ),
            Cue(
                id=3,
                start=120,
                end=130,
                text="c",
            ),
        ],
        duration=100,
    )
    assert [c.id for c in out] == [1]
    assert all(c.end > c.start for c in out)


def test_fix_ends_every_end_after_start():
    """Check that every fixed end time is after its start time."""
    cues = merge(
        chunks=[
            [
                ParsedLine(
                    start=10,
                    end=None,
                    text="а",
                ),
                ParsedLine(
                    start=10,
                    end=None,
                    text="б",
                ),
                ParsedLine(
                    start=99.9,
                    end=None,
                    text="в",
                ),
            ]
        ]
    )
    out = fix_ends(
        cues=cues,
        duration=100,
    )
    assert all(c.end > c.start for c in out)


def test_completeness_leading_gap():
    """Check that a long gap at the start counts as a gap."""
    r = check_completeness(
        cues=[
            Cue(
                id=1,
                start=180,
                end=590,
                text="a",
            )
        ],
        duration=600,
    )
    assert r.complete and r.gaps == ((0, 180),)


def test_merge_seam_dedupe_applies_before_join():
    """Check that duplicates at the seams are removed before lines are joined."""
    a = [
        ParsedLine(
            start=10,
            end=12,
            text="p",
        ),
        ParsedLine(
            start=10,
            end=12,
            text="q",
        ),
    ]
    b = [
        ParsedLine(
            start=11,
            end=13,
            text="p",
        )
    ]
    assert [(c.start, c.text) for c in merge(chunks=[a, b])] == [(10, "p q")]


def test_fix_ends_same_start_unmerged_never_degenerate():
    """Check that cues with the same start and no merge never get an empty duration."""
    out = fix_ends(
        cues=[
            Cue(
                id=1,
                start=10,
                end=None,
                text="a",
            ),
            Cue(
                id=2,
                start=10,
                end=None,
                text="b",
            ),
            Cue(
                id=3,
                start=20,
                end=None,
                text="c",
            ),
        ],
        duration=100,
    )
    assert all(c.end > c.start for c in out)
    assert out[0].end == 11.5 and out[1].end == 11.5


def test_plan_ranges_merges_sub_second_tail_into_previous():
    """Check that a tail shorter than a second is merged into the previous range."""
    assert plan_ranges(
        duration=600.5,
        chunk_seconds=300,
    ) == [(0, 300), (300, 600.5)]
    assert plan_ranges(
        duration=601.0,
        chunk_seconds=300,
    ) == [(0, 300), (300, 600), (600, 601.0)]


def test_is_truncated_does_not_assume_sorted_lines():
    """Check that the truncation check does not need sorted lines."""
    lines = [
        ParsedLine(
            start=400,
            end=402,
            text="b",
        ),
        ParsedLine(
            start=10,
            end=12,
            text="a",
        ),
    ]
    assert (
        is_truncated(
            lines=lines,
            range_end=450,
        )
        is False
    )


def test_completeness_does_not_assume_sorted_cues():
    """Check that the completeness check does not need sorted cues."""
    cues = [
        Cue(
            id=2,
            start=50.0,
            end=60.0,
            text="b",
        ),
        Cue(
            id=1,
            start=0.0,
            end=10.0,
            text="a",
        ),
    ]
    result = check_completeness(
        cues=cues,
        duration=120.0,
    )
    assert result.complete is True
    assert result.last_end == 60.0
    assert result.gaps == ()
