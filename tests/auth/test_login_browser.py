"""Tests of the login browser: finding it, command lines, profile lock and launch."""

import asyncio
import os
import socket
import sys
from pathlib import Path
from typing import get_args

import pytest

from lingotube.auth import login_browser
from lingotube.auth.devtools import DevToolsError
from lingotube.auth.login_browser import (
    PROFILE_BUSY_HINT,
    RunningLoginBrowser,
    browser_command_line,
    find_browser_executable,
    find_first_installed_browser,
    is_login_profile_in_use,
    launch_login_browser,
    launch_sign_in_window,
    sign_in_window_command_line,
)
from lingotube.errors import AuthError, ProfileBusyError

WINDOWS_CHROME = Path(r"C:\PF\Google\Chrome\Application\chrome.exe")
WINDOWS_EDGE = Path(r"C:\PF\Microsoft\Edge\Application\msedge.exe")


def test_finds_chrome_in_program_files_on_windows():
    """Check that Chrome is found in Program Files on Windows."""
    found = find_browser_executable(
        "chrome",
        platform="win32",
        env={"PROGRAMFILES": r"C:\PF"},
        is_file={WINDOWS_CHROME}.__contains__,
        which=lambda name: None,
    )
    assert found == WINDOWS_CHROME


def test_finds_edge_via_which_on_linux():
    """Check that Edge is found with the PATH lookup on Linux."""
    found = find_browser_executable(
        "edge",
        platform="linux",
        env={},
        is_file=lambda path: False,
        which=lambda name: "/usr/bin/microsoft-edge-stable" if name == "microsoft-edge-stable" else None,
    )
    assert found == Path("/usr/bin/microsoft-edge-stable")


def test_returns_none_when_not_installed():
    """Check that a browser that is not installed gives None."""
    assert (
        find_browser_executable(
            "chrome",
            platform="linux",
            env={},
            is_file=lambda path: False,
            which=lambda name: None,
        )
        is None
    )


def test_first_installed_prefers_chrome_then_edge():
    """Check that Chrome is preferred to Edge when both are installed."""
    both = {WINDOWS_CHROME, WINDOWS_EDGE}
    common = {
        "platform": "win32",
        "env": {"PROGRAMFILES": r"C:\PF"},
        "which": lambda name: None,
    }
    assert find_first_installed_browser(is_file=both.__contains__, **common) == (
        "chrome",
        WINDOWS_CHROME,
    )
    assert find_first_installed_browser(is_file={WINDOWS_EDGE}.__contains__, **common) == ("edge", WINDOWS_EDGE)
    assert find_first_installed_browser(is_file=lambda p: False, **common) is None


def test_command_line_has_no_automation_or_address_flags():
    """Check that the login browser command line has no automation flags."""
    args = browser_command_line(Path("chrome"), Path("p"), "headless", "https://x/")
    assert not any(a.startswith(("--enable-automation", "--remote-debugging-address")) for a in args)
    assert "--remote-debugging-port=0" in args and args[-1] == "https://x/"


def test_command_line_headless_and_offscreen_flags():
    """Check that the headless and offscreen modes add their flags."""
    headless = browser_command_line(Path("c"), Path("p"), "headless", "u")
    offscreen = browser_command_line(Path("c"), Path("p"), "offscreen", "u")
    assert "--headless" in headless
    assert "--window-position=-32000,-32000" in offscreen
    assert "--window-size=1024,768" in offscreen
    assert "--headless" not in offscreen
    assert "--window-position=-32000,-32000" not in headless


def test_no_visible_window_launch_mode_with_debugging_port_exists():
    """Check that there is no visible-window launch mode with a debugging port."""
    assert set(get_args(login_browser.LaunchMode)) == {"headless", "offscreen"}
    with pytest.raises(KeyError):
        browser_command_line(Path("c"), Path("p"), "window", "u")


def test_profile_busy_hint_mentions_lingering_background_process():
    """Check that the profile-busy hint mentions a background process that is still running."""
    assert PROFILE_BUSY_HINT == (
        "Закройте окно входа lingotube (или завершите его фоновый процесс браузера) и повторите."
    )


