"""Tests of the translator over an OpenAI-compatible API: batches, numbering, retries and secrets."""

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
    """Build ``n`` cues with the text ``line <id>``.

    Args:
        n: Number of cues.

    Returns:
        The cues.
    """
    return [
        Cue(
            id=i,
            start=float(i),
            end=float(i) + 0.5,
            text=f"line {i}",
        )
        for i in range(
            1,
            n + 1,
        )
    ]


def completion(content: str) -> httpx.Response:
    """Build a chat completion response with the given content.

    Args:
        content: Content of the answer.

    Returns:
        The HTTP response.
    """
    return httpx.Response(
        status_code=200,
        json={"choices": [{"message": {"content": content}}]},
    )


def user_lines(request: httpx.Request) -> list[list[str]]:
    """Read the numbered lines that a request sends to the model.

    Args:
        request: The HTTP request.

    Returns:
        The number and the text of each line.
    """
    body = json.loads(s=request.content)
    return [
        line.split(
            "\t",
            1,
        )
        for line in body["messages"][1]["content"].split("\n")
    ]


def echo_upper(request: httpx.Request) -> httpx.Response:
    """Answer a request with the same numbered lines, in upper case.

    Args:
        request: The HTTP request.

    Returns:
        The HTTP response.
    """
    return completion(content="\n".join(f"{n}\t{t.upper()}" for n, t in user_lines(request=request)))


def make(
    client: httpx.AsyncClient,
    batch_size: int = 40,
    base: str = BASE,
) -> OpenAICompatTranslator:
    """Build a translator for the test endpoint.

    Args:
        client: HTTP client.
        batch_size: Number of lines per request.
        base: Base URL of the endpoint.

    Returns:
        The translator.
    """
    return OpenAICompatTranslator(
        http=client,
        settings=TranslatorSettings(
            base_url=base,
            model="m1",
            api_key_env="MY_KEY_ENV",
            batch_size=batch_size,
        ),
        api_key=KEY,
    )


@respx.mock
async def test_translates_in_batches_keeping_ids_and_times():
    """Check that cues are translated in batches with their ids and times kept."""
    route = respx.post(url=URL).mock(side_effect=echo_upper)
    source = cues(n=90)
    async with httpx.AsyncClient() as client:
        out = await make(client=client).translate(
            cues=source,
            target_language="ru",
        )
    assert route.call_count == 3
    assert [(c.id, c.start, c.end) for c in out] == [(c.id, c.start, c.end) for c in source]
    assert [c.text for c in out] == [c.text.upper() for c in source]
    req = route.calls[0].request
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    body = json.loads(s=req.content)
    assert body["model"] == "m1" and body["temperature"] == 0
    assert "ru" in body["messages"][0]["content"]


@respx.mock
async def test_timecodes_not_sent_to_model():
    """Check that the timecodes are not sent to the model."""
    route = respx.post(url=URL).mock(side_effect=echo_upper)
    async with httpx.AsyncClient() as client:
        await make(client=client).translate(
            cues=cues(n=3),
            target_language="ru",
        )
    raw = route.calls[0].request.content.decode()
    assert "start" not in raw and "0.5" not in raw
    assert json.loads(s=raw)["messages"][1]["content"] == "1\tline 1\n2\tline 2\n3\tline 3"


