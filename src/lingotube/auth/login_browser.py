"""Launch Chrome/Edge in the lingotube-owned login profile and find its DevTools endpoint.

Only the browser process spawned here is ever closed; the person's own browser
and profiles are never touched.
"""

import asyncio
import os
import shutil
import socket
import sys
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Literal

from lingotube.auth.devtools import DevToolsConnection, DevToolsError, close_browser
from lingotube.errors import AuthError, ProfileBusyError

PROFILE_BUSY_HINT = "Закройте окно входа lingotube и повторите."
LOGIN_BROWSERS = ("chrome", "edge")
LaunchMode = Literal["window", "headless", "offscreen"]

BROWSER_CLOSE_WAIT = 10.0
BROWSER_TERMINATE_WAIT = 5.0
_PORT_FILE_POLL_INTERVAL = 0.1
_DEVTOOLS_PORT_FILE_NAME = "DevToolsActivePort"

_WINDOWS_RELATIVE_PATHS = {
    "chrome": Path("Google") / "Chrome" / "Application" / "chrome.exe",
    "edge": Path("Microsoft") / "Edge" / "Application" / "msedge.exe",
}
_WINDOWS_ENV_ROOTS = ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
_MACOS_APP_PATHS = {
    "chrome": "Google Chrome.app/Contents/MacOS/Google Chrome",
    "edge": "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
}
_LINUX_COMMANDS = {
    "chrome": ("google-chrome", "google-chrome-stable"),
    "edge": ("microsoft-edge", "microsoft-edge-stable"),
}
_MODE_FLAGS: dict[str, list[str]] = {
    "window": [],
    "headless": ["--headless"],
    "offscreen": ["--window-position=-32000,-32000", "--window-size=1024,768"],
}


def find_browser_executable(
    browser: str,
    platform: str = sys.platform,
    env: Mapping[str, str] = os.environ,
    is_file: Callable[[Path], bool] = Path.is_file,
    which: Callable[[str], str | None] = shutil.which,
) -> Path | None:
    """Return the installed executable of `browser` ("chrome" or "edge"), or None."""
    if platform == "win32":
        for env_name in _WINDOWS_ENV_ROOTS:
            root = env.get(env_name)
            if not root:
                continue
            candidate = Path(root) / _WINDOWS_RELATIVE_PATHS[browser]
            if is_file(candidate):
                return candidate
        return None
    if platform == "darwin":
        for applications in (Path("/Applications"), Path.home() / "Applications"):
            candidate = applications / _MACOS_APP_PATHS[browser]
            if is_file(candidate):
                return candidate
        return None
    for command in _LINUX_COMMANDS[browser]:
        found = which(command)
        if found:
            return Path(found)
    return None


def find_first_installed_browser(
    platform: str = sys.platform,
    env: Mapping[str, str] = os.environ,
    is_file: Callable[[Path], bool] = Path.is_file,
    which: Callable[[str], str | None] = shutil.which,
) -> tuple[str, Path] | None:
    """Return (name, executable) of the first installed browser: chrome, then edge."""
    for browser in LOGIN_BROWSERS:
        executable = find_browser_executable(
            browser, platform=platform, env=env, is_file=is_file, which=which
        )
        if executable is not None:
            return browser, executable
    return None


def browser_command_line(
    executable: Path, profile_dir: Path, mode: LaunchMode, start_url: str
) -> list[str]:
    """Argument list (no shell) for the login browser; no automation flags."""
    return [
        str(executable),
        f"--user-data-dir={profile_dir}",
        "--remote-debugging-port=0",
        "--no-first-run",
        "--no-default-browser-check",
        *_MODE_FLAGS[mode],
        start_url,
    ]


