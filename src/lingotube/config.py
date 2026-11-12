"""Settings: TOML file + env overrides, platform paths, remembered cookies path.

The model API key is NOT a setting: only the *name* of the env var is stored
(``api_key_env``); the value is read from the environment by the container.
"""

import asyncio
import math
import os
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_path, user_config_path

from lingotube.errors import ValidationError

APP_NAME = "lingotube"
ENV_LANG = "LINGOTUBE_LANG"
ENV_COOKIES_FILE = "LINGOTUBE_COOKIES_FILE"


@dataclass(frozen=True)
class TranslatorSettings:
    base_url: str
    model: str
    api_key_env: str = "LINGOTUBE_API_KEY"
    batch_size: int = 40


@dataclass(frozen=True)
class Settings:
    lang: str | None = None
    format: str = "srt"
    cookies_file: Path | None = None
    browser: str | None = None
    chunk_seconds: int = 300  # live probe: 10-minute chunks get truncated
    min_interval: float = 5.0
    max_retries: int = 2
    translator: TranslatorSettings | None = None


def default_paths() -> tuple[Path, Path]:
    """(settings file, cache dir). Creates nothing."""
    config = user_config_path(
        appname=APP_NAME,
        appauthor=False,
    )
    cache = user_cache_path(
        appname=APP_NAME,
        appauthor=False,
    )
    return config / "settings.toml", cache


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
    if typ == "float" and not math.isfinite(value):  # type: ignore[arg-type]
        raise ValidationError(
            message=f"Setting '{where}{name}' must be a finite number"
        )
    return float(value) if typ == "float" else value  # type: ignore[arg-type]


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
        raise ValidationError(
            message=f"Setting '{where}{name}' must be {_MIN[name][1]}"
        )
    if name == "format" and value not in FORMATS:
        raise ValidationError(
            message=f"Setting 'format' must be one of {', '.join(FORMATS)}"
        )
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
    """Synchronous on purpose: called once at startup on a tiny file."""
    values: dict[str, object] = {}
    if path is not None:
        try:
            with open(
                file=path,
                mode="rb",
            ) as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            data = {}
        except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            raise ValidationError(
                message=f"Cannot read settings file {path}: {e}"
            ) from e
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
        values["cookies_file"] = Path(values["cookies_file"])
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
    raise ValidationError(
        message=f"Cannot serialize settings value of type {type(v).__name__}"
    )


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
        raise ValidationError(
            message=f"Cannot update settings file {settings_path}: {e}"
        ) from e
    data["cookies_file"] = str(object=path.resolve())
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
        try:
            os.unlink(path=tmp)
        except FileNotFoundError:
            pass


async def remember_cookies_file(
    path: Path,
    settings_path: Path,
) -> None:
    await asyncio.to_thread(
        _remember,
        path,
        settings_path,
    )
