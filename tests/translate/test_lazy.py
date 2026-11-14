"""Tests of the lazy translator: the real translator is built only when it is needed."""

import pytest

from lingotube.models import Cue
from lingotube.translate.lazy import LazyTranslator

CUES = [
    Cue(
        id=1,
        start=0.0,
        end=1.0,
        text="a",
    )
]


class Upper:
    """Translator that makes the text upper case."""

    async def translate(
        self,
        cues,
        target_language,
    ):
        """Return the cues with their text in upper case.

        Args:
            cues: Cues to translate.
            target_language: Language to translate to. Not used.

        Returns:
            The translated cues.
        """
        return [
            Cue(
                id=c.id,
                start=c.start,
                end=c.end,
                text=c.text.upper() + target_language,
            )
            for c in cues
        ]


async def test_factory_runs_only_on_translate():
    """Check that the factory runs only when a translation is requested."""
    calls: list[int] = []

    def factory():
        calls.append(1)
        return Upper()

    lazy = LazyTranslator(factory=factory)
    assert calls == []
    out = await lazy.translate(
        cues=CUES,
        target_language="ru",
    )
    assert calls == [1] and out[0].text == "Aru"


async def test_awaitable_factory_is_supported():
    """Check that a factory that returns an awaitable is supported."""

    async def factory():
        return Upper()

    out = await LazyTranslator(factory=factory).translate(
        cues=CUES,
        target_language="de",
    )
    assert out[0].text == "Ade"


async def test_prepare_builds_the_translator_once_and_surfaces_its_error():
    """Check that prepare builds the translator once and passes on its error."""
    calls: list[int] = []

    def factory():
        calls.append(1)
        return Upper()

    lazy = LazyTranslator(factory=factory)
    await lazy.prepare()
    out = await lazy.translate(
        cues=CUES,
        target_language="ru",
    )
    assert calls == [1] and out[0].text == "Aru"

    def broken():
        raise RuntimeError("no key")

    with pytest.raises(expected_exception=RuntimeError):
        await LazyTranslator(factory=broken).prepare()
