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

PROFILE_BUSY_MESSAGE = "The lingotube login profile is open right now."
PROFILE_BUSY_HINT = "Close the lingotube sign-in window (or end its background browser process) and try again."
LOGIN_BROWSERS = ("chrome", "edge")
LaunchMode = Literal["headless", "offscreen"]

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
    """Find the installed executable of a browser.

    Args:
        browser: ``chrome`` or ``edge``.
        platform: Platform name, as in ``sys.platform``.
        env: Environment variables, used to find the Windows install folders.
        is_file: Function that checks whether a path is a file.
        which: Function that finds a command on the PATH (Linux).

    Returns:
        The path of the executable, or None if the browser is not installed.
    """
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
    """Find the first installed login browser: Chrome, then Edge.

    Args:
        platform: Platform name, as in ``sys.platform``.
        env: Environment variables, used to find the Windows install folders.
        is_file: Function that checks whether a path is a file.
        which: Function that finds a command on the PATH (Linux).

    Returns:
        The browser name and its executable, or None if neither is installed.
    """
    for browser in LOGIN_BROWSERS:
        executable = find_browser_executable(browser, platform=platform, env=env, is_file=is_file, which=which)
        if executable is not None:
            return browser, executable
    return None


def browser_command_line(executable: Path, profile_dir: Path, mode: LaunchMode, start_url: str) -> list[str]:
    """Build the argument list that starts the login browser.

    No shell is used and no automation flags are set.

    Args:
        executable: Browser executable.
        profile_dir: Login profile folder.
        mode: ``headless`` or ``offscreen``.
        start_url: Page to open first.

    Returns:
        The arguments, the executable first.
    """
    return [
        str(executable),
        f"--user-data-dir={profile_dir}",
        "--remote-debugging-port=0",
        "--no-first-run",
        "--no-default-browser-check",
        *_MODE_FLAGS[mode],
        start_url,
    ]


def sign_in_window_command_line(executable: Path, profile_dir: Path, login_url: str) -> list[str]:
    """Build the argument list that opens the sign-in window.

    There is no ``--remote-debugging-*`` flag and no automation flag. A browser with a
    debugging port has ``navigator.webdriver`` set, and Google then refuses the sign-in.

    Args:
        executable: Browser executable.
        profile_dir: Login profile folder.
        login_url: Sign-in page to open.

    Returns:
        The arguments, the executable first.
    """
    return [
        str(executable),
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        login_url,
    ]


def is_login_profile_in_use(profile_dir: Path, platform: str = sys.platform) -> bool:
    """Check whether a live browser holds the lock of the login profile.

    On Windows a lock file that can be removed is treated as stale and is deleted, so this
    check can remove a file.

    Args:
        profile_dir: Login profile folder.
        platform: Platform name, as in ``sys.platform``.

    Returns:
        True if a live browser uses the profile, otherwise False.
    """
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
    """A browser process started by lingotube, with the URL of its DevTools WebSocket.

    Attributes:
        websocket_url: WebSocket URL of the DevTools endpoint.
    """

    def __init__(
        self,
        websocket_url: str,
        process: asyncio.subprocess.Process,
        close_wait: float = BROWSER_CLOSE_WAIT,
        terminate_wait: float = BROWSER_TERMINATE_WAIT,
    ) -> None:
        """Wrap a started browser process.

        Args:
            websocket_url: WebSocket URL of the DevTools endpoint.
            process: The browser process.
            close_wait: Seconds to wait after ``Browser.close`` before terminating.
            terminate_wait: Seconds to wait after terminating before killing.
        """
        self.websocket_url = websocket_url
        self._process = process
        self._close_wait = close_wait
        self._terminate_wait = terminate_wait

    @property
    def has_exited(self) -> bool:
        """Return True once the browser process has exited.

        Returns:
            True if the process has exited.
        """
        return self._process.returncode is not None

    async def _wait_for_exit(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._process.wait(), timeout)
        except TimeoutError:
            return False
        return True

    async def shut_down(self, connection: DevToolsConnection | None) -> None:
        """Close the browser that lingotube started: ``Browser.close``, then terminate, then kill.

        Args:
            connection: Open DevTools connection, or None to skip ``Browser.close``.
        """
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


