"""Capability «summary»: one chat request for a video summary in the given language, cached."""

from lingotube.ask.client import AskClient
from lingotube.cache import Cache, CacheKey
from lingotube.errors import ChatUnavailableError
from lingotube.prompts import PROMPT_VERSION, load_prompt

MODE = "chat"
KIND = "summary"


class SummaryFeature:
    def __init__(self, ask: AskClient, cache: Cache) -> None:
        self._ask = ask
        self._cache = cache

    async def run(self, video_id: str, language: str, *, use_cache: bool = True) -> str:
        key = CacheKey(video_id, KIND, language, MODE, PROMPT_VERSION)
        if use_cache:
            data = await self._cache.get(key)
            if data is not None and isinstance(data.get("text"), str) and data["text"].strip():
                return data["text"]
        session = await self._ask.open(video_id)
        text = (await session.ask(load_prompt("summary", language=language))).strip()
        if not text:
            raise ChatUnavailableError(
                "Чат вернул пустой ответ вместо краткого содержания.",
                hint="Повторите запрос позже.",
            )
        await self._cache.put(key, {"text": text})
        return text
