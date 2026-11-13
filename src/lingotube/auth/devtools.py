"""Minimal Chrome DevTools Protocol client over a loopback WebSocket.

Exception messages are fixed text only: nothing from the browser (which may carry
cookie values) is ever propagated.
"""

import asyncio
import itertools
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException

_MAX_MESSAGE_BYTES = 16 * 2**20


class DevToolsError(Exception):
    """A DevTools command failed; the message is our own text, never browser output."""


class DevToolsConnectionClosed(DevToolsError):
    """The browser closed the DevTools connection."""


@dataclass(frozen=True)
class BrowserCookie:
    name: str
    value: str
    domain: str

    def __repr__(self) -> str:
        return f"BrowserCookie(name={self.name}, domain={self.domain}, value=***)"


class DevToolsConnection:
    def __init__(self, websocket: ClientConnection, timeout: float) -> None:
        self._websocket = websocket
        self._timeout = timeout
        self._message_ids = itertools.count(1)

    async def send_command(
        self, method: str, params: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send one command and return its `result`; events and foreign ids are skipped."""
        message_id = next(self._message_ids)
        command: dict[str, Any] = {"id": message_id, "method": method}
        if params is not None:
            command["params"] = dict(params)
        try:
            async with asyncio.timeout(self._timeout):
                await self._websocket.send(json.dumps(command))
                while True:
                    reply = json.loads(await self._websocket.recv())
                    if reply.get("id") != message_id:
                        continue
                    if "error" in reply:
                        raise DevToolsError(f"DevTools command {method} failed")
                    return reply.get("result", {})
        except ConnectionClosed:
            raise DevToolsConnectionClosed("DevTools connection closed") from None
        except TimeoutError:
            raise DevToolsError(f"DevTools command {method} timed out") from None
        except ValueError:
            raise DevToolsError(
                f"DevTools command {method} got a malformed reply"
            ) from None


def _require_loopback_websocket_url(websocket_url: str) -> None:
    parts = urlsplit(websocket_url)
    if parts.scheme != "ws" or parts.hostname != "127.0.0.1":
        raise ValueError("DevTools endpoint must be ws://127.0.0.1")


@asynccontextmanager
async def connect_to_browser_devtools(
    websocket_url: str, timeout: float = 10.0
) -> AsyncIterator[DevToolsConnection]:
    _require_loopback_websocket_url(websocket_url)
    async with AsyncExitStack() as stack:
        try:
            websocket = await stack.enter_async_context(
                connect(
                    websocket_url,
                    proxy=None,
                    open_timeout=timeout,
                    max_size=_MAX_MESSAGE_BYTES,
                )
            )
        except OSError, TimeoutError, WebSocketException, ValueError:
            raise DevToolsError("DevTools connection failed") from None
        yield DevToolsConnection(websocket, timeout)


async def read_all_cookies(connection: DevToolsConnection) -> list[BrowserCookie]:
    result = await connection.send_command("Storage.getCookies")
    return [
        BrowserCookie(name=c["name"], value=c["value"], domain=c["domain"])
        for c in result.get("cookies", [])
    ]


async def clear_all_cookies(connection: DevToolsConnection) -> None:
    await connection.send_command("Storage.clearCookies")


async def open_page(connection: DevToolsConnection, url: str) -> None:
    await connection.send_command("Target.createTarget", {"url": url})


async def count_open_pages(connection: DevToolsConnection) -> int:
    result = await connection.send_command("Target.getTargets")
    return sum(1 for t in result.get("targetInfos", []) if t.get("type") == "page")


async def close_browser(connection: DevToolsConnection) -> None:
    try:
        await connection.send_command("Browser.close")
    except DevToolsConnectionClosed:
        pass