def profile_busy_error() -> ProfileBusyError:
    """Return the error for a login profile that is open in another window.

    Returns:
        The ProfileBusyError with its message and hint.
    """
    return ProfileBusyError(message=PROFILE_BUSY_MESSAGE, hint=PROFILE_BUSY_HINT)


async def shut_down_spawned_process(process: asyncio.subprocess.Process) -> None:
    """Terminate, then kill, a browser process that lingotube started.

    No DevTools connection is needed.

    Args:
        process: The browser process.
    """
    await RunningLoginBrowser(websocket_url="", process=process).shut_down(None)


async def launch_login_browser(
    executable: Path,
    profile_dir: Path,
    mode: LaunchMode,
    start_url: str,
    spawn: Callable[..., Awaitable[asyncio.subprocess.Process]] = asyncio.create_subprocess_exec,
    port_file_timeout: float = 30.0,
) -> RunningLoginBrowser:
    """Start the browser in the login profile and wait for its DevTools endpoint.

    Args:
        executable: Browser executable.
        profile_dir: Login profile folder.
        mode: ``headless`` or ``offscreen``.
        start_url: Page to open first.
        spawn: Function that starts the process.
        port_file_timeout: Seconds to wait for the DevTools port file.

    Returns:
        The running browser.

    Raises:
        ProfileBusyError: If the profile is already in use.
        AuthError: If the browser does not start or does not answer in time.
    """
    if is_login_profile_in_use(profile_dir):
        raise profile_busy_error()
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
            message="The browser did not start.",
            hint="Check that Chrome or Edge is installed, then run `lingotube login` again.",
        ) from None
    try:
        async with asyncio.timeout(port_file_timeout):
            while True:
                websocket_url = _read_websocket_url(port_file)
                if websocket_url is not None:
                    return RunningLoginBrowser(websocket_url=websocket_url, process=process)
                if process.returncode is not None:
                    break
                await asyncio.sleep(_PORT_FILE_POLL_INTERVAL)
    except TimeoutError:
        await shut_down_spawned_process(process)
        raise AuthError(
            message="The browser did not respond in time.",
            hint="Run `lingotube login` again.",
        ) from None
    except BaseException:
        await shut_down_spawned_process(process)
        raise

    if is_login_profile_in_use(profile_dir):
        raise profile_busy_error()
    raise AuthError(
        message="The browser did not start.",
        hint="Check that Chrome or Edge is installed, then run `lingotube login` again.",
    )


class SignInWindow:
    """A visible browser process that lingotube started for the person to sign in."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        """Wrap the sign-in window process.

        Args:
            process: The browser process.
        """
        self._process = process

    @property
    def has_exited(self) -> bool:
        """Return True once the sign-in window has been closed.

        Returns:
            True if the process has exited.
        """
        return self._process.returncode is not None

    async def close(self) -> None:
        """Terminate, then kill, the sign-in window process. Does nothing once it has exited."""
        await shut_down_spawned_process(self._process)


async def launch_sign_in_window(
    executable: Path,
    profile_dir: Path,
    login_url: str,
    spawn: Callable[..., Awaitable[asyncio.subprocess.Process]] = asyncio.create_subprocess_exec,
) -> SignInWindow:
    """Clear the login profile and open the sign-in window without a debugging port.

    Args:
        executable: Browser executable.
        profile_dir: Login profile folder. It is emptied first.
        login_url: Sign-in page to open.
        spawn: Function that starts the process.

    Returns:
        The sign-in window.

    Raises:
        ProfileBusyError: If the profile is already in use or cannot be removed.
        AuthError: If the profile cannot be prepared or the browser does not start.
    """
    if is_login_profile_in_use(profile_dir):
        raise profile_busy_error()
    try:
        if profile_dir.exists():
            shutil.rmtree(profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        # No exception text: it may contain paths.
        raise profile_busy_error() from None
    except OSError:
        raise AuthError(
            message="Could not prepare the lingotube login profile.",
            hint="Check the permissions of the profile folder and run `lingotube login` again.",
        ) from None
    try:
        process = await spawn(
            *sign_in_window_command_line(executable, profile_dir, login_url),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        raise AuthError(
            message="The browser did not start.",
            hint="Check that Chrome or Edge is installed, then run `lingotube login` again.",
        ) from None
    return SignInWindow(process)