def test_profile_path_with_spaces_and_cyrillic_is_one_argument():
    """Check that a profile path with spaces and Cyrillic letters stays one argument."""
    profile = Path(r"C:\Users\Антон Иванов\AppData\Local\lingotube\login-profile")
    args = browser_command_line(Path("chrome.exe"), profile, "headless", "about:blank")
    assert f"--user-data-dir={profile}" in args


def test_profile_not_in_use_without_lock(tmp_path):
    """Check that a profile without a lock is not in use."""
    assert not is_login_profile_in_use(tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX lock")
def test_profile_in_use_when_singleton_lock_points_to_live_pid(tmp_path):
    """Check that a profile is in use when its lock points to a live process."""
    (tmp_path / "SingletonLock").symlink_to(f"{socket.gethostname()}-{os.getpid()}")
    assert is_login_profile_in_use(tmp_path, platform="linux")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX lock")
def test_profile_not_in_use_when_singleton_lock_points_to_other_host(tmp_path):
    """Check that a lock from another host does not mark the profile as in use."""
    (tmp_path / "SingletonLock").symlink_to(f"not-{socket.gethostname()}-{os.getpid()}")
    assert not is_login_profile_in_use(tmp_path, platform="linux")


def test_lock_outside_the_login_profile_does_not_make_it_busy(tmp_path):
    # The person's own browser (another profile) holds its lock elsewhere.
    """Check that a lock outside the login profile does not make it busy."""
    (tmp_path / "lockfile").write_text("")
    profile = tmp_path / "login-profile"
    profile.mkdir()
    assert not is_login_profile_in_use(profile, platform="win32")
    assert (tmp_path / "lockfile").exists()


async def test_launch_starts_while_another_profile_is_locked(tmp_path):
    """Check that the launch works while another profile is locked."""
    (tmp_path / "lockfile").write_text("")
    profile = tmp_path / "login-profile"
    profile.mkdir()
    browser = await launch_login_browser(
        executable=Path("chrome"),
        profile_dir=profile,
        mode="headless",
        start_url="u",
        spawn=spawn_writing_port_file(profile, FakeProcess()),
    )
    assert browser.websocket_url.endswith("/devtools/browser/abc")


def test_windows_removable_lockfile_is_stale(tmp_path):
    """Check that a removable lock file on Windows is treated as stale."""
    (tmp_path / "lockfile").write_text("")
    assert not is_login_profile_in_use(tmp_path, platform="win32")


def test_windows_unremovable_lockfile_means_in_use(tmp_path, monkeypatch):
    """Check that a lock file that cannot be removed on Windows means the profile is in use."""
    (tmp_path / "lockfile").write_text("")

    def refuse_removal(path):
        raise PermissionError

    monkeypatch.setattr(login_browser.os, "remove", refuse_removal)
    assert is_login_profile_in_use(tmp_path, platform="win32")


class FakeProcess:
    """Fake browser process that records the terminate and kill calls."""

    def __init__(self, exits_on_terminate=True, exits_on_kill=True, returncode=None):
        """Create the fake process, which may or may not exit on terminate or kill.

        Args:
            exits_on_terminate: Whether terminate makes the process exit.
            exits_on_kill: Whether kill makes the process exit.
            returncode: Exit code, or None while the process runs.
        """
        self.returncode = returncode
        self.exits_on_terminate = exits_on_terminate
        self.exits_on_kill = exits_on_kill
        self.calls: list[str] = []

    async def wait(self):
        """Wait until the fake process exits.

        Returns:
            The exit code.
        """
        while self.returncode is None:
            await asyncio.sleep(0.01)
        return self.returncode

    def terminate(self):
        """Record a terminate request."""
        self.calls.append("terminate")
        if self.exits_on_terminate:
            self.returncode = 0

    def kill(self):
        """Record a kill request."""
        self.calls.append("kill")
        if self.exits_on_kill:
            self.returncode = -9


class FakeConnection:
    """Fake DevTools connection that records the commands it receives."""

    def __init__(self, error: Exception | None = None):
        """Create the fake connection.

        Args:
            error: Exception raised by every command, or None for normal replies.
        """
        self.error = error
        self.commands: list[str] = []

    async def send_command(self, method, params=None):
        """Record a command, then raise the configured error or return an empty result.

        Args:
            method: DevTools method name.
            params: Parameters of the command, or None.

        Returns:
            An empty result.
        """
        self.commands.append(method)
        if self.error:
            raise self.error
        return {}


def spawn_writing_port_file(profile_dir: Path, process: FakeProcess):
    """Build a fake process spawner that writes the DevTools port file into the profile folder.

    Args:
        profile_dir: Login profile folder where the port file is written.
        process: Fake process that the spawner returns.

    Returns:
        The fake spawner. It records the arguments it was called with.
    """
    captured = {}

    async def spawn(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        (profile_dir / "DevToolsActivePort").write_text("53211\n/devtools/browser/abc\n")
        return process

    spawn.captured = captured
    return spawn


async def test_launch_reads_devtools_port_file(tmp_path):
    """Check that the launch reads the DevTools port file."""
    process = FakeProcess()
    spawn = spawn_writing_port_file(tmp_path, process)
    browser = await launch_login_browser(
        executable=Path("chrome"),
        profile_dir=tmp_path,
        mode="headless",
        start_url="https://x/",
        spawn=spawn,
    )
    assert browser.websocket_url == "ws://127.0.0.1:53211/devtools/browser/abc"
    assert not browser.has_exited
    assert spawn.captured["args"][0] == "chrome"
    assert spawn.captured["kwargs"]["stdin"] == asyncio.subprocess.DEVNULL
    assert spawn.captured["kwargs"]["stdout"] == asyncio.subprocess.DEVNULL
    assert spawn.captured["kwargs"]["stderr"] == asyncio.subprocess.DEVNULL


async def test_launch_ignores_stale_port_file(tmp_path):
    """Check that an old port file is ignored."""
    (tmp_path / "DevToolsActivePort").write_text("1\n/devtools/browser/stale\n")
    process = FakeProcess()
    seen_during_spawn = {}

    async def spawn(*args, **kwargs):
        seen_during_spawn["stale_present"] = (tmp_path / "DevToolsActivePort").exists()
        (tmp_path / "DevToolsActivePort").write_text("2\n/devtools/browser/new\n")
        return process

    browser = await launch_login_browser(
        executable=Path("chrome"),
        profile_dir=tmp_path,
        mode="headless",
        start_url="u",
        spawn=spawn,
    )
    assert seen_during_spawn["stale_present"] is False
    assert browser.websocket_url.endswith(":2/devtools/browser/new")


async def test_launch_raises_profile_busy_when_busy_before_launch(tmp_path, monkeypatch):
    """Check that a busy profile before the launch raises ProfileBusyError."""
    monkeypatch.setattr(login_browser, "is_login_profile_in_use", lambda *a, **k: True)

    async def spawn(*args, **kwargs):
        raise AssertionError("must not spawn")

    with pytest.raises(ProfileBusyError) as info:
        await launch_login_browser(
            executable=Path("chrome"),
            profile_dir=tmp_path,
            mode="headless",
            start_url="u",
            spawn=spawn,
        )
    assert info.value.hint == PROFILE_BUSY_HINT
    assert info.value.exit_code == 1


async def test_launch_raises_profile_busy_when_process_exits_and_profile_locked(tmp_path, monkeypatch):
    """Check that ProfileBusyError is raised when the process exits and the profile stays locked."""
    spawned = []
    monkeypatch.setattr(
        login_browser, "is_login_profile_in_use", lambda *a, **k: bool(spawned)
    )  # free before the launch, locked once our process has started and exited

    async def spawn(*args, **kwargs):
        spawned.append(True)
        return FakeProcess(returncode=0)

    with pytest.raises(ProfileBusyError):
        await launch_login_browser(
            executable=Path("chrome"),
            profile_dir=tmp_path,
            mode="headless",
            start_url="u",
            spawn=spawn,
        )


async def test_launch_raises_auth_error_when_process_exits_without_lock(tmp_path):
    """Check that AuthError is raised when the process exits without a lock."""

    async def spawn(*args, **kwargs):
        return FakeProcess(returncode=1)

    with pytest.raises(AuthError) as info:
        await launch_login_browser(
            executable=Path("chrome"),
            profile_dir=tmp_path,
            mode="headless",
            start_url="u",
            spawn=spawn,
        )
    assert info.value.message == "Браузер не запустился."


async def test_launch_timeout_kills_own_process(tmp_path):
    """Check that a timed-out launch stops the browser that lingotube started."""
    process = FakeProcess()

    async def spawn(*args, **kwargs):
        return process

    with pytest.raises(AuthError) as info:
        await launch_login_browser(
            executable=Path("chrome"),
            profile_dir=tmp_path,
            mode="headless",
            start_url="u",
            spawn=spawn,
            port_file_timeout=0.3,
        )
    assert info.value.message == "Браузер не ответил вовремя."
    assert "terminate" in process.calls


async def test_launch_cancelled_while_waiting_terminates_own_process(tmp_path):
    """Check that a cancelled launch stops the browser that lingotube started."""
    process = FakeProcess()
    spawned = asyncio.Event()

    async def spawn(*args, **kwargs):
        spawned.set()
        return process

    task = asyncio.create_task(
        launch_login_browser(
            executable=Path("chrome"),
            profile_dir=tmp_path,
            mode="headless",
            start_url="u",
            spawn=spawn,
        )
    )
    await spawned.wait()
    await asyncio.sleep(0.05)  # let the launch reach its port-file polling loop
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.calls == ["terminate"]
    assert process.returncode is not None


async def test_shut_down_closes_browser_via_devtools():
    """Check that shutting down closes the browser through DevTools."""
    process = FakeProcess()
    connection = FakeConnection()

    async def close_then_exit(method, params=None):
        connection.commands.append(method)
        process.returncode = 0
        return {}

    connection.send_command = close_then_exit
    browser = RunningLoginBrowser(websocket_url="ws://x", process=process)
    await browser.shut_down(connection)
    assert connection.commands == ["Browser.close"]
    assert process.calls == []
    assert browser.has_exited


async def test_shut_down_terminates_after_close_timeout():
    """Check that the browser is terminated when it does not close in time."""
    process = FakeProcess(exits_on_terminate=False)
    connection = FakeConnection(error=DevToolsError("boom"))
    browser = RunningLoginBrowser(
        websocket_url="ws://x",
        process=process,
        close_wait=0.05,
        terminate_wait=0.05,
    )
    await browser.shut_down(connection)
    assert process.calls == ["terminate", "kill"]


async def test_shut_down_spawned_process_terminates_without_devtools():
    """Check that a spawned process is terminated without DevTools."""
    process = FakeProcess()
    await login_browser.shut_down_spawned_process(process)
    assert process.calls == ["terminate"]


async def test_shut_down_is_safe_twice_and_after_exit():
    """Check that shutting down twice, or after the exit, is safe."""
    process = FakeProcess(returncode=0)
    browser = RunningLoginBrowser(websocket_url="ws://x", process=process)
    await browser.shut_down(None)
    await browser.shut_down(None)
    assert process.calls == []


async def test_launch_maps_spawn_os_error_to_auth_error_without_exception_text(
    tmp_path,
):
    """Check that an OS error when starting the browser becomes AuthError without its text."""

    async def spawn(*args, **kwargs):
        raise FileNotFoundError("LEAKME-secret-path")

    with pytest.raises(AuthError) as info:
        await launch_login_browser(
            executable=Path("chrome"),
            profile_dir=tmp_path,
            mode="headless",
            start_url="u",
            spawn=spawn,
        )
    assert info.value.message == "Браузер не запустился."
    assert "LEAKME" not in info.value.message + (info.value.hint or "")
    assert info.value.__cause__ is None


LOGIN_URL = "https://accounts.google.com/ServiceLogin?service=youtube"


def test_sign_in_window_command_line_has_no_debugging_or_automation_flags():
    """Check that the sign-in window command line has no debugging or automation flags."""
    args = sign_in_window_command_line(Path("chrome"), Path("p"), LOGIN_URL)
    assert not any(a.startswith(("--remote-debugging", "--enable-automation")) for a in args)
    assert "--disable-background-mode" in args
    assert "--no-first-run" in args
    assert "--no-default-browser-check" in args
    assert "--user-data-dir=p" in args
    assert args[0] == "chrome" and args[-1] == LOGIN_URL


def test_sign_in_window_profile_with_spaces_and_cyrillic_is_one_argument():
    """Check that a sign-in profile path with spaces and Cyrillic letters stays one argument."""
    profile = Path(r"C:\Users\Антон Иванов\AppData\Local\lingotube\login-profile")
    args = sign_in_window_command_line(Path("chrome.exe"), profile, LOGIN_URL)
    assert f"--user-data-dir={profile}" in args


async def test_sign_in_window_deletes_profile_before_launch(tmp_path):
    """Check that the login profile is deleted before the sign-in window opens."""
    profile = tmp_path / "login-profile"
    (profile / "Default").mkdir(parents=True)
    (profile / "Default" / "Cookies").write_text("old account")
    seen = {}

    async def spawn(*args, **kwargs):
        seen["old_present"] = (profile / "Default" / "Cookies").exists()
        seen["args"] = args
        return FakeProcess()

    window = await launch_sign_in_window(
        executable=Path("chrome"),
        profile_dir=profile,
        login_url=LOGIN_URL,
        spawn=spawn,
    )
    assert seen["old_present"] is False
    assert not any(a.startswith("--remote-debugging") for a in seen["args"])
    assert not window.has_exited


async def test_sign_in_window_profile_locked_during_delete_is_profile_busy(tmp_path, monkeypatch):
    """Check that a profile locked during deletion raises ProfileBusyError."""

    def refuse(path, *args, **kwargs):
        raise PermissionError("LEAKME-path")

    monkeypatch.setattr(login_browser.shutil, "rmtree", refuse)
    (tmp_path / "p").mkdir()

    async def spawn(*args, **kwargs):
        raise AssertionError("must not spawn")

    with pytest.raises(ProfileBusyError) as info:
        await launch_sign_in_window(
            executable=Path("chrome"),
            profile_dir=tmp_path / "p",
            login_url=LOGIN_URL,
            spawn=spawn,
        )
    assert "LEAKME" not in str(info.value)
    assert info.value.hint == PROFILE_BUSY_HINT


async def test_sign_in_window_busy_profile_is_checked_before_delete(tmp_path, monkeypatch):
    """Check that a busy profile is detected before anything is deleted."""
    (tmp_path / "keep").write_text("x")
    monkeypatch.setattr(login_browser, "is_login_profile_in_use", lambda *a, **k: True)

    async def spawn(*args, **kwargs):
        raise AssertionError("must not spawn")

    with pytest.raises(ProfileBusyError):
        await launch_sign_in_window(
            executable=Path("chrome"),
            profile_dir=tmp_path,
            login_url=LOGIN_URL,
            spawn=spawn,
        )
    assert (tmp_path / "keep").exists()


async def test_sign_in_window_close_terminates_only_own_process(tmp_path):
    """Check that closing the sign-in window stops only the process lingotube started."""
    process = FakeProcess()

    async def spawn(*args, **kwargs):
        return process

    window = await launch_sign_in_window(
        executable=Path("chrome"),
        profile_dir=tmp_path / "p",
        login_url=LOGIN_URL,
        spawn=spawn,
    )
    await window.close()
    assert process.calls == ["terminate"]
    assert window.has_exited
