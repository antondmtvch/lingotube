"""Composition root: the only place concrete implementations are created.

Components never import this module; only the CLI layer takes objects from it.
`Singleton` here means "one per container" (one per CLI invocation), not a global.
"""

from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from http.cookiejar import CookieJar, DefaultCookiePolicy
from pathlib import Path
from typing import TextIO

import httpx
from dependency_injector import containers, providers

from lingotube.ask.client import Pacer, YouTubeAskClient
from lingotube.auth.base import CookieSource
from lingotube.auth.browser import BrowserCookieSource, ChainCookieSource
from lingotube.auth.file import FileCookieSource
from lingotube.cache import Cache
from lingotube.config import Settings
from lingotube.errors import AuthError
from lingotube.features.build import BuildFeature
from lingotube.features.subtitles import SubtitlesFeature
from lingotube.features.summary import SummaryFeature
from lingotube.features.transcript import TranscriptFeature
from lingotube.translate.openai_compat import OpenAICompatTranslator

TRANSLATOR_TIMEOUT = 120.0  # a model translating a batch can be slow


@asynccontextmanager
async def youtube_http() -> AsyncIterator[httpx.AsyncClient]:
    """No redirects, no proxy env, and a jar that rejects every Set-Cookie: cookies
    travel only in the explicit header built by the chat client."""
    jar = CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))
    async with httpx.AsyncClient(follow_redirects=False, cookies=jar, trust_env=False) as client:
        yield client


@asynccontextmanager
async def translator_http() -> AsyncIterator[httpx.AsyncClient]:
    """The translator's own client: never carries YouTube cookies."""
    async with httpx.AsyncClient(follow_redirects=False, timeout=TRANSLATOR_TIMEOUT) as client:
        yield client


def stream_writer(stream: TextIO) -> Callable[[str], None]:
    def write(message: str) -> None:
        stream.write(message + "\n")
        stream.flush()

    return write


def progress_writer(stream: TextIO) -> Callable[[int, int], None]:
    write = stream_writer(stream)
    return lambda done, total: write(f"часть {done} из {total}")


def make_cookie_source(settings: Settings, warn: Callable[[str], None]) -> CookieSource:
    if settings.cookies_file is not None:
        return FileCookieSource(settings.cookies_file, warn=warn)
    if settings.browser is not None:
        return BrowserCookieSource(settings.browser)
    return ChainCookieSource([BrowserCookieSource(None)])


def translator_mode(settings: Settings) -> str:
    return "own_model" if settings.translator is not None else "none"


def translator_api_key(settings: Settings, env: Mapping[str, str]) -> str:
    assert settings.translator is not None
    name = settings.translator.api_key_env
    key = env.get(name, "").strip()
    if not key:
        raise AuthError(
            "Не задан ключ модели перевода.",
            hint=f"Задайте ключ в переменной окружения {name} (ключ не передаётся параметром команды).",
        )
    return key


class Container(containers.DeclarativeContainer):
    settings = providers.Dependency(instance_of=Settings)
    env = providers.Dependency(instance_of=Mapping)
    cache_dir = providers.Dependency(instance_of=Path)
    err = providers.Dependency()

    warn = providers.Singleton(stream_writer, err)
    progress = providers.Singleton(progress_writer, err)

    http = providers.Resource(youtube_http)
    translator_http = providers.Resource(translator_http)

    cookie_source = providers.Singleton(make_cookie_source, settings, warn)
    pacer = providers.Singleton(Pacer, settings.provided.min_interval)
    ask_client = providers.Singleton(
        YouTubeAskClient, http, cookie_source, pacer, max_retries=settings.provided.max_retries
    )
    cache = providers.Singleton(Cache, cache_dir)

    translator = providers.Selector(
        providers.Callable(translator_mode, settings),
        own_model=providers.Singleton(
            OpenAICompatTranslator,
            translator_http,
            settings.provided.translator,
            providers.Callable(translator_api_key, settings, env),
        ),
        none=providers.Object(None),
    )

    transcript_feature = providers.Factory(TranscriptFeature, ask_client, cache, settings, progress)
    subtitles_feature = providers.Factory(SubtitlesFeature, transcript_feature, translator, cache)
    summary_feature = providers.Factory(SummaryFeature, ask_client, cache)
    build_feature = providers.Factory(BuildFeature, cache)


def build_container(
    *, settings: Settings, env: Mapping[str, str], cache_dir: Path, err: TextIO
) -> Container:
    return Container(
        settings=providers.Object(settings),
        env=providers.Object(env),
        cache_dir=providers.Object(cache_dir),
        err=providers.Object(err),
    )
