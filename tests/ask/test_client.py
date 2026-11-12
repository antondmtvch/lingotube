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
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def page_html() -> str:
    return (FIX / "watch_page.html").read_text(encoding="utf-8")


class FakeCookies:
    async def load(self) -> Credentials:
        return Credentials({"SAPISID": SAPISID, "SID": SID})


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def ftime() -> FakeTime:
    return FakeTime()


@pytest.fixture
def mock():
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


@pytest.fixture
async def http():
    async with httpx.AsyncClient(follow_redirects=False) as client:
        yield client


def make_client(
    http: httpx.AsyncClient, ftime: FakeTime, min_interval: float = 5.0
) -> YouTubeAskClient:
    pacer = Pacer(min_interval, sleep=ftime.sleep, clock=ftime.clock)
    return YouTubeAskClient(
        http, FakeCookies(), pacer, max_retries=2, wall_clock=lambda: NOW
    )


def route_page(mock, nxt: str = "next_eligible.json") -> None:
    mock.get(WATCH).mock(return_value=httpx.Response(200, text=page_html()))
    mock.post(NEXT).mock(return_value=httpx.Response(200, json=fixture_json(nxt)))


def answer_response() -> httpx.Response:
    return httpx.Response(200, json=fixture_json("get_panel_answer.json"))


async def test_open_and_ask_happy_path(mock, http, ftime):
    route_page(mock)
    panel = mock.post(PANEL).mock(return_value=answer_response())
    session = await make_client(http, ftime).open(VIDEO)
    assert session.info.video_id == "dQw4w9WgXcQ"
    assert session.info.language == "ru"
    answer = await session.ask("дай транскрипцию")
    assert "(0:02) Всем привет" in answer
    sent = json.loads(panel.calls.last.request.content)
    assert sent["continuation"] == "FAKE_CONTINUATION_1"
    assert sent["context"]["clickTracking"]["clickTrackingParams"] == "FAKE_CTP_1"
    assert (
        sent["formData"]["inputComposerFormData"]["userInputText"] == "дай транскрипцию"
    )
    assert (
        sent["formData"]["inputComposerFormData"]["clientMessageId"]
        == "youchat-1700000000000"
    )
    req = panel.calls.last.request
    assert req.headers["Authorization"] == sapisidhash(SAPISID, YT, int(NOW))
    assert req.headers["Origin"] == YT
    assert f"SAPISID={SAPISID}" in req.headers["Cookie"]
    watch = mock.calls[0].request
    assert watch.url.params["v"] == VIDEO
    assert "Authorization" not in watch.headers
    assert json.loads(mock.calls[1].request.content)["videoId"] == VIDEO


async def test_fresh_send_command_used_for_next_ask(mock, http, ftime):
    route_page(mock)
    fresh = fixture_json("get_panel_answer.json")
    fresh["extra"] = {
        "sendUserQueryCommand": {
            "innertubeCommand": {
                "clickTrackingParams": "CTP_NEW",
                "continuationCommand": {"token": "TOK_NEW"},
            }
        }
    }
    panel = mock.post(PANEL).mock(
        side_effect=[httpx.Response(200, json=fresh), answer_response()]
    )
    session = await make_client(http, ftime).open(VIDEO)
    await session.ask("a")
    await session.ask("b")
    first, second = (json.loads(c.request.content) for c in panel.calls)
    assert first["continuation"] == "FAKE_CONTINUATION_1"
    assert second["continuation"] == "TOK_NEW"


async def test_command_reused_when_answer_has_none(mock, http, ftime):
    route_page(mock)
    panel = mock.post(PANEL).mock(return_value=answer_response())
    session = await make_client(http, ftime).open(VIDEO)
    await session.ask("a")
    await session.ask("b")
    assert all(
        json.loads(c.request.content)["continuation"] == "FAKE_CONTINUATION_1"
        for c in panel.calls
    )


