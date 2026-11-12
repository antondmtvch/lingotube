"""Translator over an OpenAI-compatible `/chat/completions` endpoint.

Cues go in numbered batches ("n<TAB>text"); timecodes are never sent. The answer
is mapped back by number and must contain every number exactly once with
non-empty text, otherwise the batch is asked once more and then fails. The key
travels only in the Authorization header and is masked in every error; no cookies
are ever sent (the HTTP client given here is the translator's own).
"""

import asyncio
import re
from collections.abc import Sequence
from dataclasses import replace

import httpx

from lingotube.config import TranslatorSettings
from lingotube.errors import AuthError, NetworkError, ValidationError
from lingotube.models import Cue
from lingotube.prompts import load_prompt
from lingotube.redact import redact

MAX_IN_FLIGHT = 3
ATTEMPTS = 2  # one retry of a mismatched batch
_LINE = re.compile(r"^\s*(\d+)(?:[\t ]+|[.):]\s*)(.*?)\s*$")


class OpenAICompatTranslator:
    def __init__(
        self, http: httpx.AsyncClient, settings: TranslatorSettings, api_key: str
    ) -> None:
        self._http = http
        self._settings = settings
        self._api_key = api_key

    async def translate(self, cues: Sequence[Cue], target_language: str) -> list[Cue]:
        size = self._settings.batch_size
        batches = [list(cues[i : i + size]) for i in range(0, len(cues), size)]
        gate = asyncio.Semaphore(MAX_IN_FLIGHT)

        async def run(batch: list[Cue]) -> list[Cue]:
            async with gate:
                return await self._translate_batch(batch, target_language)

        tasks = [asyncio.create_task(run(b)) for b in batches]
        try:
            results = await asyncio.gather(*tasks)
        except BaseException:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return [c for batch in results for c in batch]

    async def _translate_batch(self, batch: list[Cue], language: str) -> list[Cue]:
        system = load_prompt("translate_batch", language=language)
        user = "\n".join(
            f"{n}\t{' '.join(c.text.split())}" for n, c in enumerate(batch, 1)
        )
        for _ in range(ATTEMPTS):
            texts = _parse(await self._complete(system, user), len(batch))
            if texts is not None:
                return [replace(c, text=t) for c, t in zip(batch, texts)]
        raise ValidationError(
            f"Модель вернула перевод реплик {batch[0].id}–{batch[-1].id}, не совпадающий по "
            f"числу или номерам строк (дважды).",
            hint="Уменьшите translator.batch_size или проверьте модель.",
        )

    async def _complete(self, system: str, user: str) -> str:
        url = self._settings.base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": self._settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        try:
            response = await self._http.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {self._api_key}"},
                follow_redirects=False,
            )
        except httpx.InvalidURL:
            raise ValidationError(
                "Некорректный адрес модели перевода.",
                hint="Проверьте настройку translator.base_url.",
            ) from None
        except httpx.HTTPError as e:
            raise NetworkError(
                redact(
                    f"Не удалось обратиться к модели перевода: {type(e).__name__}: {e}",
                    [self._api_key],
                )
            ) from None
        status = response.status_code
        if status in (401, 403):
            raise AuthError(
                f"Модель перевода отклонила ключ (HTTP {status}).",
                hint=f"Проверьте ключ в переменной окружения {self._settings.api_key_env}.",
            ) from None
        if 300 <= status < 400:
            raise NetworkError(
                "Модель перевода ответила перенаправлением; перенаправления не выполняются."
            ) from None
        if status >= 400:
            raise NetworkError(
                redact(
                    f"Модель перевода вернула ошибку HTTP {status}.", [self._api_key]
                )
            ) from None
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except ValueError, KeyError, IndexError, TypeError:
            return ""
        return content if isinstance(content, str) else ""


def _parse(answer: str, count: int) -> list[str] | None:
    """Texts in batch order, or None when numbers/count/text do not match."""
    found: dict[int, str] = {}
    for line in answer.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        m = _LINE.match(line)
        if m is None:
            continue  # blank lines, preamble, code fences
        number, text = int(m.group(1)), m.group(2)
        if number in found or not text:
            return None
        found[number] = text
    if set(found) != set(range(1, count + 1)):
        return None
    return [found[n] for n in range(1, count + 1)]
