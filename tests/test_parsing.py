import pytest

from lingotube.parsing import ParsedLine, parse_answer


def test_interval_format():
    text = (
        "Ниже представлена транскрипция всех реплик:\n\n"
        "(0:02-0:04) Помогите!\n(0:04-0:07) Загоняем живого к грибам и бобрам.\n"
        "(0:07-0:10) Вот и думайте.\n"
    )
    assert parse_answer(text=text) == [
        ParsedLine(
            start=2.0,
            end=4.0,
            text="Помогите!",
        ),
        ParsedLine(
            start=4.0,
            end=7.0,
            text="Загоняем живого к грибам и бобрам.",
        ),
        ParsedLine(
            start=7.0,
            end=10.0,
            text="Вот и думайте.",
        ),
    ]


def test_start_only_format():
    assert parse_answer(text="(0:14) Всем привет, дорогие друзья.") == [
        ParsedLine(
            start=14.0,
            end=None,
            text="Всем привет, дорогие друзья.",
        )
    ]


@pytest.mark.parametrize(
    argnames="line,start,end",
    argvalues=[
        ("(1:02:03-1:02:07) x", 3723.0, 3727.0),
        ("[0:02 - 0:04] x", 2.0, 4.0),
        ("(0:02–0:04) x", 2.0, 4.0),
        ("(0:02—0:04) x", 2.0, 4.0),
        ("**(0:02-0:04)** x", 2.0, 4.0),
        ("- (0:02-0:04) x", 2.0, 4.0),
        ("(00:02-00:04) x", 2.0, 4.0),
    ],
)
def test_variations(
    line,
    start,
    end,
):
    assert parse_answer(text=line) == [
        ParsedLine(
            start=start,
            end=end,
            text="x",
        )
    ]


def test_start_only_after_one_hour():
    assert parse_answer(text="(1:00:00) x") == [
        ParsedLine(
            start=3600.0,
            end=None,
            text="x",
        )
    ]


def test_bracketed_sound_text_kept_verbatim():
    assert parse_answer(text="(0:05) [music]") == [
        ParsedLine(
            start=5.0,
            end=None,
            text="[music]",
        )
    ]
    assert parse_answer(text="(0:05) [gasps] ох") == [
        ParsedLine(
            start=5.0,
            end=None,
            text="[gasps] ох",
        )
    ]


def test_degenerate_interval_kept():
    assert parse_answer(text="(5:25-5:25) parasite.") == [
        ParsedLine(
            start=325.0,
            end=325.0,
            text="parasite.",
        )
    ]


def test_continuation_line_joins_previous():
    assert (
        parse_answer(text="(0:02-0:04) Первая\nпродолжение\n(0:05-0:06) Вторая")[0].text
        == "Первая продолжение"
    )


def test_preamble_and_outro_dropped():
    text = "Вот расшифровка:\n\n(0:02) Раз\n(0:05) Два\n\nНадеюсь, это помогло!"
    assert parse_answer(text=text) == [
        ParsedLine(
            start=2.0,
            end=None,
            text="Раз",
        ),
        ParsedLine(
            start=5.0,
            end=None,
            text="Два",
        ),
    ]


def test_outro_without_blank_line_joins_previous():
    assert parse_answer(text="(0:02) Раз\nНадеюсь") == [
        ParsedLine(
            start=2.0,
            end=None,
            text="Раз Надеюсь",
        )
    ]


def test_no_timecodes_returns_empty():
    assert parse_answer(text="Извините, я не могу помочь.") == []


def test_empty_text_line_skipped():
    assert parse_answer(text="(0:02-0:04)   ") == []


def test_empty_input():
    assert parse_answer(text="") == []


def test_long_whitespace_line_is_fast():
    import time

    t = time.perf_counter()
    assert parse_answer(text=" " * 100_000 + "x") == []
    assert parse_answer(text="- " + " " * 100_000 + "x") == []
    assert parse_answer(text="(0:01) a\n" + "- " + " " * 100_000 + "x")[0].start == 1.0
    assert time.perf_counter() - t < 0.5


@pytest.mark.parametrize(
    argnames="line",
    argvalues=["(0:75) x", "(1:99:99-0:01) x", "(1:60:00) x", "(0:02-0:99) x"],
)
def test_out_of_range_is_not_a_timecode(line):
    assert parse_answer(text=line) == []


def test_out_of_range_line_follows_text_rules():
    assert parse_answer(text="(0:02) a\n(0:75) b") == [
        ParsedLine(
            start=2.0,
            end=None,
            text="a (0:75) b",
        )
    ]


def test_end_before_start_gives_none_end():
    assert parse_answer(text="(0:10-0:05) x") == [
        ParsedLine(
            start=10.0,
            end=None,
            text="x",
        )
    ]


def test_minutes_over_99_in_ms_form():
    assert parse_answer(text="(105:30) x") == [
        ParsedLine(
            start=6330.0,
            end=None,
            text="x",
        )
    ]


def test_bullet_with_several_spaces_and_bold():
    assert parse_answer(text="-  **(0:02-0:04)** x") == [
        ParsedLine(
            start=2.0,
            end=4.0,
            text="x",
        )
    ]
    assert parse_answer(text="*   (0:02) x") == [
        ParsedLine(
            start=2.0,
            end=None,
            text="x",
        )
    ]
