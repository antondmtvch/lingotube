"""Translator interface: translates cue texts, never touches timing."""

from collections.abc import Sequence
from typing import Protocol

from lingotube.models import Cue


class Translator(Protocol):
    async def prepare(self) -> None:
        """Makes the translator ready (e.g. reads its key); raises if it cannot work."""
        ...

    async def translate(
        self,
        cues: Sequence[Cue],
        target_language: str,
    ) -> list[Cue]:
        """Returns cues with the same `id`, `start`, `end` and translated `text`."""
        ...
