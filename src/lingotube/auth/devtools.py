"""Minimal Chrome DevTools Protocol client over a loopback WebSocket.

Exception messages are fixed text only: nothing from the browser (which may carry
cookie values) is ever propagated.
"""

import asyncio
import itertools
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager, suppress
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
    """One cookie read from the browser through DevTools.

    Attributes:
        name: Cookie name.
        value: Cookie value. It is never printed.
        domain: Domain the cookie belongs to.
    """

    name: str
    value: str
    domain: str

    def __repr__(self) -> str:
        """Show the name and the domain, never the value."""
        return f"BrowserCookie(name={self.name}, domain={self.domain}, value=***)"


class DevToolsConnection:
    """An open DevTools session that sends commands and waits for their replies."""

    def __init__(self, websocket: ClientConnection, timeout: float) -> None:
        """Wrap an open WebSocket.

        Args:
            websocket: Connected WebSocket to the browser.
            timeout: Seconds to wait for each reply.
        """
        self._websocket = websocket
        self._timeout = timeout
        self._message_ids = itertools.count(1)

    async def send_command(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
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
                    if not isinstance(reply, dict):
                        raise ValueError("DevTools reply is not a JSON object")
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
            raise DevToolsError(f"DevTools command {method} got a malformed reply") from None


def _require_loopback_websocket_url(websocket_url: str) -> None:
    parts = urlsplit(websocket_url)
    if parts.scheme != "ws" or parts.hostname != "127.0.0.1":
        raise ValueError("DevTools endpoint must be ws://127.0.0.1")


@asynccontextmanager
async def connect_to_browser_devtools(websocket_url: str, timeout: float = 10.0) -> AsyncIterator[DevToolsConnection]:
    """Open a DevTools connection to a local browser.

    Only ws://127.0.0.1 endpoints are accepted.

    Args:
        websocket_url: WebSocket URL of the DevTools endpoint.
        timeout: Seconds to wait for the connection.

    Yields:
        An open connection, which is closed when the block ends.

    Raises:
        ValueError: If the URL is not a loopback ws:// address.
        DevToolsError: If the connection cannot be opened.
    """
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
    """Read every cookie that the browser holds.

    Args:
        connection: Open DevTools connection.

    Returns:
        The cookies, in the order the browser returned them.

    Raises:
        DevToolsError: If the reply has a malformed cookie entry.
    """
    result = await connection.send_command("Storage.getCookies")
    try:
        return [BrowserCookie(name=c["name"], value=c["value"], domain=c["domain"]) for c in result.get("cookies", [])]
    except KeyError, TypeError:
        # No exception text: it could carry a cookie entry.
        raise DevToolsError("DevTools returned a malformed cookie entry") from None


async def close_browser(connection: DevToolsConnection) -> None:
    """Ask the browser to close.

    A connection that is already closed is not an error.

    Args:
        connection: Open DevTools connection.
    """
    with suppress(DevToolsConnectionClosed):
        await connection.send_command("Browser.close")
