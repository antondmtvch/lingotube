import pytest

from lingotube.parsing import ParsedLine, parse_answer


def test_interval_format():
    text = ("Ниже представлена транскрипция всех реплик:\n\n"
            "(0:02-0:04) Помогите!\n(0:04-0:07) Загоняем живого к грибам и бобрам.\n"
            "(0:07-0:10) Вот и думайте.\n")
    assert parse_answer(text) == [
        ParsedLine(2.0, 4.0, "Помогите!"),
        ParsedLine(4.0, 7.0, "Загоняем живого к грибам и бобрам."),
        ParsedLine(7.0, 10.0, "Вот и думайте."),
    ]


def test_start_only_format():
    assert parse_answer("(0:14) Всем привет, дорогие друзья.") == [
        ParsedLine(14.0, None, "Всем привет, дорогие друзья.")]


@pytest.mark.parametrize("line,start,end", [
    ("(1:02:03-1:02:07) x", 3723.0, 3727.0),
    ("[0:02 - 0:04] x", 2.0, 4.0),
    ("(0:02–0:04) x", 2.0, 4.0),
    ("(0:02—0:04) x", 2.0, 4.0),
    ("**(0:02-0:04)** x", 2.0, 4.0),
    ("- (0:02-0:04) x", 2.0, 4.0),
    ("(00:02-00:04) x", 2.0, 4.0),
])
def test_variations(line, start, end):
    assert parse_answer(line) == [ParsedLine(start, end, "x")]


def test_start_only_after_one_hour():
    assert parse_answer("(1:00:00) x") == [ParsedLine(3600.0, None, "x")]


def test_bracketed_sound_text_kept_verbatim():
    assert parse_answer("(0:05) [music]") == [ParsedLine(5.0, None, "[music]")]
    assert parse_answer("(0:05) [gasps] ох") == [ParsedLine(5.0, None, "[gasps] ох")]


def test_degenerate_interval_kept():
    assert parse_answer("(5:25-5:25) parasite.") == [ParsedLine(325.0, 325.0, "parasite.")]


def test_continuation_line_joins_previous():
    assert parse_answer("(0:02-0:04) Первая\nпродолжение\n(0:05-0:06) Вторая")[0].text == "Первая продолжение"


def test_preamble_and_outro_dropped():
    text = "Вот расшифровка:\n\n(0:02) Раз\n(0:05) Два\n\nНадеюсь, это помогло!"
    assert parse_answer(text) == [ParsedLine(2.0, None, "Раз"), ParsedLine(5.0, None, "Два")]


def test_outro_without_blank_line_joins_previous():
    assert parse_answer("(0:02) Раз\nНадеюсь") == [ParsedLine(2.0, None, "Раз Надеюсь")]


def test_no_timecodes_returns_empty():
    assert parse_answer("Извините, я не могу помочь.") == []


def test_empty_text_line_skipped():
    assert parse_answer("(0:02-0:04)   ") == []


def test_empty_input():
    assert parse_answer("") == []


def test_long_whitespace_line_is_fast():
    import time
    t = time.perf_counter()
    assert parse_answer(" " * 100_000 + "x") == []
    assert parse_answer("- " + " " * 100_000 + "x") == []
    assert parse_answer("(0:01) a\n" + "- " + " " * 100_000 + "x")[0].start == 1.0
    assert time.perf_counter() - t < 0.5


@pytest.mark.parametrize("line", ["(0:75) x", "(1:99:99-0:01) x", "(1:60:00) x", "(0:02-0:99) x"])
def test_out_of_range_is_not_a_timecode(line):
    assert parse_answer(line) == []


def test_out_of_range_line_follows_text_rules():
    assert parse_answer("(0:02) a\n(0:75) b") == [ParsedLine(2.0, None, "a (0:75) b")]


def test_end_before_start_gives_none_end():
    assert parse_answer("(0:10-0:05) x") == [ParsedLine(10.0, None, "x")]


def test_minutes_over_99_in_ms_form():
    assert parse_answer("(105:30) x") == [ParsedLine(6330.0, None, "x")]
