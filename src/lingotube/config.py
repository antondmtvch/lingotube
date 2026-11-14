"""Settings: TOML file + env overrides, platform paths, remembered cookies path.

The model API key is NOT a setting: only the *name* of the env var is stored
(``api_key_env``); the value is read from the environment by the container.
"""

import asyncio
import contextlib
import math
import os
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_path, user_config_path, user_data_path

from lingotube.errors import ValidationError

APP_NAME = "lingotube"
ENV_LANG = "LINGOTUBE_LANG"
ENV_COOKIES_FILE = "LINGOTUBE_COOKIES_FILE"


@dataclass(frozen=True)
class TranslatorSettings:
    """Settings of the own-model translator, an OpenAI-compatible API.

    Attributes:
        base_url: Base URL of the API, for example https://api.openai.com/v1.
        model: Model name sent to the API.
        api_key_env: Name of the environment variable that holds the key.
            The key itself is never stored in the settings.
        batch_size: Number of lines translated in one request.
    """

    base_url: str
    model: str
    api_key_env: str = "LINGOTUBE_API_KEY"
    batch_size: int = 40


@dataclass(frozen=True)
class Settings:
    """Effective settings: the settings file, then the environment overrides.

    Attributes:
        lang: Subtitle language code, or None.
        format: Default output format: srt, vtt or json.
        cookies_file: Path to a cookies file, or None.
        browser: Browser to read cookies from, or None.
        chunk_seconds: Length of one chunk of a long video, in seconds.
        min_interval: Minimum pause between chat requests, in seconds.
        max_retries: Number of retries after a failed request.
        translator: Own-model translator settings, or None for the chat mode.
    """

    lang: str | None = None
    format: str = "srt"
    cookies_file: Path | None = None
    browser: str | None = None
    chunk_seconds: int = 300  # live probe: 10-minute chunks get truncated
    min_interval: float = 5.0
    max_retries: int = 2
    translator: TranslatorSettings | None = None


def default_paths() -> tuple[Path, Path]:
    """Return the default settings file and cache folder.

    Creates nothing.

    Returns:
        A tuple of the settings file path and the cache folder path.
    """
    config = user_config_path(
        appname=APP_NAME,
        appauthor=False,
    )
    cache = user_cache_path(
        appname=APP_NAME,
        appauthor=False,
    )
    return config / "settings.toml", cache


@dataclass(frozen=True)
class LoginPaths:
    """Locations used by the sign-in profile of ``lingotube login``.

    Attributes:
        profile_dir: Browser profile folder used for sign-in.
        cookies_file: File where the saved YouTube cookies are kept.
    """

    profile_dir: Path
    cookies_file: Path


def default_login_paths() -> LoginPaths:
    """Return the sign-in profile folder and the saved-cookies file.

    Creates nothing.

    Returns:
        The login paths in the user data folder.
    """
    data = user_data_path(
        appname=APP_NAME,
        appauthor=False,
    )
    return LoginPaths(
        profile_dir=data / "login-profile",
        cookies_file=data / "login-cookies.json",
    )


_TOP_TYPES = {
    "lang": "str",
    "format": "str",
    "cookies_file": "str",
    "browser": "str",
    "chunk_seconds": "int",
    "min_interval": "float",
    "max_retries": "int",
}
_TR_TYPES = {
    "base_url": "str",
    "model": "str",
    "api_key_env": "str",
    "batch_size": "int",
}


def _check(
    name: str,
    value: object,
    typ: str,
    where: str,
) -> object:
    ok = {
        "str": isinstance(
            value,
            str,
        ),
        "int": isinstance(
            value,
            int,
        )
        and not isinstance(
            value,
            bool,
        ),
        "float": isinstance(
            value,
            (int, float),
        )
        and not isinstance(
            value,
            bool,
        ),
    }[typ]
    if not ok:
        raise ValidationError(message=f"Setting '{where}{name}' must be of type {typ}")
    if typ == "float":
        try:
            number = float(value)  # type: ignore[arg-type]
        except OverflowError:  # a TOML integer too large for a float
            number = math.inf
        if not math.isfinite(number):
            raise ValidationError(message=f"Setting '{where}{name}' must be a finite number")
        return number
    return value


_MIN = {
    "chunk_seconds": (1, "greater than 0"),
    "batch_size": (1, "greater than 0"),
    "min_interval": (0, "at least 0"),
    "max_retries": (0, "at least 0"),
}
FORMATS = ("srt", "vtt", "json")


def _validated(
    name: str,
    value: object,
    typ: str,
    where: str,
) -> object:
    value = _check(
        name=name,
        value=value,
        typ=typ,
        where=where,
    )
    if name in _MIN and value < _MIN[name][0]:  # type: ignore[operator]
        raise ValidationError(message=f"Setting '{where}{name}' must be {_MIN[name][1]}")
    if name == "format" and value not in FORMATS:
        raise ValidationError(message=f"Setting 'format' must be one of {', '.join(FORMATS)}")
    return value


def _parse_translator(raw: object) -> TranslatorSettings:
    if not isinstance(
        raw,
        dict,
    ):
        raise ValidationError(message="Setting 'translator' must be a table")
    for k in raw:
        if k not in _TR_TYPES:
            raise ValidationError(message=f"Unknown setting 'translator.{k}'")
    for req in ("base_url", "model"):
        if req not in raw:
            raise ValidationError(message=f"Setting 'translator.{req}' is required")
    return TranslatorSettings(
        **{
            k: _validated(
                name=k,
                value=v,
                typ=_TR_TYPES[k],
                where="translator.",
            )
            for k, v in raw.items()
        }
    )


