"""A translator that is built only when the first translation is requested."""

import inspect
from collections.abc import Awaitable, Callable, Sequence

from lingotube.models import Cue
from lingotube.translate.base import Translator


class LazyTranslator:
    """Defers building the real translator (and so reading its API key) until `translate`.

    A command that needs no translation (same language, cached result) therefore never
    needs the key. `factory` may return the translator or an awaitable of it.
    """

    def __init__(
        self,
        factory: Callable[[], Translator | Awaitable[Translator]],
    ) -> None:
        self._factory = factory
        self._translator: Translator | None = None

    async def prepare(self) -> None:
        """Builds the real translator now, so a missing key surfaces before any slow work."""
        if self._translator is None:
            built = self._factory()
            if inspect.isawaitable(object=built):
                built = await built
            self._translator = built

    async def translate(
        self,
        cues: Sequence[Cue],
        target_language: str,
    ) -> list[Cue]:
        await self.prepare()
        assert self._translator is not None
        return await self._translator.translate(
            cues=cues,
            target_language=target_language,
        )
