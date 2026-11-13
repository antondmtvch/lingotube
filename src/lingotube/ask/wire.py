"""Pure functions for YouTube's internal Ask-chat requests (spec section 12 + probe findings).

No network and no clocks here: everything is data in, data out.
"""

import copy
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from lingotube.errors import ChatUnavailableError
from lingotube.models import VideoInfo

CHAT_PANEL_ID = "PAyouchat"

_CONTEXT_MARKER = '"INNERTUBE_CONTEXT":'
_PLAYER_MARKER = re.compile(pattern=r"var ytInitialPlayerResponse\s*=\s*")
_LOGGED_IN = re.compile(pattern=r'"LOGGED_IN"\s*:\s*(true|false)')


@dataclass(
    frozen=True,
    slots=True,
)
class SendCommand:
    """Opaque chat command from `sendUserQueryCommand`. Values never appear in repr."""

    continuation: str
    click_tracking_params: str

    def __repr__(self) -> str:
        return "SendCommand(***)"


def _walk(obj: Any) -> Iterator[dict[str, Any]]:
    """Yield every dict of a JSON tree (iterative: answers are deep and large)."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(
            cur,
            dict,
        ):
            yield cur
            stack.extend(reversed(list(cur.values())))
        elif isinstance(
            cur,
            list,
        ):
            stack.extend(reversed(cur))


def _chat_panels(data: Any) -> Iterator[dict[str, Any]]:
    for d in _walk(obj=data):
        renderer = d.get("engagementPanelSectionListRenderer")
        if (
            isinstance(
                renderer,
                dict,
            )
            and renderer.get("panelIdentifier") == CHAT_PANEL_ID
        ):
            yield renderer


def _command_from(raw: Any) -> SendCommand | None:
    if not isinstance(
        raw,
        dict,
    ):
        return None
    inner = raw.get("innertubeCommand")
    if not isinstance(
        inner,
        dict,
    ):
        return None
    ctp = inner.get("clickTrackingParams")
    cc = inner.get("continuationCommand")
    token = (
        cc.get("token")
        if isinstance(
            cc,
            dict,
        )
        else None
    )
    if (
        isinstance(
            token,
            str,
        )
        and token
        and isinstance(
            ctp,
            str,
        )
        and ctp
    ):
        return SendCommand(
            continuation=token,
            click_tracking_params=ctp,
        )
    return None


def find_send_command(
    next_response: dict[str, Any],
    *,
    panel_only: bool = True,
) -> SendCommand | None:
    """First complete `sendUserQueryCommand` inside a `PAyouchat` panel (or anywhere if not panel_only)."""
    roots = list(_chat_panels(data=next_response)) if panel_only else [next_response]
    for root in roots:
        for d in _walk(obj=root):
            cmd = _command_from(raw=d.get("sendUserQueryCommand"))
            if cmd is not None:
                return cmd
    return None


def find_chat_panel_token(next_response: dict[str, Any]) -> str | None:
    """First continuation token of the `PAyouchat` panel (for the 'empty initial get_panel')."""
    for panel in _chat_panels(data=next_response):
        for d in _walk(obj=panel):
            cc = d.get("continuationCommand")
            if (
                isinstance(
                    cc,
                    dict,
                )
                and isinstance(
                    cc.get("token"),
                    str,
                )
                and cc["token"]
            ):
                return cc["token"]
    return None


def is_signed_in(next_response: dict[str, Any]) -> bool:
    ctx = next_response.get("responseContext")
    main = (
        ctx.get("mainAppWebResponseContext")
        if isinstance(
            ctx,
            dict,
        )
        else None
    )
    return (
        isinstance(
            main,
            dict,
        )
        and main.get("loggedOut") is False
    )


def build_ask_body(
    context: dict[str, Any],
    cmd: SendCommand,
    prompt: str,
    now_ms: int,
    player_offset_ms: int = 0,
) -> dict[str, Any]:
    ctx = copy.deepcopy(x=context)
    ctx["clickTracking"] = {"clickTrackingParams": cmd.click_tracking_params}
    return {
        "context": ctx,
        "continuation": cmd.continuation,
        "formData": {
            "inputComposerFormData": {
                "clientMessageId": f"youchat-{now_ms}",
                "playerOffsetMs": str(player_offset_ms),
                "userInputText": prompt,
            }
        },
    }


def extract_answer(get_panel_response: dict[str, Any]) -> str:
    """Only `youChatItemViewModel.text.content`; snackbars, chips, disclaimers are ignored."""
    parts: list[str] = []
    for d in _walk(obj=get_panel_response):
        item = d.get("youChatItemViewModel")
        text = (
            item.get("text")
            if isinstance(
                item,
                dict,
            )
            else None
        )
        content = (
            text.get("content")
            if isinstance(
                text,
                dict,
            )
            else None
        )
        if (
            isinstance(
                content,
                str,
            )
            and content.strip()
        ):
            parts.append(content)
    if not parts:
        raise ChatUnavailableError(message="Чат YouTube вернул пустой ответ.")
    return "\n".join(parts)


def _decode_object_at(
    html: str,
    start: int,
) -> Any:
    brace = html.find(
        "{",
        start,
    )
    if brace < 0:
        raise ValueError("no object")
    value, _ = json.JSONDecoder().raw_decode(
        s=html,
        idx=brace,
    )
    return value


def page_logged_in(html: str) -> bool | None:
    m = _LOGGED_IN.search(string=html)
    return None if m is None else m.group(1) == "true"


def extract_page(html: str) -> tuple[dict[str, Any], VideoInfo]:
    """Innertube client context (ytcfg) and video info (ytInitialPlayerResponse)."""
    unavailable = ChatUnavailableError(message="Не удалось разобрать страницу видео YouTube (видео недоступно?).")
    i = html.find(_CONTEXT_MARKER)
    m = _PLAYER_MARKER.search(string=html)
    if i < 0 or m is None:
        raise unavailable
    try:
        context = _decode_object_at(
            html=html,
            start=i + len(_CONTEXT_MARKER),
        )
        player = _decode_object_at(
            html=html,
            start=m.end(),
        )
    except ValueError:
        raise unavailable from None
    details = (
        player.get("videoDetails")
        if isinstance(
            player,
            dict,
        )
        else None
    )
    if not isinstance(
        context,
        dict,
    ) or not isinstance(
        details,
        dict,
    ):
        raise unavailable
    video_id, title, length = (
        details.get("videoId"),
        details.get("title"),
        details.get("lengthSeconds"),
    )
    if (
        not isinstance(
            video_id,
            str,
        )
        or not isinstance(
            length,
            str | int,
        )
        or not str(length).isdigit()
    ):
        raise unavailable
    return context, VideoInfo(
        video_id=video_id,
        duration=float(int(length)),
        title=(
            title
            if isinstance(
                title,
                str,
            )
            else ""
        ),
        language=_asr_language(player=player),
    )


def _asr_language(player: dict[str, Any]) -> str | None:
    captions = player.get("captions")
    renderer = (
        captions.get("playerCaptionsTracklistRenderer")
        if isinstance(
            captions,
            dict,
        )
        else None
    )
    tracks = (
        renderer.get("captionTracks")
        if isinstance(
            renderer,
            dict,
        )
        else None
    )
    for track in (
        tracks
        if isinstance(
            tracks,
            list,
        )
        else []
    ):
        if (
            isinstance(
                track,
                dict,
            )
            and track.get("kind") == "asr"
        ):
            code = track.get("languageCode")
            if (
                isinstance(
                    code,
                    str,
                )
                and code
            ):
                return code
    return None
