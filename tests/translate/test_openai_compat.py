import asyncio
import json

import httpx
import pytest
import respx

from lingotube.config import TranslatorSettings
from lingotube.errors import AuthError, NetworkError, ValidationError
from lingotube.models import Cue
from lingotube.translate.openai_compat import OpenAICompatTranslator

BASE = "https://llm.example.test/v1"
URL = f"{BASE}/chat/completions"
KEY = "sk-secret-key-123"


def cues(n: int) -> list[Cue]:
    return [Cue(i, float(i), float(i) + 0.5, f"line {i}") for i in range(1, n + 1)]


def completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def user_lines(request: httpx.Request) -> list[list[str]]:
    body = json.loads(request.content)
    return [line.split("\t", 1) for line in body["messages"][1]["content"].split("\n")]


def echo_upper(request: httpx.Request) -> httpx.Response:
    return completion("\n".join(f"{n}\t{t.upper()}" for n, t in user_lines(request)))


def make(client: httpx.AsyncClient, batch_size: int = 40, base: str = BASE) -> OpenAICompatTranslator:
    return OpenAICompatTranslator(client, TranslatorSettings(base, "m1", "MY_KEY_ENV", batch_size), KEY)


@respx.mock
async def test_translates_in_batches_keeping_ids_and_times():
    route = respx.post(URL).mock(side_effect=echo_upper)
    source = cues(90)
    async with httpx.AsyncClient() as client:
        out = await make(client).translate(source, "ru")
    assert route.call_count == 3
    assert [(c.id, c.start, c.end) for c in out] == [(c.id, c.start, c.end) for c in source]
    assert [c.text for c in out] == [c.text.upper() for c in source]
    req = route.calls[0].request
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    body = json.loads(req.content)
    assert body["model"] == "m1" and body["temperature"] == 0
    assert "ru" in body["messages"][0]["content"]


@respx.mock
async def test_timecodes_not_sent_to_model():
    route = respx.post(URL).mock(side_effect=echo_upper)
    async with httpx.AsyncClient() as client:
        await make(client).translate(cues(3), "ru")
    raw = route.calls[0].request.content.decode()
    assert "start" not in raw and "0.5" not in raw
    assert json.loads(raw)["messages"][1]["content"] == "1\tline 1\n2\tline 2\n3\tline 3"


@respx.mock
async def test_count_mismatch_retries_batch_once_then_fails():
    route = respx.post(URL).mock(return_value=completion("\n".join(f"{i}\tx" for i in range(1, 40))))
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValidationError) as exc:
            await make(client).translate(cues(40), "ru")
    assert exc.value.exit_code == 7
    assert route.call_count == 2
    assert "1" in str(exc.value) and "40" in str(exc.value)


@respx.mock
async def test_mismatch_then_ok_succeeds():
    route = respx.post(URL).mock(side_effect=[completion("1\tonly"), echo_upper])
    async with httpx.AsyncClient() as client:
        out = await make(client).translate(cues(2), "ru")
    assert route.call_count == 2
    assert [c.text for c in out] == ["LINE 1", "LINE 2"]


@respx.mock
async def test_duplicate_or_empty_is_mismatch():
    route = respx.post(URL).mock(side_effect=[completion("1\ta\n1\tb"), completion("1\ta\n2\t  ")])
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValidationError):
            await make(client).translate(cues(2), "ru")
    assert route.call_count == 2


@respx.mock
@pytest.mark.parametrize("status,exc", [(401, AuthError), (403, AuthError), (500, NetworkError)])
async def test_api_key_in_header_not_in_error(status, exc):
    respx.post(URL).mock(return_value=httpx.Response(status, text=f"bad key {KEY}"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(exc) as e:
            await make(client).translate(cues(2), "ru")
    text = f"{e.value} {e.value.hint}"
    assert KEY not in text
    if exc is AuthError:
        assert "MY_KEY_ENV" in text


@respx.mock
async def test_transport_error_is_network_error_without_key():
    respx.post(URL).mock(side_effect=httpx.ConnectError(f"boom {KEY}"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(NetworkError) as e:
            await make(client).translate(cues(2), "ru")
    assert KEY not in str(e.value)
    assert e.value.__cause__ is None


@respx.mock
async def test_request_goes_only_to_base_url_and_carries_no_cookies():
    route = respx.post(URL).mock(side_effect=echo_upper)
    async with httpx.AsyncClient() as client:
        await make(client, base=BASE + "/").translate(cues(2), "ru")
    assert route.call_count == 1 and len(respx.calls) == 1
    req = route.calls[0].request
    assert req.url.host == "llm.example.test"
    assert "cookie" not in req.headers


@respx.mock
async def test_at_most_three_batches_in_flight():
    state = {"now": 0, "peak": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        return echo_upper(request)

    respx.post(URL).mock(side_effect=handler)
    async with httpx.AsyncClient() as client:
        out = await make(client, batch_size=1).translate(cues(10), "ru")
    assert state["peak"] == 3
    assert [c.id for c in out] == list(range(1, 11))