async def test_empty_initial_get_panel_fallback(mock, http, ftime):
    nxt = fixture_json("next_no_chat.json")
    nxt["engagementPanels"] = [
        {
            "engagementPanelSectionListRenderer": {
                "panelIdentifier": "PAyouchat",
                "content": {"continuationCommand": {"token": "PANEL_TOK"}},
            }
        }
    ]
    mock.get(WATCH).mock(return_value=httpx.Response(200, text=page_html()))
    mock.post(NEXT).mock(return_value=httpx.Response(200, json=nxt))
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
    panel = mock.post(PANEL).mock(
        side_effect=[httpx.Response(200, json=initial), answer_response()]
    )
    session = await make_client(http, ftime).open(VIDEO)
    await session.ask("q")
    first, second = (json.loads(c.request.content) for c in panel.calls)
    assert first["continuation"] == "PANEL_TOK" and "formData" not in first
    assert second["continuation"] == "TOK_I"


async def test_signed_out_is_auth_error(mock, http, ftime):
    route_page(mock, "next_signed_out.json")
    with pytest.raises(AuthError) as e:
        await make_client(http, ftime).open(VIDEO)
    assert e.value.exit_code == 4
    assert e.value.hint and "инкогнито" in e.value.hint


async def test_signed_out_watch_page_is_auth_error(mock, http, ftime):
    mock.get(WATCH).mock(
        return_value=httpx.Response(
            200, text=page_html().replace('"LOGGED_IN":true', '"LOGGED_IN":false')
        )
    )
    nxt = mock.post(NEXT).mock(
        return_value=httpx.Response(200, json=fixture_json("next_eligible.json"))
    )
    with pytest.raises(AuthError):
        await make_client(http, ftime).open(VIDEO)
    assert not nxt.called


async def test_no_panel_is_chat_unavailable(mock, http, ftime):
    route_page(mock, "next_no_chat.json")
    with pytest.raises(ChatUnavailableError) as e:
        await make_client(http, ftime).open(VIDEO)
    assert e.value.exit_code == 3


async def test_requests_only_go_to_youtube(mock, http, ftime):
    route_page(mock)
    mock.post(PANEL).mock(return_value=answer_response())
    session = await make_client(http, ftime).open(VIDEO)
    await session.ask("q")
    assert len(mock.calls) == 3
    for call in mock.calls:
        assert call.request.url.scheme == "https"
        assert call.request.url.host == "www.youtube.com"


async def test_redirect_off_site_not_followed(mock, http, ftime):
    mock.get(WATCH).mock(
        return_value=httpx.Response(
            302, headers={"Location": "https://example.com/steal"}
        )
    )
    evil = mock.route(host="example.com").mock(
        return_value=httpx.Response(200, text="gotcha")
    )
    with pytest.raises(NetworkError) as e:
        await make_client(http, ftime).open(VIDEO)
    assert e.value.exit_code == 6
    assert not evil.called
    assert all(c.request.url.host == "www.youtube.com" for c in mock.calls)


async def test_redirect_not_followed_even_if_client_follows(mock, ftime):
    mock.get(WATCH).mock(
        return_value=httpx.Response(
            302, headers={"Location": "https://example.com/steal"}
        )
    )
    evil = mock.route(host="example.com").mock(
        return_value=httpx.Response(200, text="gotcha")
    )
    async with httpx.AsyncClient(follow_redirects=True) as careless:
        with pytest.raises(NetworkError):
            await make_client(careless, ftime).open(VIDEO)
    assert not evil.called


async def test_retries_then_network_error(mock, http, ftime):
    route_page(mock)
    panel = mock.post(PANEL).mock(return_value=httpx.Response(500))
    session = await make_client(http, ftime).open(VIDEO)
    with pytest.raises(NetworkError) as e:
        await session.ask("q")
    assert e.value.exit_code == 6
    assert panel.call_count == 1 + 2


