import pytest

from lingotube.errors import (
    AuthError,
    ChatUnavailableError,
    IncompleteError,
    LingotubeError,
    NetworkError,
    ValidationError,
)
from lingotube.models import Cue, Transcript


def make() -> Transcript:
    return Transcript(
        video_id="dQw4w9WgXcQ",
        duration=750.0,
        language="en",
        prompt_version="1",
        cues=(
            Cue(
                id=1,
                start=2.0,
                end=4.0,
                text="Help!",
            ),
            Cue(
                id=2,
                start=4.0,
                end=None,
                text="x",
            ),
        ),
    )


def test_roundtrip():
    t = make()
    assert Transcript.from_dict(d=t.to_dict()) == t


def test_to_dict_keys():
    d = make().to_dict()
    assert set(d) == {"video_id", "duration", "language", "prompt_version", "cues"}
    assert d["cues"][0] == {"id": 1, "start": 2.0, "end": 4.0, "text": "Help!"}


@pytest.mark.parametrize(
    argnames="bad",
    argvalues=[
        {"cues": "x"},
        {},
        [],
        {**make().to_dict(), "cues": [{"id": "1", "start": 0, "end": 1, "text": "a"}]},
        {**make().to_dict(), "cues": [{"id": 1, "start": "0", "end": 1, "text": "a"}]},
        {**make().to_dict(), "cues": [{"id": 1, "start": 0, "end": "1", "text": "a"}]},
        {**make().to_dict(), "cues": [{"id": 1, "start": 0, "end": 1, "text": 5}]},
        {**make().to_dict(), "cues": ["x"]},
    ],
)
def test_from_dict_invalid(bad):
    with pytest.raises(expected_exception=ValidationError):
        Transcript.from_dict(d=bad)


@pytest.mark.parametrize(
    argnames=("cls", "code", "exit_code"),
    argvalues=[
        (ChatUnavailableError, "chat_unavailable", 3),
        (AuthError, "auth", 4),
        (IncompleteError, "incomplete", 5),
        (NetworkError, "network", 6),
        (ValidationError, "validation", 7),
    ],
)
def test_errors(
    cls,
    code,
    exit_code,
):
    e = cls(
        message="boom",
        hint="try this",
    )
    assert isinstance(
        e,
        LingotubeError,
    )
    assert (e.code, e.exit_code, e.message, e.hint) == (
        code,
        exit_code,
        "boom",
        "try this",
    )
    assert str(object=e) == "boom"
