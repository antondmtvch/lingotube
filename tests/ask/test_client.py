"""Tests of the Ask chat client: sessions, retries, pacing, errors and secrets."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from lingotube.ask.client import Pacer, YouTubeAskClient
from lingotube.auth import Credentials, sapisidhash
from lingotube.errors import AuthError, ChatUnavailableError, NetworkError

FIX = Path(__file__).parent.parent / "fixtures"
YT = "https://www.youtube.com"
WATCH = f"{YT}/watch"
NEXT = f"{YT}/youtubei/v1/next"
PANEL = f"{YT}/youtubei/v1/get_panel"
SAPISID = "SAPISID_SECRET_VALUE"
SID = "SID_SECRET_VALUE"
NOW = 1700000000.0
VIDEO = "-n5MqamatXE"


def fixture_json(name: str) -> dict:
    """Read a JSON fixture file as a dict."""
    return json.loads(s=(FIX / name).read_text(encoding="utf-8"))


def page_html() -> str:
    """Read the saved watch page fixture."""
    return (FIX / "watch_page.html").read_text(encoding="utf-8")


class FakeCookies:
    """Cookie source that returns fixed credentials."""

    async def load(self) -> Credentials:
        """Return fixed credentials with a SAPISID cookie."""
        return Credentials(cookies={"SAPISID": SAPISID, "SID": SID})


class FakeTime:
    """Fake clock and sleep that advance time without waiting."""

    def __init__(self) -> None:
        """Start the fake clock at zero."""
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        """Return the fake current time."""
        return self.now

    async def sleep(self, seconds: float) -> None:
        """Advance the fake time and remember the length of the sleep."""
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def ftime() -> FakeTime:
    """Provide a fresh fake clock."""
    return FakeTime()


@pytest.fixture
def mock():
    """Provide a respx router that fails on any request it does not know."""
    with respx.mock(
        assert_all_mocked=True,
        assert_all_called=False,
    ) as router:
        yield router


@pytest.fixture
async def http():
    """Provide an HTTP client that does not follow redirects."""
    async with httpx.AsyncClient(follow_redirects=False) as client:
        yield client


def make_client(
    http: httpx.AsyncClient,
    ftime: FakeTime,
    min_interval: float = 5.0,
) -> YouTubeAskClient:
    """Build a chat client that uses the fake clock and the fake cookies."""
    pacer = Pacer(
        min_interval=min_interval,
        sleep=ftime.sleep,
        clock=ftime.clock,
    )
    return YouTubeAskClient(
        http=http,
        cookies=FakeCookies(),
        pacer=pacer,
        max_retries=2,
        wall_clock=lambda: NOW,
    )


def route_page(
    mock,
    nxt: str = "next_eligible.json",
) -> None:
    """Route the watch page and the next request to the saved fixtures."""
    mock.get(url=WATCH).mock(
        return_value=httpx.Response(
            status_code=200,
            text=page_html(),
        )
    )
    mock.post(url=NEXT).mock(
        return_value=httpx.Response(
            status_code=200,
            json=fixture_json(name=nxt),
        )
    )


def answer_response() -> httpx.Response:
    """Build a get_panel response that holds an answer."""
    return httpx.Response(
        status_code=200,
        json=fixture_json(name="get_panel_answer.json"),
    )


async def test_open_and_ask_happy_path(
    mock,
    http,
    ftime,
):
    """Check that a chat opens and an answer is returned."""
    route_page(mock=mock)
    panel = mock.post(url=PANEL).mock(return_value=answer_response())
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    assert session.info.video_id == "dQw4w9WgXcQ"
    assert session.info.language == "ru"
    answer = await session.ask(prompt="дай транскрипцию")
    assert "(0:02) Всем привет" in answer
    sent = json.loads(s=panel.calls.last.request.content)
    assert sent["continuation"] == "FAKE_CONTINUATION_1"
    assert sent["context"]["clickTracking"]["clickTrackingParams"] == "FAKE_CTP_1"
    assert sent["formData"]["inputComposerFormData"]["userInputText"] == "дай транскрипцию"
    assert sent["formData"]["inputComposerFormData"]["clientMessageId"] == "youchat-1700000000000"
    req = panel.calls.last.request
    assert req.headers["Authorization"] == sapisidhash(
        sapisid=SAPISID,
        origin=YT,
        now=int(NOW),
    )
    assert req.headers["Origin"] == YT
    assert f"SAPISID={SAPISID}" in req.headers["Cookie"]
    watch = mock.calls[0].request
    assert watch.url.params["v"] == VIDEO
    assert "Authorization" not in watch.headers
    assert json.loads(s=mock.calls[1].request.content)["videoId"] == VIDEO


async def test_fresh_send_command_used_for_next_ask(
    mock,
    http,
    ftime,
):
    """Check that the send command from the last answer is used for the next question."""
    route_page(mock=mock)
    fresh = fixture_json(name="get_panel_answer.json")
    fresh["extra"] = {
        "sendUserQueryCommand": {
            "innertubeCommand": {
                "clickTrackingParams": "CTP_NEW",
                "continuationCommand": {"token": "TOK_NEW"},
            }
        }
    }
    panel = mock.post(url=PANEL).mock(
        side_effect=[
            httpx.Response(
                status_code=200,
                json=fresh,
            ),
            answer_response(),
        ]
    )
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    await session.ask(prompt="a")
    await session.ask(prompt="b")
    first, second = (json.loads(s=c.request.content) for c in panel.calls)
    assert first["continuation"] == "FAKE_CONTINUATION_1"
    assert second["continuation"] == "TOK_NEW"


async def test_command_reused_when_answer_has_none(
    mock,
    http,
    ftime,
):
    """Check that the previous send command is reused when the answer has none."""
    route_page(mock=mock)
    panel = mock.post(url=PANEL).mock(return_value=answer_response())
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    await session.ask(prompt="a")
    await session.ask(prompt="b")
    assert all(json.loads(s=c.request.content)["continuation"] == "FAKE_CONTINUATION_1" for c in panel.calls)


async def test_empty_initial_get_panel_fallback(
    mock,
    http,
    ftime,
):
    """Check that the chat panel is requested again when the first get_panel is empty."""
    nxt = fixture_json(name="next_no_chat.json")
    nxt["engagementPanels"] = [
        {
            "engagementPanelSectionListRenderer": {
                "panelIdentifier": "PAyouchat",
                "content": {"continuationCommand": {"token": "PANEL_TOK"}},
            }
        }
    ]
    mock.get(url=WATCH).mock(
        return_value=httpx.Response(
            status_code=200,
            text=page_html(),
        )
    )
    mock.post(url=NEXT).mock(
        return_value=httpx.Response(
            status_code=200,
            json=nxt,
        )
    )
    initial = {
        "footer": {
            "sendUserQueryCommand": {
                "innertubeCommand": {
                    "clickTrackingParams": "CTP_I",
                    "continuationCommand": {"token": "TOK_I"},
                }
            }
        }
    }
    panel = mock.post(url=PANEL).mock(
        side_effect=[
            httpx.Response(
                status_code=200,
                json=initial,
            ),
            answer_response(),
        ]
    )
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    await session.ask(prompt="q")
    first, second = (json.loads(s=c.request.content) for c in panel.calls)
    assert first["continuation"] == "PANEL_TOK" and "formData" not in first
    assert second["continuation"] == "TOK_I"


async def test_signed_out_is_auth_error(
    mock,
    http,
    ftime,
):
    """Check that a signed-out next response raises AuthError."""
    route_page(
        mock=mock,
        nxt="next_signed_out.json",
    )
    with pytest.raises(expected_exception=AuthError) as e:
        await make_client(
            http=http,
            ftime=ftime,
        ).open(video_id=VIDEO)
    assert e.value.exit_code == 4
    assert e.value.hint and "инкогнито" in e.value.hint


async def test_signed_out_watch_page_is_auth_error(
    mock,
    http,
    ftime,
):
    """Check that a signed-out watch page raises AuthError."""
    mock.get(url=WATCH).mock(
        return_value=httpx.Response(
            status_code=200,
            text=page_html().replace(
                '"LOGGED_IN":true',
                '"LOGGED_IN":false',
            ),
        )
    )
    nxt = mock.post(url=NEXT).mock(
        return_value=httpx.Response(
            status_code=200,
            json=fixture_json(name="next_eligible.json"),
        )
    )
    with pytest.raises(expected_exception=AuthError):
        await make_client(
            http=http,
            ftime=ftime,
        ).open(video_id=VIDEO)
    assert not nxt.called


async def test_no_panel_is_chat_unavailable(
    mock,
    http,
    ftime,
):
    """Check that a missing chat panel raises ChatUnavailableError."""
    route_page(
        mock=mock,
        nxt="next_no_chat.json",
    )
    with pytest.raises(expected_exception=ChatUnavailableError) as e:
        await make_client(
            http=http,
            ftime=ftime,
        ).open(video_id=VIDEO)
    assert e.value.exit_code == 3


async def test_requests_only_go_to_youtube(
    mock,
    http,
    ftime,
):
    """Check that every request goes to youtube.com."""
    route_page(mock=mock)
    mock.post(url=PANEL).mock(return_value=answer_response())
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    await session.ask(prompt="q")
    assert len(mock.calls) == 3
    for call in mock.calls:
        assert call.request.url.scheme == "https"
        assert call.request.url.host == "www.youtube.com"


async def test_redirect_off_site_not_followed(
    mock,
    http,
    ftime,
):
    """Check that a redirect to another site is not followed."""
    mock.get(url=WATCH).mock(
        return_value=httpx.Response(
            status_code=302,
            headers={"Location": "https://example.com/steal"},
        )
    )
    evil = mock.route(host="example.com").mock(
        return_value=httpx.Response(
            status_code=200,
            text="gotcha",
        )
    )
    with pytest.raises(expected_exception=NetworkError) as e:
        await make_client(
            http=http,
            ftime=ftime,
        ).open(video_id=VIDEO)
    assert e.value.exit_code == 6
    assert not evil.called
    assert all(c.request.url.host == "www.youtube.com" for c in mock.calls)


async def test_redirect_not_followed_even_if_client_follows(
    mock,
    ftime,
):
    """Check that redirects are not followed even if the HTTP client would follow them."""
    mock.get(url=WATCH).mock(
        return_value=httpx.Response(
            status_code=302,
            headers={"Location": "https://example.com/steal"},
        )
    )
    evil = mock.route(host="example.com").mock(
        return_value=httpx.Response(
            status_code=200,
            text="gotcha",
        )
    )
    async with httpx.AsyncClient(follow_redirects=True) as careless:
        with pytest.raises(expected_exception=NetworkError):
            await make_client(
                http=careless,
                ftime=ftime,
            ).open(video_id=VIDEO)
    assert not evil.called


async def test_retries_then_network_error(
    mock,
    http,
    ftime,
):
    """Check that repeated server errors are retried and then raise NetworkError."""
    route_page(mock=mock)
    panel = mock.post(url=PANEL).mock(return_value=httpx.Response(status_code=500))
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    with pytest.raises(expected_exception=NetworkError) as e:
        await session.ask(prompt="q")
    assert e.value.exit_code == 6
    assert panel.call_count == 1 + 2


async def test_transport_error_retried_then_network_error(
    mock,
    http,
    ftime,
):
    """Check that transport errors are retried and then raise NetworkError."""
    route_page(mock=mock)
    panel = mock.post(url=PANEL).mock(side_effect=httpx.ReadTimeout(message="slow"))
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    with pytest.raises(expected_exception=NetworkError) as e:
        await session.ask(prompt="q")
    assert "ReadTimeout" in str(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__
    assert panel.call_count == 3


async def test_retry_succeeds_second_time(
    mock,
    http,
    ftime,
):
    """Check that a request that succeeds on the second try is accepted."""
    route_page(mock=mock)
    mock.post(url=PANEL).mock(side_effect=[httpx.Response(status_code=500), answer_response()])
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    assert "(0:" in await session.ask(prompt="q")


async def test_pacer_called_before_each_ask(
    mock,
    http,
    ftime,
):
    """Check that the pacer is consulted before every question."""
    route_page(mock=mock)
    starts: list[float] = []

    def on_panel(request: httpx.Request) -> httpx.Response:
        starts.append(ftime.now)
        return answer_response()

    mock.post(url=PANEL).mock(side_effect=on_panel)
    session = await make_client(
        http=http,
        ftime=ftime,
        min_interval=5.0,
    ).open(video_id=VIDEO)
    await session.ask(prompt="a")
    await session.ask(prompt="b")
    assert len(starts) == 2
    assert starts[1] - starts[0] >= 5.0
    assert ftime.sleeps and all(s > 0 for s in ftime.sleeps)


async def test_pacer_spaces_every_request(
    mock,
    http,
    ftime,
):
    """Check that consecutive requests are spaced by the minimum interval."""
    starts: list[float] = []

    def stamp(response: httpx.Response):
        def handler(request: httpx.Request) -> httpx.Response:
            starts.append(ftime.now)
            return response

        return handler

    mock.get(url=WATCH).mock(
        side_effect=stamp(
            response=httpx.Response(
                status_code=200,
                text=page_html(),
            )
        )
    )
    mock.post(url=NEXT).mock(
        side_effect=stamp(
            response=httpx.Response(
                status_code=200,
                json=fixture_json(name="next_eligible.json"),
            )
        )
    )
    mock.post(url=PANEL).mock(side_effect=stamp(response=answer_response()))
    session = await make_client(
        http=http,
        ftime=ftime,
        min_interval=5.0,
    ).open(video_id=VIDEO)
    await session.ask(prompt="a")
    assert len(starts) == 3
    assert all(
        b - a >= 5.0
        for a, b in zip(
            starts,
            starts[1:],
            strict=False,
        )
    )


async def test_pacer_no_wait_after_long_gap():
    """Check that no wait happens after a gap longer than the minimum interval."""
    ft = FakeTime()
    pacer = Pacer(
        min_interval=5.0,
        sleep=ft.sleep,
        clock=ft.clock,
    )
    await pacer.wait()
    ft.now += 10
    await pacer.wait()
    assert ft.sleeps == []
    await pacer.wait()
    assert ft.sleeps == [5.0]


async def test_error_message_has_no_secrets(
    mock,
    http,
    ftime,
):
    """Check that error messages never contain the cookies or tokens."""
    route_page(mock=mock)
    header = sapisidhash(
        sapisid=SAPISID,
        origin=YT,
        now=int(NOW),
    )
    digest = header.split(
        " ",
        1,
    )[1]
    leak = f"boom {SAPISID} {SID} FAKE_CONTINUATION_1 FAKE_CTP_1 {header} {digest}"
    mock.post(url=PANEL).mock(side_effect=httpx.ConnectError(message=leak))
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    with pytest.raises(expected_exception=NetworkError) as e:
        await session.ask(prompt="q")
    text = str(e.value) + (e.value.hint or "")
    for secret in (
        SAPISID,
        SID,
        "FAKE_CONTINUATION_1",
        "FAKE_CTP_1",
        header,
        header.split(
            "_",
            1,
        )[1],
    ):
        assert secret not in text
    assert "ConnectError" in text and "***" in text


async def test_http_401_is_auth_error(
    mock,
    http,
    ftime,
):
    """Check that HTTP 401 raises AuthError."""
    mock.get(url=WATCH).mock(
        return_value=httpx.Response(
            status_code=200,
            text=page_html(),
        )
    )
    nxt = mock.post(url=NEXT).mock(return_value=httpx.Response(status_code=401))
    with pytest.raises(expected_exception=AuthError) as e:
        await make_client(
            http=http,
            ftime=ftime,
        ).open(video_id=VIDEO)
    assert e.value.exit_code == 4
    assert nxt.call_count == 1


async def test_other_4xx_is_network_error_without_retry(
    mock,
    http,
    ftime,
):
    """Check that other client errors raise NetworkError without a retry."""
    route_page(mock=mock)
    panel = mock.post(url=PANEL).mock(return_value=httpx.Response(status_code=400))
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    with pytest.raises(expected_exception=NetworkError):
        await session.ask(prompt="q")
    assert panel.call_count == 1


async def test_non_json_next_is_network_error(
    mock,
    http,
    ftime,
):
    """Check that a non-JSON next response raises NetworkError."""
    mock.get(url=WATCH).mock(
        return_value=httpx.Response(
            status_code=200,
            text=page_html(),
        )
    )
    mock.post(url=NEXT).mock(
        return_value=httpx.Response(
            status_code=200,
            text="<html>oops</html>",
        )
    )
    with pytest.raises(expected_exception=NetworkError):
        await make_client(
            http=http,
            ftime=ftime,
        ).open(video_id=VIDEO)


async def test_reprs_hide_secrets(
    mock,
    http,
    ftime,
):
    """Check that the representations of the client and session hide the secrets."""
    route_page(mock=mock)
    client = make_client(
        http=http,
        ftime=ftime,
    )
    session = await client.open(video_id=VIDEO)
    for text in (repr(client), repr(session)):
        for secret in (SAPISID, SID, "FAKE_CONTINUATION_1", "FAKE_CTP_1"):
            assert secret not in text


async def test_short_cookie_values_are_not_masked(
    mock,
    http,
    ftime,
):
    """Check that very short cookie values are not masked, so that the text stays readable."""

    class ShortCookies:
        async def load(self) -> Credentials:
            return Credentials(
                cookies={
                    "SAPISID": SAPISID,
                    "SID": SID,
                    "PREF": "1",
                    "HSID": "abcd",
                }
            )

    route_page(mock=mock)
    mock.post(url=PANEL).mock(side_effect=httpx.ConnectError(message="HTTP 2019 abcd"))
    client = YouTubeAskClient(
        http=http,
        cookies=ShortCookies(),
        pacer=Pacer(
            min_interval=5.0,
            sleep=ftime.sleep,
            clock=ftime.clock,
        ),
        max_retries=2,
        wall_clock=lambda: NOW,
    )
    session = await client.open(video_id=VIDEO)
    with pytest.raises(expected_exception=NetworkError) as e:
        await session.ask(prompt="q")
    assert "HTTP 2019" in str(e.value)
    assert "abcd" not in str(e.value)


async def test_exhausted_retries_error_has_no_chained_cause(
    mock,
    http,
    ftime,
):
    """Check that the error after exhausted retries has no chained exception."""
    route_page(mock=mock)
    mock.post(url=PANEL).mock(return_value=httpx.Response(status_code=500))
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    with pytest.raises(expected_exception=NetworkError) as e:
        await session.ask(prompt="q")
    assert e.value.__cause__ is None and e.value.__suppress_context__


async def test_non_transport_http_error_has_no_chained_cause(
    mock,
    http,
    ftime,
):
    """Check that a non-transport HTTP error has no chained exception."""
    route_page(mock=mock)
    mock.post(url=PANEL).mock(side_effect=httpx.TooManyRedirects(message=f"loop {SAPISID}"))
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    with pytest.raises(expected_exception=NetworkError) as e:
        await session.ask(prompt="q")
    assert e.value.__cause__ is None and e.value.__suppress_context__
    assert SAPISID not in str(e.value) and "***" in str(e.value)


async def test_http_403_is_auth_error_and_leaks_nothing(
    mock,
    http,
    ftime,
):
    """Check that HTTP 403 raises AuthError and leaks no secret."""
    route_page(mock=mock)
    panel = mock.post(url=PANEL).mock(
        return_value=httpx.Response(
            status_code=403,
            text=f"denied {SAPISID} {SID}",
            headers={"x-echo": SAPISID},
        )
    )
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    with pytest.raises(expected_exception=AuthError) as e:
        await session.ask(prompt="q")
    assert e.value.exit_code == 4
    assert "403" in str(e.value)
    text = str(e.value) + (e.value.hint or "")
    assert SAPISID not in text and SID not in text
    assert panel.call_count == 1


async def test_http_429_is_retried_paced_and_leaks_nothing(
    mock,
    http,
    ftime,
):
    """Check that HTTP 429 is retried with pacing and leaks no secret."""
    route_page(mock=mock)
    starts: list[float] = []

    def on_panel(request: httpx.Request) -> httpx.Response:
        starts.append(ftime.now)
        return httpx.Response(
            status_code=429,
            text=f"slow down {SAPISID} {SID}",
        )

    mock.post(url=PANEL).mock(side_effect=on_panel)
    session = await make_client(
        http=http,
        ftime=ftime,
        min_interval=5.0,
    ).open(video_id=VIDEO)
    with pytest.raises(expected_exception=NetworkError) as e:
        await session.ask(prompt="q")
    assert e.value.exit_code == 6
    assert "429" in str(e.value)
    text = str(e.value) + (e.value.hint or "")
    assert SAPISID not in text and SID not in text
    assert len(starts) == 3
    assert all(b - a >= 5.0 for a, b in zip(starts, starts[1:], strict=False))
