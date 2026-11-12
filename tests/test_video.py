import pytest

from lingotube.errors import ValidationError
from lingotube.video import parse_video_id

OK = [
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=90s&list=PLx", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?si=abc", "dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("  https://youtu.be/dQw4w9WgXcQ  ", "dQw4w9WgXcQ"),
    ("-n5MqamatXE", "-n5MqamatXE"),
    ("https://www.youtube.com/watch?v=-n5MqamatXE", "-n5MqamatXE"),
]
BAD = [
    "",
    "hello",
    "https://example.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=short",
    "https://www.youtube.com/playlist?list=PLx",
]


@pytest.mark.parametrize(("src", "expected"), OK)
def test_ok(src, expected):
    assert parse_video_id(src) == expected


@pytest.mark.parametrize("src", BAD)
def test_bad(src):
    with pytest.raises(ValidationError) as ei:
        parse_video_id(src)
    assert ei.value.exit_code == 7
