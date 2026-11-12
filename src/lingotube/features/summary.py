"""Capability «summary»: one chat request for a video summary in the given language, cached."""

from collections.abc import Callable

from lingotube.ask.client import AskClient
from lingotube.cache import Cache, CacheKey, put_best_effort
from lingotube.errors import ChatUnavailableError
from lingotube.prompts import PROMPT_VERSION, load_prompt

MODE = "chat"
KIND = "summary"


class SummaryFeature:
    def __init__(
        self,
        ask: AskClient,
        cache: Cache,
        warn: Callable[[str], None] = lambda message: None,
    ) -> None:
        self._ask = ask
        self._cache = cache
        self._warn = warn

    async def run(
        self,
        video_id: str,
        language: str,
        *,
        use_cache: bool = True,
    ) -> str:
        key = CacheKey(
            video_id=video_id,
            kind=KIND,
            language=language,
            mode=MODE,
            prompt_version=PROMPT_VERSION,
        )
        if use_cache:
            data = await self._cache.get(key=key)
            if (
                data is not None
                and isinstance(
                    data.get("text"),
                    str,
                )
                and data["text"].strip()
            ):
                return data["text"]
        session = await self._ask.open(video_id=video_id)
        text = (
            await session.ask(
                prompt=load_prompt(
                    name="summary",
                    language=language,
                )
            )
        ).strip()
        if not text:
            raise ChatUnavailableError(
                message="Чат вернул пустой ответ вместо краткого содержания.",
                hint="Повторите запрос позже.",
            )
        failed = await put_best_effort(
            cache=self._cache,
            key=key,
            value={"text": text},
        )
        if failed is not None:
            self._warn(failed)
        return text


def register(
    app,
    get_context,
) -> None:
    """Adds the `summary` command: text to stdout, or to a file with -o."""
    from lingotube import commands as c

    @app.command(
        name="summary",
        help="Краткое содержание на выбранном языке.",
    )
    def summary(
        video: c.VideoArg,
        lang: c.LangOpt = None,
        output: c.OutputOpt = None,
        cookies_file: c.CookiesFileOpt = None,
        browser: c.BrowserOpt = None,
        no_cache: c.NoCacheOpt = False,
        json_: c.JsonOpt = False,
    ) -> None:
        common = c.Common(
            json=json_,
            cookies_file=cookies_file,
            browser=browser,
            no_cache=no_cache,
        )

        async def body(
            ctx: c.AppContext,
            video_id: str | None,
        ) -> c.Outcome:
            assert video_id is not None
            language = c.require_lang(
                lang=lang,
                settings=ctx.settings,
            )
            feature = await ctx.provide(provider=ctx.container.summary_feature)
            text = await feature.run(
                video_id=video_id,
                language=language,
                use_cache=common.use_cache,
            )
            path = await c.deliver(
                ctx=ctx,
                text=text + "\n",
                output=output if output is not None else "-",
                default_name="",
            )
            result = {"video_id": video_id, "language": language, "text": text}
            if path is not None:
                result["path"] = str(path)
            return c.Outcome(
                result=result,
                text=text if path is None else None,
            )

        c.execute(
            get_context=get_context,
            common=common,
            video=video,
            body=body,
        )