async def test_transport_error_retried_then_network_error(mock, http, ftime):
    route_page(mock)
    panel = mock.post(PANEL).mock(side_effect=httpx.ReadTimeout("slow"))
    session = await make_client(http, ftime).open(VIDEO)
    with pytest.raises(NetworkError) as e:
        await session.ask("q")
    assert "ReadTimeout" in str(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__
    assert panel.call_count == 3


async def test_retry_succeeds_second_time(mock, http, ftime):
    route_page(mock)
    mock.post(PANEL).mock(side_effect=[httpx.Response(500), answer_response()])
    session = await make_client(http, ftime).open(VIDEO)
    assert "(0:" in await session.ask("q")


async def test_pacer_called_before_each_ask(mock, http, ftime):
    route_page(mock)
    starts: list[float] = []

    def on_panel(request: httpx.Request) -> httpx.Response:
        starts.append(ftime.now)
        return answer_response()

    mock.post(PANEL).mock(side_effect=on_panel)
    session = await make_client(http, ftime, min_interval=5.0).open(VIDEO)
    await session.ask("a")
    await session.ask("b")
    assert len(starts) == 2
    assert starts[1] - starts[0] >= 5.0
    assert ftime.sleeps and all(s > 0 for s in ftime.sleeps)


async def test_pacer_spaces_every_request(mock, http, ftime):
    starts: list[float] = []

    def stamp(response: httpx.Response):
        def handler(request: httpx.Request) -> httpx.Response:
            starts.append(ftime.now)
            return response

        return handler

    mock.get(WATCH).mock(side_effect=stamp(httpx.Response(200, text=page_html())))
    mock.post(NEXT).mock(
        side_effect=stamp(httpx.Response(200, json=fixture_json("next_eligible.json")))
    )
    mock.post(PANEL).mock(side_effect=stamp(answer_response()))
    session = await make_client(http, ftime, min_interval=5.0).open(VIDEO)
    await session.ask("a")
    assert len(starts) == 3
    assert all(b - a >= 5.0 for a, b in zip(starts, starts[1:]))


async def test_pacer_no_wait_after_long_gap():
    ft = FakeTime()
    pacer = Pacer(5.0, sleep=ft.sleep, clock=ft.clock)
    await pacer.wait()
    ft.now += 10
    await pacer.wait()
    assert ft.sleeps == []
    await pacer.wait()
    assert ft.sleeps == [5.0]


async def test_error_message_has_no_secrets(mock, http, ftime):
    route_page(mock)
    header = sapisidhash(SAPISID, YT, int(NOW))
    leak = f"boom {SAPISID} {SID} FAKE_CONTINUATION_1 FAKE_CTP_1 {header} {header.split(' ', 1)[1]}"
    mock.post(PANEL).mock(side_effect=httpx.ConnectError(leak))
    session = await make_client(http, ftime).open(VIDEO)
    with pytest.raises(NetworkError) as e:
        await session.ask("q")
    text = str(e.value) + (e.value.hint or "")
    for secret in (
        SAPISID,
        SID,
        "FAKE_CONTINUATION_1",
        "FAKE_CTP_1",
        header,
        header.split("_", 1)[1],
    ):
        assert secret not in text
    assert "ConnectError" in text and "***" in text


async def test_http_401_is_auth_error(mock, http, ftime):
    mock.get(WATCH).mock(return_value=httpx.Response(200, text=page_html()))
    nxt = mock.post(NEXT).mock(return_value=httpx.Response(401))
    with pytest.raises(AuthError) as e:
        await make_client(http, ftime).open(VIDEO)
    assert e.value.exit_code == 4
    assert nxt.call_count == 1


async def test_other_4xx_is_network_error_without_retry(mock, http, ftime):
    route_page(mock)
    panel = mock.post(PANEL).mock(return_value=httpx.Response(400))
    session = await make_client(http, ftime).open(VIDEO)
    with pytest.raises(NetworkError):
        await session.ask("q")
    assert panel.call_count == 1


async def test_non_json_next_is_network_error(mock, http, ftime):
    mock.get(WATCH).mock(return_value=httpx.Response(200, text=page_html()))
    mock.post(NEXT).mock(return_value=httpx.Response(200, text="<html>oops</html>"))
    with pytest.raises(NetworkError):
        await make_client(http, ftime).open(VIDEO)


async def test_reprs_hide_secrets(mock, http, ftime):
    route_page(mock)
    client = make_client(http, ftime)
    session = await client.open(VIDEO)
    for text in (repr(client), repr(session)):
        for secret in (SAPISID, SID, "FAKE_CONTINUATION_1", "FAKE_CTP_1"):
            assert secret not in text