def is_login_profile_in_use(profile_dir: Path, platform: str = sys.platform) -> bool:
    """True when a live browser holds the lock of the login profile."""
    if platform == "win32":
        lockfile = profile_dir / "lockfile"
        if not lockfile.exists():
            return False
        try:
            os.remove(lockfile)
        except PermissionError:
            return True
        except OSError:
            return False
        return False  # removable lock file: stale
    singleton_lock = profile_dir / "SingletonLock"
    try:
        target = os.readlink(singleton_lock)
    except OSError:
        return False
    host, _, pid_text = target.rpartition("-")
    if host != socket.gethostname() or not pid_text.isdigit():
        return False
    try:
        os.kill(int(pid_text), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class RunningLoginBrowser:
    """A browser process started by lingotube, with its DevTools websocket URL."""

    def __init__(
        self,
        websocket_url: str,
        process: asyncio.subprocess.Process,
        close_wait: float = BROWSER_CLOSE_WAIT,
        terminate_wait: float = BROWSER_TERMINATE_WAIT,
    ) -> None:
        self.websocket_url = websocket_url
        self._process = process
        self._close_wait = close_wait
        self._terminate_wait = terminate_wait

    @property
    def has_exited(self) -> bool:
        return self._process.returncode is not None

    async def _wait_for_exit(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._process.wait(), timeout)
        except TimeoutError:
            return False
        return True

    async def shut_down(self, connection: DevToolsConnection | None) -> None:
        """Close the spawned browser: Browser.close, then terminate, then kill."""
        if self.has_exited:
            return
        if connection is not None:
            with suppress(DevToolsError):
                await close_browser(connection)
            if await self._wait_for_exit(self._close_wait):
                return
        if not self.has_exited:
            self._process.terminate()
            if await self._wait_for_exit(self._terminate_wait):
                return
        if not self.has_exited:
            self._process.kill()
            await self._wait_for_exit(self._terminate_wait)


def _read_websocket_url(port_file: Path) -> str | None:
    """Parse DevToolsActivePort; None while the file is missing or incomplete."""
    try:
        lines = port_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if len(lines) < 2 or not lines[0].strip().isdigit() or not lines[1].strip():
        return None
    return f"ws://127.0.0.1:{lines[0].strip()}{lines[1].strip()}"


def _profile_busy_error() -> ProfileBusyError:
    return ProfileBusyError(
        message="Профиль входа lingotube уже открыт.", hint=PROFILE_BUSY_HINT
    )


async def launch_login_browser(
    executable: Path,
    profile_dir: Path,
    mode: LaunchMode,
    start_url: str,
    spawn: Callable[
        ..., Awaitable[asyncio.subprocess.Process]
    ] = asyncio.create_subprocess_exec,
    port_file_timeout: float = 30.0,
) -> RunningLoginBrowser:
    """Start the browser in the login profile and wait for its DevTools endpoint."""
    if is_login_profile_in_use(profile_dir):
        raise _profile_busy_error()
    port_file = profile_dir / _DEVTOOLS_PORT_FILE_NAME
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
        port_file.unlink(missing_ok=True)
        process = await spawn(
            *browser_command_line(executable, profile_dir, mode, start_url),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        # No exception text: it may contain paths; the message is fixed.
        raise AuthError(
            message="Браузер не запустился.",
            hint="Проверьте установку Chrome или Edge и повторите `lingotube login`.",
        ) from None
    try:
        async with asyncio.timeout(port_file_timeout):
            while True:
                websocket_url = _read_websocket_url(port_file)
                if websocket_url is not None:
                    return RunningLoginBrowser(
                        websocket_url=websocket_url, process=process
                    )
                if process.returncode is not None:
                    break
                await asyncio.sleep(_PORT_FILE_POLL_INTERVAL)
    except TimeoutError:
        await RunningLoginBrowser(websocket_url="", process=process).shut_down(None)
        raise AuthError(
            message="Браузер не ответил вовремя.",
            hint="Повторите `lingotube login`.",
        ) from None
    except BaseException:
        await RunningLoginBrowser(websocket_url="", process=process).shut_down(None)
        raise

    if is_login_profile_in_use(profile_dir):
        raise _profile_busy_error()
    raise AuthError(
        message="Браузер не запустился.",
        hint="Проверьте установку Chrome или Edge и повторите `lingotube login`.",
    )
