import json
from pathlib import Path

import pytest

from lingotube.ask.wire import (
    SendCommand,
    build_ask_body,
    extract_answer,
    extract_page,
    find_chat_panel_token,
    find_send_command,
    is_signed_in,
    page_logged_in,
)
from lingotube.errors import ChatUnavailableError

FIX = Path(__file__).parent.parent / "fixtures"


def load(name: str) -> dict:
    return json.loads(s=(FIX / name).read_text(encoding="utf-8"))


def page() -> str:
    return (FIX / "watch_page.html").read_text(encoding="utf-8")


def test_find_send_command_in_eligible():
    cmd = find_send_command(next_response=load(name="next_eligible.json"))
    assert isinstance(
        cmd,
        SendCommand,
    )
    assert cmd.continuation == "FAKE_CONTINUATION_1"
    assert cmd.click_tracking_params == "FAKE_CTP_1"


def test_find_send_command_absent_returns_none():
    assert find_send_command(next_response=load(name="next_no_chat.json")) is None
    assert find_send_command(next_response=load(name="next_signed_out.json")) is None


def test_find_send_command_outside_panel_ignored_by_default():
    stray = {
        "x": {
            "sendUserQueryCommand": {
                "innertubeCommand": {
                    "clickTrackingParams": "C",
                    "continuationCommand": {"token": "T"},
                }
            }
        }
    }
    assert find_send_command(next_response=stray) is None
    assert find_send_command(
        next_response=stray,
        panel_only=False,
    ) == SendCommand(
        continuation="T",
        click_tracking_params="C",
    )


def test_find_chat_panel_token():
    panel = {
        "engagementPanelSectionListRenderer": {
            "panelIdentifier": "PAyouchat",
            "content": {"continuationCommand": {"token": "PANEL_TOK"}},
        }
    }
    assert find_chat_panel_token(next_response={"a": [panel]}) == "PANEL_TOK"
    assert find_chat_panel_token(next_response=load(name="next_no_chat.json")) is None


def test_is_signed_in():
    assert is_signed_in(next_response=load(name="next_eligible.json")) is True
    assert is_signed_in(next_response=load(name="next_signed_out.json")) is False
    assert is_signed_in(next_response={}) is False


def test_build_ask_body():
    body = build_ask_body(
        context={"client": {"clientName": "WEB"}},
        cmd=SendCommand(
            continuation="TOK",
            click_tracking_params="CTP",
        ),
        prompt="привет",
        now_ms=1700000000000,
    )
    form = body["formData"]["inputComposerFormData"]
    assert body["continuation"] == "TOK"
    assert form == {
        "clientMessageId": "youchat-1700000000000",
        "playerOffsetMs": "0",
        "userInputText": "привет",
    }
    assert body["context"]["clickTracking"]["clickTrackingParams"] == "CTP"


def test_build_ask_body_does_not_mutate_context():
    ctx = {"client": {"clientName": "WEB"}}
    build_ask_body(
        context=ctx,
        cmd=SendCommand(
            continuation="TOK",
            click_tracking_params="CTP",
        ),
        prompt="q",
        now_ms=1,
        player_offset_ms=5000,
    )
    assert ctx == {"client": {"clientName": "WEB"}}


def test_extract_answer():
    answer = extract_answer(get_panel_response=load(name="get_panel_answer.json"))
    assert "(0:" in answer
    assert answer.startswith("Вот полная транскрипция")


def test_extract_answer_ignores_junk_items():
    answer = extract_answer(get_panel_response=load(name="get_panel_answer.json"))
    for junk in (
        "Text copied to clipboard",
        "предложенный вопрос",
        "примечание о точности",
    ):
        assert junk not in answer


def test_extract_answer_empty_raises():
    with pytest.raises(expected_exception=ChatUnavailableError):
        extract_answer(get_panel_response={})


def test_extract_page():
    context, info = extract_page(html=page())
    assert context["client"]["clientName"] == "WEB"
    assert info.video_id == "dQw4w9WgXcQ"
    assert info.duration == 300 and info.duration > 0
    assert info.title == "Тестовое видео"
    assert info.language == "ru"


def test_extract_page_without_asr_track_has_no_language():
    html = page().replace(
        '"kind":"asr",',
        "",
    )
    _, info = extract_page(html=html)
    assert info.language is None


def test_extract_page_garbage_raises():
    with pytest.raises(expected_exception=ChatUnavailableError):
        extract_page(html="<html>nothing here</html>")


def test_page_logged_in():
    assert page_logged_in(html=page()) is True
    assert (
        page_logged_in(
            html=page().replace(
                '"LOGGED_IN":true',
                '"LOGGED_IN":false',
            )
        )
        is False
    )
    assert page_logged_in(html="<html></html>") is None


def test_send_command_repr_hides_token():
    assert "TOK" not in repr(
        SendCommand(
            continuation="TOK",
            click_tracking_params="CTP",
        )
    )
    assert "CTP" not in repr(
        SendCommand(
            continuation="TOK",
            click_tracking_params="CTP",
        )
    )
