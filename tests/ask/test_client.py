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
    return json.loads(s=(FIX / name).read_text(encoding="utf-8"))


def page_html() -> str:
    return (FIX / "watch_page.html").read_text(encoding="utf-8")


class FakeCookies:
    async def load(self) -> Credentials:
        return Credentials(cookies={"SAPISID": SAPISID, "SID": SID})


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
    with respx.mock(
        assert_all_mocked=True,
        assert_all_called=False,
    ) as router:
        yield router


@pytest.fixture
async def http():
    async with httpx.AsyncClient(follow_redirects=False) as client:
        yield client


def make_client(
    http: httpx.AsyncClient,
    ftime: FakeTime,
    min_interval: float = 5.0,
) -> YouTubeAskClient:
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
    return httpx.Response(
        status_code=200,
        json=fixture_json(name="get_panel_answer.json"),
    )


async def test_open_and_ask_happy_path(
    mock,
    http,
    ftime,
):
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
    assert (
        sent["formData"]["inputComposerFormData"]["userInputText"] == "дай транскрипцию"
    )
    assert (
        sent["formData"]["inputComposerFormData"]["clientMessageId"]
        == "youchat-1700000000000"
    )
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
    route_page(mock=mock)
    panel = mock.post(url=PANEL).mock(return_value=answer_response())
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    await session.ask(prompt="a")
    await session.ask(prompt="b")
    assert all(
        json.loads(s=c.request.content)["continuation"] == "FAKE_CONTINUATION_1"
        for c in panel.calls
    )


async def test_empty_initial_get_panel_fallback(
    mock,
    http,
    ftime,
):
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
    route_page(mock=mock)
    panel = mock.post(url=PANEL).mock(side_effect=httpx.ReadTimeout(message="slow"))
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    with pytest.raises(expected_exception=NetworkError) as e:
        await session.ask(prompt="q")
    assert "ReadTimeout" in str(object=e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__
    assert panel.call_count == 3


async def test_retry_succeeds_second_time(
    mock,
    http,
    ftime,
):
    route_page(mock=mock)
    mock.post(url=PANEL).mock(
        side_effect=[httpx.Response(status_code=500), answer_response()]
    )
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
        )
    )


async def test_pacer_no_wait_after_long_gap():
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
    route_page(mock=mock)
    header = sapisidhash(
        sapisid=SAPISID,
        origin=YT,
        now=int(NOW),
    )
    digest = header.split(
        sep=" ",
        maxsplit=1,
    )[1]
    leak = f"boom {SAPISID} {SID} FAKE_CONTINUATION_1 FAKE_CTP_1 {header} {digest}"
    mock.post(url=PANEL).mock(side_effect=httpx.ConnectError(message=leak))
    session = await make_client(
        http=http,
        ftime=ftime,
    ).open(video_id=VIDEO)
    with pytest.raises(expected_exception=NetworkError) as e:
        await session.ask(prompt="q")
    text = str(object=e.value) + (e.value.hint or "")
    for secret in (
        SAPISID,
        SID,
        "FAKE_CONTINUATION_1",
        "FAKE_CTP_1",
        header,
        header.split(
            sep="_",
            maxsplit=1,
        )[1],
    ):
        assert secret not in text
    assert "ConnectError" in text and "***" in text


async def test_http_401_is_auth_error(
    mock,
    http,
    ftime,
):
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
    route_page(mock=mock)
    client = make_client(
        http=http,
        ftime=ftime,
    )
    session = await client.open(video_id=VIDEO)
    for text in (repr(client), repr(session)):
        for secret in (SAPISID, SID, "FAKE_CONTINUATION_1", "FAKE_CTP_1"):
            assert secret not in text
