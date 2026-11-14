"""Translator interface: translates cue texts, never touches timing."""

from collections.abc import Sequence
from typing import Protocol

from lingotube.models import Cue


class Translator(Protocol):
    """Interface of a translator: it translates cue texts and never touches the timing."""

    async def prepare(self) -> None:
        """Make the translator ready, for example by reading its key.

        Raises:
            AuthError: If the translator cannot work, for example because the API key is
                missing. The error comes before any slow work starts.
        """
        ...

    async def translate(
        self,
        cues: Sequence[Cue],
        target_language: str,
    ) -> list[Cue]:
        """Translate cue texts into the target language.

        Args:
            cues: Cues to translate.
            target_language: Language code of the result.

        Returns:
            Cues with the same ``id``, ``start`` and ``end``, and translated ``text``.
        """
        ...