def load_settings(
    path: Path | None,
    env: Mapping[str, str],
) -> Settings:
    """Load settings from the TOML file and the environment.

    The environment overrides the file. The function is synchronous on purpose: it runs
    once at startup and reads a small file.

    Args:
        path: Settings file, or None to use only the environment.
        env: Environment variables, usually os.environ.

    Returns:
        The effective settings.

    Raises:
        ValidationError: If the file cannot be read or a setting is invalid.
    """
    values: dict[str, object] = {}
    if path is not None:
        try:
            with open(
                path,
                "rb",
            ) as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            data = {}
        except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            raise ValidationError(message=f"Cannot read settings file {path}: {e}") from e
        for k, v in data.items():
            if k == "translator":
                values[k] = _parse_translator(raw=v)
            elif k in _TOP_TYPES:
                values[k] = _validated(
                    name=k,
                    value=v,
                    typ=_TOP_TYPES[k],
                    where="",
                )
            else:
                raise ValidationError(
                    message=f"Unknown setting '{k}'",
                    hint=f"Allowed: {sorted([*_TOP_TYPES, 'translator'])}",
                )
    if env.get(
        ENV_LANG,
        "",
    ).strip():
        values["lang"] = env[ENV_LANG].strip()
    if env.get(
        ENV_COOKIES_FILE,
        "",
    ).strip():
        values["cookies_file"] = env[ENV_COOKIES_FILE].strip()
    if isinstance(
        values.get("cookies_file"),
        str,
    ):
        cookies_file = Path(values["cookies_file"])
        if (
            path is not None
            and not (cookies_file.is_absolute() or cookies_file.root)
            and env.get(ENV_COOKIES_FILE, "").strip() == ""
        ):
            cookies_file = path.parent / cookies_file  # relative to the settings file
        values["cookies_file"] = cookies_file
    return Settings(**values)  # type: ignore[arg-type]


# --- minimal TOML writer (stdlib has none); scalars, lists and one level of tables ---


def _toml_str(s: str) -> str:
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _toml_value(v: object) -> str:
    if isinstance(
        v,
        bool,
    ):
        return "true" if v else "false"
    if isinstance(
        v,
        (int, float),
    ):
        return repr(v)
    if isinstance(
        v,
        str,
    ):
        return _toml_str(s=v)
    if isinstance(
        v,
        list,
    ):
        return "[" + ", ".join(_toml_value(v=i) for i in v) + "]"
    raise ValidationError(message=f"Cannot serialize settings value of type {type(v).__name__}")


def _dump_toml(data: dict) -> str:
    lines = [
        f"{k} = {_toml_value(v=v)}"
        for k, v in data.items()
        if not isinstance(
            v,
            dict,
        )
    ]
    for k, table in (
        (k, v)
        for k, v in data.items()
        if isinstance(
            v,
            dict,
        )
    ):
        lines += ["", f"[{k}]"]
        lines += [f"{kk} = {_toml_value(v=vv)}" for kk, vv in table.items()]
    return "\n".join(lines) + "\n"


def _remember(
    path: Path,
    settings_path: Path,
) -> None:
    try:
        data = tomllib.loads(settings_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise ValidationError(message=f"Cannot update settings file {settings_path}: {e}") from e
    value = str(path.resolve())
    if data.get("cookies_file") == value:
        return  # unchanged: keep the user's file (comments, formatting) as is
    data["cookies_file"] = value
    _write_settings_atomically(
        settings_path=settings_path,
        data=data,
    )


def _write_settings_atomically(
    settings_path: Path,
    data: dict,
) -> None:
    """Dump ``data`` as TOML via a temp file in the same dir, then replace."""
    text = _dump_toml(data=data)
    settings_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    fd, tmp = tempfile.mkstemp(
        dir=settings_path.parent,
        prefix=".tmp-",
        suffix=".part",
    )
    try:
        with os.fdopen(
            fd=fd,
            mode="w",
            encoding="utf-8",
        ) as f:
            f.write(text)
        os.replace(
            src=tmp,
            dst=settings_path,
        )
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path=tmp)


async def remember_cookies_file(
    path: Path,
    settings_path: Path,
) -> None:
    """Save the path of a cookies file in the settings file.

    Does nothing if the same path is already saved.

    Args:
        path: Cookies file to remember.
        settings_path: Settings file to update.

    Raises:
        ValidationError: If the settings file cannot be read.
        OSError: If the settings file cannot be written.
    """
    await asyncio.to_thread(
        _remember,
        path,
        settings_path,
    )


_REMEMBERED_COOKIE_SOURCE_KEYS = ("cookies_file", "browser")


def _forget_remembered_cookie_sources_blocking(settings_path: Path) -> list[str]:
    try:
        data = tomllib.loads(settings_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise ValidationError(message=f"Cannot update settings file {settings_path}: {e}") from e
    removed = [key for key in _REMEMBERED_COOKIE_SOURCE_KEYS if key in data]
    if not removed:
        return []  # keep the user's file (comments, formatting) as is
    for key in removed:
        del data[key]
    _write_settings_atomically(
        settings_path=settings_path,
        data=data,
    )
    return removed


async def forget_remembered_cookie_sources(settings_path: Path) -> list[str]:
    """Remove the remembered ``cookies_file`` and ``browser`` settings.

    Args:
        settings_path: Settings file to update.

    Returns:
        The names of the keys that were removed.
    """
    return await asyncio.to_thread(
        _forget_remembered_cookie_sources_blocking,
        settings_path,
    )