@respx.mock
async def test_count_mismatch_retries_batch_once_then_fails():
    """Check that a batch with a wrong count is retried once and then fails."""
    route = respx.post(url=URL).mock(
        return_value=completion(
            content="\n".join(
                f"{i}\tx"
                for i in range(
                    1,
                    40,
                )
            )
        )
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(expected_exception=ValidationError) as exc:
            await make(client=client).translate(
                cues=cues(n=40),
                target_language="ru",
            )
    assert exc.value.exit_code == 7
    assert route.call_count == 2
    assert "1" in str(exc.value) and "40" in str(exc.value)


@respx.mock
async def test_mismatch_then_ok_succeeds():
    """Check that a batch that is correct on the second try succeeds."""
    route = respx.post(url=URL).mock(side_effect=[completion(content="1\tonly"), echo_upper])
    async with httpx.AsyncClient() as client:
        out = await make(client=client).translate(
            cues=cues(n=2),
            target_language="ru",
        )
    assert route.call_count == 2
    assert [c.text for c in out] == ["LINE 1", "LINE 2"]


@respx.mock
async def test_duplicate_or_empty_is_mismatch():
    """Check that duplicate or empty lines count as a mismatch."""
    route = respx.post(url=URL).mock(
        side_effect=[
            completion(content="1\ta\n1\tb"),
            completion(content="1\ta\n2\t  "),
        ]
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(expected_exception=ValidationError):
            await make(client=client).translate(
                cues=cues(n=2),
                target_language="ru",
            )
    assert route.call_count == 2


@respx.mock
@pytest.mark.parametrize(
    argnames="status,exc",
    argvalues=[(401, AuthError), (403, AuthError), (500, NetworkError)],
)
async def test_api_key_in_header_not_in_error(
    status,
    exc,
):
    """Check that the API key is in the header only and never in an error."""
    respx.post(url=URL).mock(
        return_value=httpx.Response(
            status_code=status,
            text=f"bad key {KEY}",
        )
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(expected_exception=exc) as e:
            await make(client=client).translate(
                cues=cues(n=2),
                target_language="ru",
            )
    text = f"{e.value} {e.value.hint}"
    assert KEY not in text
    if exc is AuthError:
        assert "MY_KEY_ENV" in text


@respx.mock
async def test_transport_error_is_network_error_without_key():
    """Check that a transport error becomes a network error without the key."""
    respx.post(url=URL).mock(side_effect=httpx.ConnectError(message=f"boom {KEY}"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(expected_exception=NetworkError) as e:
            await make(client=client).translate(
                cues=cues(n=2),
                target_language="ru",
            )
    assert KEY not in str(e.value)
    assert e.value.__cause__ is None


@respx.mock
async def test_request_goes_only_to_base_url_and_carries_no_cookies():
    """Check that requests go only to the base URL and carry no cookies."""
    route = respx.post(url=URL).mock(side_effect=echo_upper)
    async with httpx.AsyncClient() as client:
        await make(
            client=client,
            base=BASE + "/",
        ).translate(
            cues=cues(n=2),
            target_language="ru",
        )
    assert route.call_count == 1 and len(respx.calls) == 1
    req = route.calls[0].request
    assert req.url.host == "llm.example.test"
    assert "cookie" not in req.headers


@respx.mock
async def test_at_most_three_batches_in_flight():
    """Check that at most three batches are sent at the same time."""
    state = {"now": 0, "peak": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        state["now"] += 1
        state["peak"] = max(
            state["peak"],
            state["now"],
        )
        await asyncio.sleep(delay=0.01)
        state["now"] -= 1
        return echo_upper(request=request)

    respx.post(url=URL).mock(side_effect=handler)
    async with httpx.AsyncClient() as client:
        out = await make(
            client=client,
            batch_size=1,
        ).translate(
            cues=cues(n=10),
            target_language="ru",
        )
    assert state["peak"] == 3
    assert [c.id for c in out] == list(
        range(
            1,
            11,
        )
    )


@respx.mock
@pytest.mark.parametrize(
    argnames="answer",
    argvalues=[
        "1\tA\r\n2\tB\r\n3\tC",
        "\n1\tA\n\n2\tB\n\n3\tC\n\n",
        "  1\t A  \n\t2 \tB\t\n 3\tC  ",
        "1.\tA\n2) B\n3:C",
        "Here is the translation:\n```\n1\tA\n2\tB\n3\tC\n```",
    ],
)
async def test_lenient_response_formats(answer):
    """Check that the model answer is accepted in several lenient formats."""
    respx.post(url=URL).mock(return_value=completion(content=answer))
    async with httpx.AsyncClient() as client:
        out = await make(client=client).translate(
            cues=cues(n=3),
            target_language="ru",
        )
    assert [c.text for c in out] == ["A", "B", "C"]


@respx.mock
async def test_tab_and_line_separator_inside_text_preserved():
    """Check that tabs and line separators inside the text are preserved."""
    respx.post(url=URL).mock(return_value=completion(content="1\ta\tb c\n2\tz"))
    async with httpx.AsyncClient() as client:
        out = await make(client=client).translate(
            cues=cues(n=2),
            target_language="ru",
        )
    assert [c.text for c in out] == ["a\tb c", "z"]


@respx.mock
async def test_extra_number_is_still_mismatch():
    """Check that an extra number in the answer is still a mismatch."""
    route = respx.post(url=URL).mock(return_value=completion(content="1\ta\n2\tb\n3\tc"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(expected_exception=ValidationError):
            await make(client=client).translate(
                cues=cues(n=2),
                target_language="ru",
            )
    assert route.call_count == 2


@respx.mock
async def test_redirect_is_refused():
    """Check that a redirect from the model endpoint is refused."""
    target = respx.get(url="https://evil.example.test/x").mock(return_value=httpx.Response(status_code=200))
    respx.post(url=URL).mock(
        return_value=httpx.Response(
            status_code=302,
            headers={"Location": "https://evil.example.test/x"},
        )
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(expected_exception=NetworkError) as e:
            await make(client=client).translate(
                cues=cues(n=2),
                target_language="ru",
            )
    assert "evil.example.test" not in str(e.value)
    assert not target.called


async def test_invalid_base_url_is_validation_error():
    """Check that an invalid base URL is a validation error."""
    async with httpx.AsyncClient() as client:
        with pytest.raises(expected_exception=ValidationError) as e:
            await make(
                client=client,
                base="http://user:pw@exa mple:bad/v1",
            ).translate(
                cues=cues(n=2),
                target_language="ru",
            )
    assert e.value.exit_code == 7
    assert "translator.base_url" in f"{e.value} {e.value.hint}"
    assert "pw" not in f"{e.value} {e.value.hint}"


@respx.mock
async def test_line_without_number_is_appended_to_previous_item():
    """Check that a line without a number is added to the previous item."""
    respx.post(url=URL).mock(return_value=completion(content="1\tA\nB\n2\tC"))
    async with httpx.AsyncClient() as client:
        out = await make(client=client).translate(
            cues=cues(n=2),
            target_language="ru",
        )
    assert "A" in out[0].text and "B" in out[0].text
    assert out[1].text == "C"


@respx.mock
async def test_trailing_prose_after_last_item_is_dropped():
    """Check that prose after the last item is dropped."""
    respx.post(url=URL).mock(return_value=completion(content="1\tA\n2\tC\nHope this helps!"))
    async with httpx.AsyncClient() as client:
        out = await make(client=client).translate(
            cues=cues(n=2),
            target_language="ru",
        )
    assert out[0].text == "A"
    assert out[1].text == "C"
