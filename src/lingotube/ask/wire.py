"""Pure functions for YouTube's internal Ask-chat requests (spec section 12 + probe findings).

No network and no clocks here: everything is data in, data out.
"""

import copy
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from lingotube.errors import YOUTUBE_CHANGED_HINT, ChatUnavailableError, YouTubeChangedError
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
    """Opaque chat command taken from a ``sendUserQueryCommand`` entry.

    Its values never appear in the representation.

    Attributes:
        continuation: Token that identifies the chat for the next question.
        click_tracking_params: Tracking parameters sent with the question.
    """

    continuation: str
    click_tracking_params: str

    def __repr__(self) -> str:
        """Hide the command values in the representation."""
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
    """Find the first complete send command in a response.

    Args:
        next_response: Parsed JSON response to search.
        panel_only: If True, search only inside the chat panel. Otherwise search the
            whole response.

    Returns:
        The command, or None if the response has no complete command.
    """
    roots = list(_chat_panels(data=next_response)) if panel_only else [next_response]
    for root in roots:
        for d in _walk(obj=root):
            cmd = _command_from(raw=d.get("sendUserQueryCommand"))
            if cmd is not None:
                return cmd
    return None


def find_chat_panel_token(next_response: dict[str, Any]) -> str | None:
    """Find the first continuation token inside the chat panel.

    Args:
        next_response: Parsed JSON response to search.

    Returns:
        The token, or None if the chat panel has none. The token is needed when the
        first get_panel response is empty.
    """
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
    """Check whether YouTube reports the user as signed in.

    Args:
        next_response: Parsed JSON response of the next request.

    Returns:
        True only if the response says explicitly that the user is not logged out.
    """
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
    """Build the request body that sends one question to the chat.

    Args:
        context: Innertube client context from the watch page. It is copied, not changed.
        cmd: Send command that identifies the chat.
        prompt: Question text.
        now_ms: Current time in milliseconds, used in the client message id.
        player_offset_ms: Playback position sent with the question. Defaults to 0.

    Returns:
        The JSON body of the get_panel request.
    """
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
    """Join the text of the chat answer items.

    Only ``youChatItemViewModel.text.content`` is used. Snackbars, chips and disclaimers
    are ignored.

    Args:
        get_panel_response: Parsed JSON response of the get_panel request.

    Returns:
        The answer text, with the parts separated by newlines.

    Raises:
        YouTubeChangedError: If the response has no chat item at all.
        ChatUnavailableError: If the chat item exists but has no answer text.
    """
    if not any("youChatItemViewModel" in d for d in _walk(obj=get_panel_response)):
        raise YouTubeChangedError(
            message="The YouTube chat response has an unexpected shape.",
            hint=YOUTUBE_CHANGED_HINT,
        )
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
        raise ChatUnavailableError(message="The YouTube chat returned an empty answer.")
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
    """Read the logged-in flag from the HTML of the watch page.

    Args:
        html: HTML of the watch page.

    Returns:
        True or False if the page states it, or None if the page has no such flag.
    """
    m = _LOGGED_IN.search(string=html)
    return None if m is None else m.group(1) == "true"


def extract_page(html: str) -> tuple[dict[str, Any], VideoInfo]:
    """Read the client context and the video facts from the watch page.

    Args:
        html: HTML of the watch page.

    Returns:
        The Innertube client context and the video info.

    Raises:
        YouTubeChangedError: If the page cannot be parsed.
    """
    unavailable = YouTubeChangedError(
        message="Could not read the YouTube watch page.",
        hint=YOUTUBE_CHANGED_HINT,
    )
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
    status = player.get("playabilityStatus") if isinstance(player, dict) else None
    if not isinstance(details, dict) and isinstance(status, dict) and status.get("status") not in (None, "OK"):
        raise ChatUnavailableError(message="The YouTube video is unavailable (removed, private or mistyped).")
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
