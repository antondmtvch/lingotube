from pathlib import Path

import pytest

from lingotube.config import (
    Settings,
    TranslatorSettings,
    default_paths,
    load_settings,
    remember_cookies_file,
)
from lingotube.errors import ValidationError


def test_load_settings_defaults():
    assert load_settings(None, {}) == Settings()
    s = Settings()
    assert (s.chunk_seconds, s.min_interval, s.max_retries, s.format) == (
        300,
        5.0,
        2,
        "srt",
    )


def test_missing_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "none.toml", {}) == Settings()


def test_load_settings_from_toml_and_env(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text(
        'lang = "ru"\nformat = "vtt"\ncookies_file = "/a/c.txt"\nmin_interval = 7\n'
        '[translator]\nbase_url = "http://x/v1"\nmodel = "m"\nbatch_size = 10\n',
        encoding="utf-8",
    )
    s = load_settings(f, {})
    assert s.lang == "ru" and s.format == "vtt" and s.min_interval == 7.0
    assert s.cookies_file == Path("/a/c.txt")
    assert s.translator == TranslatorSettings("http://x/v1", "m", batch_size=10)
    s = load_settings(f, {"LINGOTUBE_LANG": "de", "LINGOTUBE_COOKIES_FILE": "/e/c.txt"})
    assert s.lang == "de" and s.cookies_file == Path("/e/c.txt")


def test_unknown_key_in_toml_is_validation_error(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text("bogus = 1\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="bogus"):
        load_settings(f, {})
    f.write_text(
        '[translator]\nbase_url="u"\nmodel="m"\napi_key="zzz"\n', encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="api_key"):
        load_settings(f, {})


def test_wrong_types_and_bad_toml(tmp_path):
    f = tmp_path / "s.toml"
    for text in [
        'chunk_seconds = "x"\n',
        "lang = 5\n",
        "max_retries = true\n",
        "lang = \n",
        '[translator]\nmodel = "m"\n',
    ]:
        f.write_text(text, encoding="utf-8")
        with pytest.raises(ValidationError):
            load_settings(f, {})


def test_api_key_never_in_settings_repr():
    t = TranslatorSettings("http://x", "m")
    assert t.api_key_env == "LINGOTUBE_API_KEY"
    s = Settings(translator=t)
    env = {"LINGOTUBE_API_KEY": "sk-secret-123"}
    assert "sk-secret-123" not in repr(load_settings(None, env)) + repr(s)
    assert not any(
        "key" in f and f != "api_key_env"
        for f in TranslatorSettings.__dataclass_fields__
    )


async def test_remember_cookies_file_creates_and_preserves(tmp_path):
    sp = tmp_path / "sub" / "settings.toml"
    cookies = tmp_path / "c.txt"
    await remember_cookies_file(cookies, sp)
    assert load_settings(sp, {}).cookies_file == cookies.resolve()
    sp.write_text(
        'lang = "ru"\ncookies_file = "old"\nmin_interval = 2.5\n[translator]\nbase_url = "u\\"q"\nmodel = "m"\n',
        encoding="utf-8",
    )
    await remember_cookies_file(Path("rel.txt"), sp)
    s = load_settings(sp, {})
    assert s.lang == "ru" and s.min_interval == 2.5
    assert s.translator == TranslatorSettings('u"q', "m")
    assert s.cookies_file == Path("rel.txt").resolve()
    assert [p.name for p in sp.parent.iterdir()] == ["settings.toml"]


def test_default_paths_creates_nothing():
    settings, cache = default_paths()
    assert settings.name == "settings.toml" and "lingotube" in str(settings).lower()
    assert "lingotube" in str(cache).lower()


@pytest.mark.parametrize(
    "text,key",
    [
        ("chunk_seconds = 0", "chunk_seconds"),
        ("chunk_seconds = -5", "chunk_seconds"),
        ("min_interval = -1", "min_interval"),
        ("min_interval = nan", "min_interval"),
        ("min_interval = inf", "min_interval"),
        ("max_retries = -1", "max_retries"),
        ("format = 'pdf'", "format"),
        ("[translator]\nbase_url='u'\nmodel='m'\nbatch_size = 0", "batch_size"),
        ("[translator]\nbase_url='u'\nmodel='m'\nbatch_size = -3", "batch_size"),
    ],
)
def test_out_of_range_values_rejected(tmp_path, text, key):
    f = tmp_path / "s.toml"
    f.write_text(text + "\n", encoding="utf-8")
    with pytest.raises(ValidationError, match=key) as ei:
        load_settings(f, {})
    assert (
        not any(c.isdigit() for c in str(ei.value).replace(key, ""))
        or "greater than 0" in str(ei.value)
        or "at least 0" in str(ei.value)
    )


def test_boundary_values_and_formats_accepted(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text(
        "chunk_seconds = 1\nmin_interval = 0\nmax_retries = 0\nformat = 'json'\n",
        encoding="utf-8",
    )
    s = load_settings(f, {})
    assert (s.chunk_seconds, s.min_interval, s.max_retries, s.format) == (
        1,
        0.0,
        0,
        "json",
    )
    for fmt in ("srt", "vtt"):
        f.write_text(f"format = '{fmt}'\n", encoding="utf-8")
        assert load_settings(f, {}).format == fmt


def test_empty_env_values_are_unset(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text('lang = "ru"\ncookies_file = "/a/c.txt"\n', encoding="utf-8")
    s = load_settings(f, {"LINGOTUBE_LANG": "  ", "LINGOTUBE_COOKIES_FILE": ""})
    assert s.lang == "ru" and s.cookies_file == Path("/a/c.txt")
    s = load_settings(None, {"LINGOTUBE_LANG": "", "LINGOTUBE_COOKIES_FILE": " "})
    assert s == Settings()
