"""Async client for YouTube's Ask chat — the only code that talks to YouTube.

Security rules (spec section 10, global constraints):
- every request goes to https://www.youtube.com only (checked before sending);
- redirects are never followed (any 3xx is a NetworkError);
- requests are strictly sequential and paced (one lock + Pacer for every request);
- error messages pass through `redact` with cookies, SAPISIDHASH, visitor data and chat tokens.

HTTP status policy: 401/403 -> AuthError; 429 and 5xx, plus transport errors -> retried up to
`max_retries` (each retry paced) then NetworkError; any other 4xx -> NetworkError without retry
(YouTube gives no reliable way to tell a chat refusal from a malformed request by status alone).
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Protocol

import httpx

from lingotube.ask import wire
from lingotube.ask.wire import SendCommand
from lingotube.auth import CookieSource, Credentials, auth_headers
from lingotube.auth.base import EXPORT_HINT
from lingotube.errors import AuthError, ChatUnavailableError, NetworkError
from lingotube.models import VideoInfo
from lingotube.redact import redact

ORIGIN = "https://www.youtube.com"
ALLOWED_HOST = "www.youtube.com"
REQUEST_TIMEOUT = 120.0  # seconds per request (probe: max answer time seen 11 s)
WATCH_PATH = "/watch"
NEXT_PATH = "/youtubei/v1/next"
GET_PANEL_PATH = "/youtubei/v1/get_panel"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
ACCEPT_LANGUAGE = "ru,en;q=0.8"  # as in the live-verified probe
WEB_CLIENT_NAME_ID = "1"  # numeric id of the WEB innertube client

_STALE_COOKIES = (
    "YouTube не видит вход в аккаунт: cookies устарели или выгружены без входа."
)


class Pacer:
    """Guarantees at least `min_interval` seconds between the starts of consecutive requests."""

    def __init__(
        self,
        min_interval: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min_interval = min_interval
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None

    async def wait(self) -> None:
        if self._last is not None:
            delay = self._min_interval - (self._clock() - self._last)
            if delay > 0:
                await self._sleep(delay)
        self._last = self._clock()

    def __repr__(self) -> str:
        return f"Pacer(min_interval={self._min_interval})"


class AskSession(Protocol):
    info: VideoInfo

    async def ask(self, prompt: str) -> str: ...


class AskClient(Protocol):
    async def open(self, video_id: str) -> AskSession: ...


def _ensure_youtube(url: httpx.URL) -> None:
    if url.scheme != "https" or url.host != ALLOWED_HOST or url.port not in (None, 443):
        raise NetworkError(
            message="Отказ: запрос не к https://www.youtube.com не выполняется."
        )


MIN_SECRET_LENGTH = 4


class _Channel:
    """Per-open request state: credentials, innertube context, secrets to redact."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        pacer: Pacer,
        lock: asyncio.Lock,
        creds: Credentials,
        video_id: str,
        max_retries: int,
        timeout: float,
        wall_clock: Callable[[], float],
    ) -> None:
        self._http = http
        self._pacer = pacer
        self._lock = lock
        self._creds = creds
        self._video_id = video_id
        self._max_retries = max_retries
        self._timeout = timeout
        self.wall_clock = wall_clock
        self._secrets: set[str] = set()
        self.add_secrets(values=creds.secrets())
        self.context: dict[str, Any] = {}

    def add_secrets(self, values: Iterable[str]) -> None:
        # a 1-3 char value would mask digits and letters all over the error text
        self._secrets.update(v for v in values if len(v) >= MIN_SECRET_LENGTH)

    def redact(self, text: str) -> str:
        return redact(
            text=text,
            secrets=self._secrets,
        )

    def set_context(self, context: dict[str, Any]) -> None:
        self.context = context
        client = context.get("client")
        if isinstance(
            client,
            dict,
        ) and isinstance(
            client.get("visitorData"),
            str,
        ):
            self.add_secrets(values=[client["visitorData"]])

    def _headers(self, api: bool) -> dict[str, str]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": ACCEPT_LANGUAGE,
            "Cookie": "; ".join(f"{k}={v}" for k, v in self._creds.cookies.items()),
        }
        if not api:
            headers["Accept"] = "text/html"
            return headers
        auth = auth_headers(
            creds=self._creds,
            now=int(self.wall_clock()),
        )
        authorization = auth["Authorization"]
        self.add_secrets(
            values=[
                authorization,
                authorization.split(
                    " ",
                    1,
                )[-1],
                authorization.rsplit(
                    "_",
                    1,
                )[-1],
            ]
        )
        headers.update(auth)
        referer = httpx.URL(
            url=ORIGIN + WATCH_PATH,
            params={"v": self._video_id},
        )
        headers.update(
            {
                "Content-Type": "application/json",
                "Referer": str(referer),
                "X-Goog-AuthUser": "0",
                "X-YouTube-Client-Name": WEB_CLIENT_NAME_ID,
            }
        )
        client = self.context.get("client")
        if isinstance(
            client,
            dict,
        ):
            if isinstance(
                client.get("clientVersion"),
                str,
            ):
                headers["X-YouTube-Client-Version"] = client["clientVersion"]
            if isinstance(
                client.get("visitorData"),
                str,
            ):
                headers["X-Goog-Visitor-Id"] = client["visitorData"]
        return headers

    async def request(
        self,
        what: str,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = httpx.URL(
            url=ORIGIN + path,
            params=params,
        )
        _ensure_youtube(url=url)
        api = body is not None
        attempts = 1 + self._max_retries
        last = ""
        for _ in range(attempts):
            async with self._lock:
                await self._pacer.wait()
                try:
                    resp = await self._http.request(
                        method=method,
                        url=url,
                        headers=self._headers(api=api),
                        json=body,
                        timeout=self._timeout,
                        follow_redirects=False,
                    )
                except httpx.TransportError as e:
                    last = f"{what}: {type(e).__name__}: {e}"
                    continue
                except httpx.HTTPError as e:
                    raise NetworkError(
                        message=self.redact(text=f"{what}: {type(e).__name__}: {e}")
                    ) from None
            status = resp.status_code
            if resp.history or 300 <= status < 400 or resp.url.host != ALLOWED_HOST:
                raise NetworkError(
                    message=f"{what}: YouTube ответил перенаправлением (HTTP {status}); переходы не выполняются."
                )
            if status in (401, 403):
                raise AuthError(
                    message=f"{what}: YouTube отказал в доступе (HTTP {status}).",
                    hint=EXPORT_HINT,
                )
            if status == 429 or status >= 500:
                last = f"{what}: HTTP {status}"
                continue
            if status >= 400:
                raise NetworkError(message=f"{what}: HTTP {status}")
            return resp
        raise NetworkError(
            message=self.redact(text=f"{last} (попыток: {attempts})")
        ) from None

    async def post_json(
        self,
        what: str,
        path: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        resp = await self.request(
            what=what,
            method="POST",
            path=path,
            params={"prettyPrint": "false"},
            body=body,
        )
        try:
            data = resp.json()
        except ValueError:
            raise NetworkError(message=f"{what}: YouTube вернул не JSON.") from None
        if not isinstance(
            data,
            dict,
        ):
            raise NetworkError(message=f"{what}: неожиданный формат ответа YouTube.")
        return data


class YouTubeAskSession(AskSession):
    """One Ask chat for one video. Remembers the current send command between questions."""

    def __init__(
        self,
        channel: _Channel,
        info: VideoInfo,
        cmd: SendCommand,
    ) -> None:
        self._channel = channel
        self.info = info
        self._cmd = cmd
        channel.add_secrets(values=[cmd.continuation, cmd.click_tracking_params])

    async def ask(self, prompt: str) -> str:
        now_ms = int(self._channel.wall_clock() * 1000)
        body = wire.build_ask_body(
            context=self._channel.context,
            cmd=self._cmd,
            prompt=prompt,
            now_ms=now_ms,
        )
        data = await self._channel.post_json(
            what="get_panel",
            path=GET_PANEL_PATH,
            body=body,
        )
        answer = wire.extract_answer(get_panel_response=data)
        fresh = wire.find_send_command(
            next_response=data,
            panel_only=False,
        )
        if fresh is not None:
            self._channel.add_secrets(
                values=[fresh.continuation, fresh.click_tracking_params]
            )
            self._cmd = fresh
        return answer

    def __repr__(self) -> str:
        return f"YouTubeAskSession(video_id={self.info.video_id!r})"


class YouTubeAskClient(AskClient):
    def __init__(
        self,
        http: httpx.AsyncClient,
        cookies: CookieSource,
        pacer: Pacer,
        max_retries: int = 2,
        *,
        wall_clock: Callable[[], float] = time.time,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        self._http = http
        self._cookies = cookies
        self._pacer = pacer
        self._max_retries = max_retries
        self._wall_clock = wall_clock
        self._timeout = timeout
        self._lock = asyncio.Lock()

    async def open(self, video_id: str) -> YouTubeAskSession:
        creds = await self._cookies.load()
        creds.require_sapisid()
        ch = _Channel(
            http=self._http,
            pacer=self._pacer,
            lock=self._lock,
            creds=creds,
            video_id=video_id,
            max_retries=self._max_retries,
            timeout=self._timeout,
            wall_clock=self._wall_clock,
        )
        page = await ch.request(
            what="watch",
            method="GET",
            path=WATCH_PATH,
            params={"v": video_id},
        )
        html = page.text
        if wire.page_logged_in(html=html) is False:
            raise AuthError(
                message=_STALE_COOKIES,
                hint=EXPORT_HINT,
            )
        context, info = wire.extract_page(html=html)
        ch.set_context(context=context)

        nxt = await ch.post_json(
            what="next",
            path=NEXT_PATH,
            body={"context": context, "videoId": video_id},
        )
        if not wire.is_signed_in(next_response=nxt):
            raise AuthError(
                message=_STALE_COOKIES,
                hint=EXPORT_HINT,
            )
        cmd = wire.find_send_command(next_response=nxt)
        if cmd is None:
            panel_token = wire.find_chat_panel_token(next_response=nxt)
            if panel_token:
                # spec section 12: the command may appear after an "empty" initial get_panel
                ch.add_secrets(values=[panel_token])
                initial = await ch.post_json(
                    what="get_panel",
                    path=GET_PANEL_PATH,
                    body={"context": context, "continuation": panel_token},
                )
                cmd = wire.find_send_command(
                    next_response=initial,
                    panel_only=False,
                )
        if cmd is None:
            raise ChatUnavailableError(
                message="Чат YouTube («Спросить») недоступен для этого видео."
            )
        return YouTubeAskSession(
            channel=ch,
            info=info,
            cmd=cmd,
        )

    def __repr__(self) -> str:
        return f"YouTubeAskClient(max_retries={self._max_retries})"
