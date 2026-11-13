import asyncio
import http
import json
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack

import pytest
from websockets.asyncio.server import ServerConnection, serve

from lingotube.auth.devtools import (
    BrowserCookie,
    DevToolsConnectionClosed,
    DevToolsError,
    clear_all_cookies,
    close_browser,
    connect_to_browser_devtools,
    count_open_pages,
    open_page,
    read_all_cookies,
)

Handler = Callable[[ServerConnection], Awaitable[None]]


@pytest.fixture
async def cdp_server():
    """Factory: run a fake DevTools server with the given handler, return its URL."""
    async with AsyncExitStack() as stack:

        async def start(handler: Handler) -> str:
            server = await stack.enter_async_context(serve(handler, "127.0.0.1", 0))
            port = server.sockets[0].getsockname()[1]
            return f"ws://127.0.0.1:{port}/devtools/browser/test"

        yield start


def replying(result: dict) -> Handler:
    async def handler(websocket: ServerConnection) -> None:
        async for raw in websocket:
            message = json.loads(raw)
            await websocket.send(json.dumps({"id": message["id"], "result": result}))

    return handler


async def test_send_command_returns_result_and_skips_events(cdp_server):
    async def handler(websocket: ServerConnection) -> None:
        await websocket.recv()
        await websocket.send(
            json.dumps({"method": "Target.targetCreated", "params": {}})
        )
        await websocket.send(json.dumps({"id": 99, "result": {"other": True}}))
        await websocket.send(json.dumps({"id": 1, "result": {"ok": True}}))

    url = await cdp_server(handler)
    async with connect_to_browser_devtools(url) as connection:
        assert await connection.send_command("Browser.getVersion") == {"ok": True}


async def test_command_error_raises_without_payload_text(cdp_server):
    async def handler(websocket: ServerConnection) -> None:
        await websocket.recv()
        await websocket.send(json.dumps({"id": 1, "error": {"message": "LEAKME"}}))

    url = await cdp_server(handler)
    async with connect_to_browser_devtools(url) as connection:
        with pytest.raises(DevToolsError) as error:
            await connection.send_command("Browser.getVersion")
    assert "LEAKME" not in str(error.value)


async def test_closed_connection_raises_connection_closed(cdp_server):
    async def handler(websocket: ServerConnection) -> None:
        await websocket.close()

    url = await cdp_server(handler)
    async with connect_to_browser_devtools(url) as connection:
        with pytest.raises(DevToolsConnectionClosed):
            await connection.send_command("Browser.getVersion")


async def test_command_timeout_raises_devtools_error(cdp_server):
    async def handler(websocket: ServerConnection) -> None:
        await websocket.wait_closed()

    url = await cdp_server(handler)
    async with connect_to_browser_devtools(url, timeout=0.2) as connection:
        with pytest.raises(DevToolsError):
            await connection.send_command("Browser.getVersion")


def test_non_loopback_url_is_rejected():
    async def connect() -> None:
        async with connect_to_browser_devtools(
            "ws://example.com:9222/devtools/browser/x"
        ):
            pass

    with pytest.raises(ValueError):
        asyncio.run(connect())


async def test_read_all_cookies_maps_fields(cdp_server):
    cookie = {"name": "SAPISID", "value": "v", "domain": ".youtube.com", "path": "/"}
    url = await cdp_server(replying({"cookies": [cookie]}))
    async with connect_to_browser_devtools(url) as connection:
        cookies = await read_all_cookies(connection)
    assert cookies == [BrowserCookie(name="SAPISID", value="v", domain=".youtube.com")]


def test_browser_cookie_repr_hides_value():
    assert "secret" not in repr(BrowserCookie("SAPISID", "secret", ".youtube.com"))


async def test_close_browser_tolerates_connection_drop(cdp_server):
    async def handler(websocket: ServerConnection) -> None:
        await websocket.recv()
        await websocket.close()

    url = await cdp_server(handler)
    async with connect_to_browser_devtools(url) as connection:
        await close_browser(connection)


async def test_count_open_pages_counts_only_pages(cdp_server):
    infos = [{"type": "page"}, {"type": "page"}, {"type": "service_worker"}]
    url = await cdp_server(replying({"targetInfos": infos}))
    async with connect_to_browser_devtools(url) as connection:
        assert await count_open_pages(connection) == 2


async def test_open_page_and_clear_all_cookies_send_expected_commands(cdp_server):
    received: list[dict] = []

    async def handler(websocket: ServerConnection) -> None:
        async for raw in websocket:
            message = json.loads(raw)
            received.append(message)
            await websocket.send(json.dumps({"id": message["id"], "result": {}}))

    url = await cdp_server(handler)
    async with connect_to_browser_devtools(url) as connection:
        await open_page(connection, "https://example.test/")
        await clear_all_cookies(connection)
    assert [(m["method"], m.get("params")) for m in received] == [
        ("Target.createTarget", {"url": "https://example.test/"}),
        ("Storage.clearCookies", None),
    ]


async def test_os_error_from_caller_body_propagates_unchanged(cdp_server):
    url = await cdp_server(replying({}))
    with pytest.raises(OSError, match="from the body"):
        async with connect_to_browser_devtools(url):
            raise OSError("from the body")


async def test_rejected_handshake_raises_devtools_error_without_server_text():
    def reject(connection, request):
        return connection.respond(http.HTTPStatus.FORBIDDEN, "LEAKME")

    async with serve(replying({}), "127.0.0.1", 0, process_request=reject) as server:
        port = server.sockets[0].getsockname()[1]
        with pytest.raises(DevToolsError) as error:
            async with connect_to_browser_devtools(f"ws://127.0.0.1:{port}/x"):
                pass
    assert "LEAKME" not in str(error.value)
