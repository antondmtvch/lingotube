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
    assert plan_ranges(1500, 600) == [(0, 600), (600, 1200), (1200, 1500)]
    assert plan_ranges(300, 600) == [(0, 300)]


def test_is_truncated():
    lines = [ParsedLine(10, 12, "a"), ParsedLine(400, 402, "b")]
    assert is_truncated(lines, range_end=600) is True
    assert is_truncated(lines, range_end=450) is False
    assert is_truncated([], range_end=600) is True


def test_is_truncated_start_only_lines():
    lines = [ParsedLine(10, None, "a"), ParsedLine(400, None, "b")]
    assert is_truncated(lines, range_end=600) is True
    assert is_truncated(lines, range_end=450) is False


def test_merge_dedupes_boundary_and_numbers():
    a = [ParsedLine(590, 595, "x"), ParsedLine(598, 601, "стык")]
    b = [ParsedLine(598, 601, "стык"), ParsedLine(605, 608, "y")]
    cues = merge([a, b])
    assert [c.text for c in cues] == ["x", "стык", "y"]
    assert [c.id for c in cues] == [1, 2, 3]


def test_merge_carries_missing_end_and_dedupes_within_2s():
    a = [ParsedLine(10, None, "стык ")]
    b = [ParsedLine(11.5, None, "стык"), ParsedLine(20, None, "z")]
    cues = merge([b, a])
    assert [(c.start, c.end, c.text) for c in cues] == [(10, None, "стык"), (20, None, "z")]


def test_fix_ends_keeps_valid_chat_end():
    assert fix_ends([Cue(1, 2, 4, "a"), Cue(2, 4, 7, "b")], 100)[0].end == 4


def test_fix_ends_repairs_invalid():
    out = fix_ends([Cue(1, 2, 2, "abc"), Cue(2, 3, 50, "b"), Cue(3, 5, 500, "c")], 100)
    assert out[0].end == 3
    assert out[1].end == 5
    assert out[2].end <= 100


def test_fix_ends_missing_end_uses_reading_time():
    out = fix_ends([Cue(1, 0, None, "x" * 30), Cue(2, 60, None, "y")], 100)
    assert out[0].end == 2.0
    assert out[1].end == 61.5
    assert fix_ends([Cue(1, 0, None, "x" * 300)], 100)[0].end == 7.0


def test_completeness():
    full = [Cue(1, 0, 5, "a"), Cue(2, 580, 590, "b")]
    r = check_completeness(full, 600)
    assert r.complete and r.gaps == ((5, 580),)
    assert check_completeness([Cue(1, 0, 5, "a")], 600).complete is False
    assert check_completeness([], 600).complete is False


def test_merge_joins_same_start_lines():
    cues = merge([[ParsedLine(10, None, "а"), ParsedLine(10, None, "б"), ParsedLine(20, None, "в")]])
    assert [(c.id, c.start, c.end, c.text) for c in cues] == [(1, 10, None, "а б"), (2, 20, None, "в")]


def test_merge_same_start_keeps_max_end():
    cues = merge([[ParsedLine(10, 12, "а"), ParsedLine(10, None, "б"), ParsedLine(10, 15, "в")]])
    assert [(c.end, c.text) for c in cues] == [(15, "а б в")]


def test_fix_ends_drops_cues_past_duration_and_renumbers():
    out = fix_ends([Cue(1, 5, None, "a"), Cue(2, 100, None, "b"), Cue(3, 120, 130, "c")], 100)
    assert [c.id for c in out] == [1]
    assert all(c.end > c.start for c in out)


def test_fix_ends_every_end_after_start():
    cues = merge([[ParsedLine(10, None, "а"), ParsedLine(10, None, "б"), ParsedLine(99.9, None, "в")]])
    out = fix_ends(cues, 100)
    assert all(c.end > c.start for c in out)


def test_completeness_leading_gap():
    r = check_completeness([Cue(1, 180, 590, "a")], 600)
    assert r.complete and r.gaps == ((0, 180),)


def test_merge_seam_dedupe_applies_before_join():
    a = [ParsedLine(10, 12, "p"), ParsedLine(10, 12, "q")]
    b = [ParsedLine(11, 13, "p")]
    assert [(c.start, c.text) for c in merge([a, b])] == [(10, "p q")]


def test_fix_ends_same_start_unmerged_never_degenerate():
    out = fix_ends([Cue(1, 10, None, "a"), Cue(2, 10, None, "b"), Cue(3, 20, None, "c")], 100)
    assert all(c.end > c.start for c in out)
    assert out[0].end == 11.5 and out[1].end == 11.5
