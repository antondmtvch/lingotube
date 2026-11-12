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

from lingotube.ask.client import AskClient, Pacer, YouTubeAskClient
from lingotube.auth.base import CookieSource
from lingotube.auth.browser import (
    BROWSERS,
    BrowserCookieSource,
    ChainCookieSource,
    default_loader,
)
from lingotube.auth.file import FileCookieSource
from lingotube.cache import Cache
from lingotube.config import Settings
from lingotube.doctor import FILE_SOURCE, UnsetCookieFile, browser_source_name
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
    async with httpx.AsyncClient(
        follow_redirects=False,
        cookies=jar,
        trust_env=False,
    ) as client:
        yield client


@asynccontextmanager
async def translator_http() -> AsyncIterator[httpx.AsyncClient]:
    """The translator's own client: never carries YouTube cookies."""
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=TRANSLATOR_TIMEOUT,
    ) as client:
        yield client


def stream_writer(stream: TextIO) -> Callable[[str], None]:
    def write(message: str) -> None:
        stream.write(message + "\n")
        stream.flush()

    return write


def progress_writer(stream: TextIO) -> Callable[[int, int], None]:
    write = stream_writer(stream=stream)
    return lambda done, total: write(f"часть {done} из {total}")


BrowserLoader = Callable[[str], Mapping[str, str]]


def make_cookie_source(
    settings: Settings,
    warn: Callable[[str], None],
    loader: BrowserLoader = default_loader,
) -> CookieSource:
    if settings.cookies_file is not None:
        return FileCookieSource(
            path=settings.cookies_file,
            warn=warn,
        )
    if settings.browser is not None:
        return BrowserCookieSource(
            browser=settings.browser,
            loader=loader,
        )
    return ChainCookieSource(
        sources=[
            BrowserCookieSource(
                browser=None,
                loader=loader,
            )
        ]
    )


def make_doctor_sources(
    settings: Settings,
    warn: Callable[[str], None],
    loader: BrowserLoader = default_loader,
) -> dict[str, CookieSource]:
    """Every cookie source `doctor` checks separately: the file, then each browser
    (only the chosen one when a browser is set)."""
    sources: dict[str, CookieSource] = {
        FILE_SOURCE: (
            FileCookieSource(
                path=settings.cookies_file,
                warn=warn,
            )
            if settings.cookies_file is not None
            else UnsetCookieFile()
        )
    }
    for browser in (settings.browser,) if settings.browser is not None else BROWSERS:
        sources[browser_source_name(browser=browser)] = BrowserCookieSource(
            browser=browser,
            loader=loader,
        )
    return sources


def make_ask_factory(
    http: httpx.AsyncClient,
    pacer: Pacer,
    max_retries: int,
) -> Callable[[CookieSource], AskClient]:
    """A chat client per cookie source (doctor tries sources one by one); one shared pacer."""
    return lambda source: YouTubeAskClient(
        http=http,
        cookies=source,
        pacer=pacer,
        max_retries=max_retries,
    )


def translator_mode(settings: Settings) -> str:
    return "own_model" if settings.translator is not None else "none"


def translator_api_key(
    settings: Settings,
    env: Mapping[str, str],
) -> str:
    assert settings.translator is not None
    name = settings.translator.api_key_env
    key = env.get(
        name,
        "",
    ).strip()
    if not key:
        raise AuthError(
            message="Не задан ключ модели перевода.",
            hint=f"Задайте ключ в переменной окружения {name} (ключ не передаётся параметром команды).",
        )
    return key


class Container(containers.DeclarativeContainer):
    settings = providers.Dependency(instance_of=Settings)
    env = providers.Dependency(instance_of=Mapping)
    cache_dir = providers.Dependency(instance_of=Path)
    err = providers.Dependency()

    warn = providers.Singleton(
        stream_writer,
        stream=err,
    )
    progress = providers.Singleton(
        progress_writer,
        stream=err,
    )

    http = providers.Resource(youtube_http)
    translator_http = providers.Resource(translator_http)

    browser_loader = providers.Object(default_loader)
    cookie_source = providers.Singleton(
        make_cookie_source,
        settings=settings,
        warn=warn,
        loader=browser_loader,
    )
    doctor_sources = providers.Singleton(
        make_doctor_sources,
        settings=settings,
        warn=warn,
        loader=browser_loader,
    )
    pacer = providers.Singleton(
        Pacer,
        min_interval=settings.provided.min_interval,
    )
    ask_client = providers.Singleton(
        YouTubeAskClient,
        http=http,
        cookies=cookie_source,
        pacer=pacer,
        max_retries=settings.provided.max_retries,
    )
    ask_factory = providers.Singleton(
        make_ask_factory,
        http=http,
        pacer=pacer,
        max_retries=settings.provided.max_retries,
    )
    cache = providers.Singleton(
        Cache,
        root=cache_dir,
    )

    translator = providers.Selector(
        selector=providers.Callable(
            translator_mode,
            settings=settings,
        ),
        own_model=providers.Singleton(
            OpenAICompatTranslator,
            http=translator_http,
            settings=settings.provided.translator,
            api_key=providers.Callable(
                translator_api_key,
                settings=settings,
                env=env,
            ),
        ),
        none=providers.Object(None),
    )

    transcript_feature = providers.Factory(
        TranscriptFeature,
        ask=ask_client,
        cache=cache,
        settings=settings,
        progress=progress,
    )
    subtitles_feature = providers.Factory(
        SubtitlesFeature,
        transcripts=transcript_feature,
        translator=translator,
        cache=cache,
    )
    summary_feature = providers.Factory(
        SummaryFeature,
        ask=ask_client,
        cache=cache,
        warn=warn,
    )
    build_feature = providers.Factory(
        BuildFeature,
        cache=cache,
    )


def build_container(
    *,
    settings: Settings,
    env: Mapping[str, str],
    cache_dir: Path,
    err: TextIO,
) -> Container:
    return Container(
        settings=providers.Object(settings),
        env=providers.Object(env),
        cache_dir=providers.Object(cache_dir),
        err=providers.Object(err),
    )
