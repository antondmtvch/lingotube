import json
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
    assert (
        load_settings(
            path=None,
            env={},
        )
        == Settings()
    )
    s = Settings()
    assert (s.chunk_seconds, s.min_interval, s.max_retries, s.format) == (
        300,
        5.0,
        2,
        "srt",
    )


def test_missing_file_gives_defaults(tmp_path):
    assert (
        load_settings(
            path=tmp_path / "none.toml",
            env={},
        )
        == Settings()
    )


def test_load_settings_from_toml_and_env(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text(
        data='lang = "ru"\nformat = "vtt"\ncookies_file = "/a/c.txt"\nmin_interval = 7\n'
        '[translator]\nbase_url = "http://x/v1"\nmodel = "m"\nbatch_size = 10\n',
        encoding="utf-8",
    )
    s = load_settings(
        path=f,
        env={},
    )
    assert s.lang == "ru" and s.format == "vtt" and s.min_interval == 7.0
    assert s.cookies_file == Path("/a/c.txt")
    assert s.translator == TranslatorSettings(
        base_url="http://x/v1",
        model="m",
        batch_size=10,
    )
    s = load_settings(
        path=f,
        env={"LINGOTUBE_LANG": "de", "LINGOTUBE_COOKIES_FILE": "/e/c.txt"},
    )
    assert s.lang == "de" and s.cookies_file == Path("/e/c.txt")


def test_unknown_key_in_toml_is_validation_error(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text(
        data="bogus = 1\n",
        encoding="utf-8",
    )
    with pytest.raises(
        expected_exception=ValidationError,
        match="bogus",
    ):
        load_settings(
            path=f,
            env={},
        )
    f.write_text(
        data='[translator]\nbase_url="u"\nmodel="m"\napi_key="zzz"\n',
        encoding="utf-8",
    )
    with pytest.raises(
        expected_exception=ValidationError,
        match="api_key",
    ):
        load_settings(
            path=f,
            env={},
        )


def test_wrong_types_and_bad_toml(tmp_path):
    f = tmp_path / "s.toml"
    for text in [
        'chunk_seconds = "x"\n',
        "lang = 5\n",
        "max_retries = true\n",
        "lang = \n",
        '[translator]\nmodel = "m"\n',
    ]:
        f.write_text(
            data=text,
            encoding="utf-8",
        )
        with pytest.raises(expected_exception=ValidationError):
            load_settings(
                path=f,
                env={},
            )


def test_api_key_never_in_settings_repr():
    t = TranslatorSettings(
        base_url="http://x",
        model="m",
    )
    assert t.api_key_env == "LINGOTUBE_API_KEY"
    s = Settings(translator=t)
    env = {"LINGOTUBE_API_KEY": "sk-secret-123"}
    assert "sk-secret-123" not in repr(
        load_settings(
            path=None,
            env=env,
        )
    ) + repr(s)
    assert not any(
        "key" in f and f != "api_key_env"
        for f in TranslatorSettings.__dataclass_fields__
    )


async def test_remember_cookies_file_creates_and_preserves(tmp_path):
    sp = tmp_path / "sub" / "settings.toml"
    cookies = tmp_path / "c.txt"
    await remember_cookies_file(
        path=cookies,
        settings_path=sp,
    )
    assert (
        load_settings(
            path=sp,
            env={},
        ).cookies_file
        == cookies.resolve()
    )
    sp.write_text(
        data='lang = "ru"\ncookies_file = "old"\nmin_interval = 2.5\n[translator]\nbase_url = "u\\"q"\nmodel = "m"\n',
        encoding="utf-8",
    )
    await remember_cookies_file(
        path=Path("rel.txt"),
        settings_path=sp,
    )
    s = load_settings(
        path=sp,
        env={},
    )
    assert s.lang == "ru" and s.min_interval == 2.5
    assert s.translator == TranslatorSettings(
        base_url='u"q',
        model="m",
    )
    assert s.cookies_file == Path("rel.txt").resolve()
    assert [p.name for p in sp.parent.iterdir()] == ["settings.toml"]


def test_default_paths_creates_nothing():
    settings, cache = default_paths()
    assert settings.name == "settings.toml" and "lingotube" in str(settings).lower()
    assert "lingotube" in str(cache).lower()


@pytest.mark.parametrize(
    argnames="text,key",
    argvalues=[
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
def test_out_of_range_values_rejected(
    tmp_path,
    text,
    key,
):
    f = tmp_path / "s.toml"
    f.write_text(
        data=text + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        expected_exception=ValidationError,
        match=key,
    ) as ei:
        load_settings(
            path=f,
            env={},
        )
    assert (
        not any(
            c.isdigit()
            for c in str(ei.value).replace(
                key,
                "",
            )
        )
        or "greater than 0" in str(ei.value)
        or "at least 0" in str(ei.value)
    )


def test_boundary_values_and_formats_accepted(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text(
        data="chunk_seconds = 1\nmin_interval = 0\nmax_retries = 0\nformat = 'json'\n",
        encoding="utf-8",
    )
    s = load_settings(
        path=f,
        env={},
    )
    assert (s.chunk_seconds, s.min_interval, s.max_retries, s.format) == (
        1,
        0.0,
        0,
        "json",
    )
    for fmt in ("srt", "vtt"):
        f.write_text(
            data=f"format = '{fmt}'\n",
            encoding="utf-8",
        )
        assert (
            load_settings(
                path=f,
                env={},
            ).format
            == fmt
        )


def test_empty_env_values_are_unset(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text(
        data='lang = "ru"\ncookies_file = "/a/c.txt"\n',
        encoding="utf-8",
    )
    s = load_settings(
        path=f,
        env={"LINGOTUBE_LANG": "  ", "LINGOTUBE_COOKIES_FILE": ""},
    )
    assert s.lang == "ru" and s.cookies_file == Path("/a/c.txt")
    s = load_settings(
        path=None,
        env={"LINGOTUBE_LANG": "", "LINGOTUBE_COOKIES_FILE": " "},
    )
    assert s == Settings()


async def test_remember_same_value_does_not_rewrite_file(tmp_path):
    sp = tmp_path / "settings.toml"
    cookies = tmp_path / "c.txt"
    original = (
        '# my comment\nlang = "ru"\n'
        f"cookies_file = {json.dumps(obj=str(cookies.resolve()))}\n"
    )
    sp.write_bytes(original.encode("utf-8"))
    await remember_cookies_file(
        path=cookies,
        settings_path=sp,
    )
    assert sp.read_bytes() == original.encode("utf-8")
