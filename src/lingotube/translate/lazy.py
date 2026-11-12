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

    async def translate(
        self,
        cues: Sequence[Cue],
        target_language: str,
    ) -> list[Cue]:
        translator = self._factory()
        if inspect.isawaitable(object=translator):
            translator = await translator
        return await translator.translate(
            cues=cues,
            target_language=target_language,
        )
