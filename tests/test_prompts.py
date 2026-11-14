"""Tests of the versioned prompt texts and their variables."""

from importlib import resources

import pytest

from lingotube.parsing import ParsedLine, parse_answer
from lingotube.prompts import PROMPT_VERSION, load_prompt
from lingotube.translate.openai_compat import _parse

NAMES = ("transcript", "transcript_translated", "summary", "translate_batch")


def test_version():
    """Check the version of the prompts."""
    assert PROMPT_VERSION == "1"


def test_transcript_substitutes_range():
    """Check that the transcript prompt gets the start and the end of the range."""
    text = load_prompt(
        name="transcript",
        start="0:00",
        end="10:00",
    )
    assert "0:00" in text and "10:00" in text
    assert "{" not in text


def test_transcript_hour_format_kept():
    """Check that the hour format of a timecode is kept in the prompt."""
    assert "1:05:00" in load_prompt(
        name="transcript",
        start="1:05:00",
        end="1:10:00",
    )


def test_translated_mentions_language_and_forbids_original():
    """Check that the translated prompt names the language and forbids the original text."""
    text = load_prompt(
        name="transcript_translated",
        start="0:00",
        end="5:00",
        language="Russian",
    )
    assert "Russian" in text and "{" not in text
    assert "только" in text and "оригинал" in text


def test_summary_language():
    """Check that the summary prompt gets the language."""
    text = load_prompt(
        name="summary",
        language="Russian",
    )
    assert "Russian" in text and "{" not in text


def test_translate_batch_keeps_tab_and_language():
    """Check that the batch translation prompt keeps the tab and gets the language."""
    text = load_prompt(
        name="translate_batch",
        language="German",
    )
    assert "German" in text
    assert "\t" in text


@pytest.mark.parametrize(
    argnames=("name", "variables"),
    argvalues=[
        ("transcript", {"start": "0:00"}),
        ("transcript_translated", {"start": "0:00", "end": "1:00"}),
        ("summary", {}),
        ("translate_batch", {}),
    ],
)
def test_missing_variable_raises_key_error(
    name,
    variables,
):
    """Check that a missing variable raises KeyError."""
    with pytest.raises(expected_exception=KeyError):
        load_prompt(
            name=name,
            **variables,
        )


def test_extra_variable_is_ignored():
    """Check that an extra variable is ignored."""
    assert "{" not in load_prompt(
        name="summary",
        language="Russian",
        unused="x",
    )


def test_substituted_value_with_braces_is_not_reprocessed():
    """Check that a substituted value with braces is not substituted again."""
    text = load_prompt(
        name="summary",
        language="{start}",
    )
    assert "{start}" in text


def test_unknown_name_raises():
    """Check that an unknown prompt name raises an error."""
    with pytest.raises(expected_exception=FileNotFoundError):
        load_prompt(name="nope")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    argnames="name",
    argvalues=NAMES,
)
def test_files_are_package_data(name):
    """Check that the prompt files are shipped with the package."""
    path = resources.files("lingotube") / "prompts" / f"{name}.v1.txt"
    assert path.is_file()
    assert path.read_text(encoding="utf-8").strip()


def test_format_doc_is_package_data():
    """Check that the format document is shipped with the package."""
    assert (resources.files("lingotube") / "prompts" / "FORMAT.md").is_file()


@pytest.mark.parametrize(
    argnames="name",
    argvalues=["transcript", "transcript_translated"],
)
def test_requested_timecode_format_parses(name):
    """Check that the sample answer format of the prompts is parsed.

    The sample answer uses ``m:ss`` timecodes, and ``h:mm:ss`` after one hour.

    Args:
        name: Prompt name, the transcript or the translated transcript.
    """
    prompt = load_prompt(
        name=name,
        start="0:00",
        end="1:10:00",
        language="Russian",
    )
    assert "(м:сс) текст" in prompt and "(ч:мм:сс)" in prompt
    answer = "(0:14) Всем привет.\n(59:59) Конец часа.\n(1:00:05) Второй час."
    assert parse_answer(text=answer) == [
        ParsedLine(
            start=14.0,
            end=None,
            text="Всем привет.",
        ),
        ParsedLine(
            start=3599.0,
            end=None,
            text="Конец часа.",
        ),
        ParsedLine(
            start=3605.0,
            end=None,
            text="Второй час.",
        ),
    ]


def test_translate_batch_requested_format_parses():
    """Check that the format requested by the batch translation prompt is parsed."""
    prompt = load_prompt(
        name="translate_batch",
        language="German",
    )
    assert "номер<TAB>перевод" in prompt
    assert _parse(
        answer="1\tHallo, Welt\n2\tBis bald",
        count=2,
    ) == ["Hallo, Welt", "Bis bald"]
