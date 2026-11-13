import asyncio
import os
import socket
import sys
from pathlib import Path

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
    found = find_browser_executable(
        "chrome",
        platform="win32",
        env={"PROGRAMFILES": r"C:\PF"},
        is_file={WINDOWS_CHROME}.__contains__,
        which=lambda name: None,
    )
    assert found == WINDOWS_CHROME


def test_finds_edge_via_which_on_linux():
    found = find_browser_executable(
        "edge",
        platform="linux",
        env={},
        is_file=lambda path: False,
        which=lambda name: (
            "/usr/bin/microsoft-edge-stable"
            if name == "microsoft-edge-stable"
            else None
        ),
    )
    assert found == Path("/usr/bin/microsoft-edge-stable")


def test_returns_none_when_not_installed():
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
    assert find_first_installed_browser(
        is_file={WINDOWS_EDGE}.__contains__, **common
    ) == ("edge", WINDOWS_EDGE)
    assert find_first_installed_browser(is_file=lambda p: False, **common) is None


def test_command_line_has_no_automation_or_address_flags():
    args = browser_command_line(Path("chrome"), Path("p"), "headless", "https://x/")
    assert not any(
        a.startswith(("--enable-automation", "--remote-debugging-address"))
        for a in args
    )
    assert "--remote-debugging-port=0" in args and args[-1] == "https://x/"


def test_command_line_headless_and_offscreen_flags():
    headless = browser_command_line(Path("c"), Path("p"), "headless", "u")
    offscreen = browser_command_line(Path("c"), Path("p"), "offscreen", "u")
    window = browser_command_line(Path("c"), Path("p"), "window", "u")
    assert "--headless" in headless
    assert "--window-position=-32000,-32000" in offscreen
    assert "--window-size=1024,768" in offscreen
    assert "--headless" not in window
    assert "--window-position=-32000,-32000" not in window


def test_profile_path_with_spaces_and_cyrillic_is_one_argument():
    profile = Path(r"C:\Users\Антон Иванов\AppData\Local\lingotube\login-profile")
    args = browser_command_line(Path("chrome.exe"), profile, "window", "about:blank")
    assert f"--user-data-dir={profile}" in args


def test_profile_not_in_use_without_lock(tmp_path):
    assert not is_login_profile_in_use(tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX lock")
def test_profile_in_use_when_singleton_lock_points_to_live_pid(tmp_path):
    (tmp_path / "SingletonLock").symlink_to(f"{socket.gethostname()}-{os.getpid()}")
    assert is_login_profile_in_use(tmp_path, platform="linux")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX lock")
def test_profile_not_in_use_when_singleton_lock_points_to_other_host(tmp_path):
    (tmp_path / "SingletonLock").symlink_to(f"not-{socket.gethostname()}-{os.getpid()}")
    assert not is_login_profile_in_use(tmp_path, platform="linux")


def test_windows_removable_lockfile_is_stale(tmp_path):
    (tmp_path / "lockfile").write_text("")
    assert not is_login_profile_in_use(tmp_path, platform="win32")


def test_windows_unremovable_lockfile_means_in_use(tmp_path, monkeypatch):
    (tmp_path / "lockfile").write_text("")

    def refuse_removal(path):
        raise PermissionError

    monkeypatch.setattr(login_browser.os, "remove", refuse_removal)
    assert is_login_profile_in_use(tmp_path, platform="win32")


class FakeProcess:
    def __init__(self, exits_on_terminate=True, exits_on_kill=True, returncode=None):
        self.returncode = returncode
        self.exits_on_terminate = exits_on_terminate
        self.exits_on_kill = exits_on_kill
        self.calls: list[str] = []

    async def wait(self):
        while self.returncode is None:
            await asyncio.sleep(0.01)
        return self.returncode

    def terminate(self):
        self.calls.append("terminate")
        if self.exits_on_terminate:
            self.returncode = 0

    def kill(self):
        self.calls.append("kill")
        if self.exits_on_kill:
            self.returncode = -9


class FakeConnection:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.commands: list[str] = []

    async def send_command(self, method, params=None):
        self.commands.append(method)
        if self.error:
            raise self.error
        return {}


def spawn_writing_port_file(profile_dir: Path, process: FakeProcess):
    captured = {}

    async def spawn(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        (profile_dir / "DevToolsActivePort").write_text(
            "53211\n/devtools/browser/abc\n"
        )
        return process

    spawn.captured = captured
    return spawn


async def test_launch_reads_devtools_port_file(tmp_path):
    process = FakeProcess()
    spawn = spawn_writing_port_file(tmp_path, process)
    browser = await launch_login_browser(
        executable=Path("chrome"),
        profile_dir=tmp_path,
        mode="window",
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
        mode="window",
        start_url="u",
        spawn=spawn,
    )
    assert seen_during_spawn["stale_present"] is False
    assert browser.websocket_url.endswith(":2/devtools/browser/new")


async def test_launch_raises_profile_busy_when_busy_before_launch(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(login_browser, "is_login_profile_in_use", lambda *a, **k: True)

    async def spawn(*args, **kwargs):
        raise AssertionError("must not spawn")

    with pytest.raises(ProfileBusyError) as info:
        await launch_login_browser(
            executable=Path("chrome"),
            profile_dir=tmp_path,
            mode="window",
            start_url="u",
            spawn=spawn,
        )
    assert info.value.hint == PROFILE_BUSY_HINT
    assert info.value.exit_code == 1


async def test_launch_raises_profile_busy_when_process_exits_and_profile_locked(
    tmp_path, monkeypatch
):
    answers = iter([False, True])
    monkeypatch.setattr(
        login_browser, "is_login_profile_in_use", lambda *a, **k: next(answers)
    )

    async def spawn(*args, **kwargs):
        return FakeProcess(returncode=0)

    with pytest.raises(ProfileBusyError):
        await launch_login_browser(
            executable=Path("chrome"),
            profile_dir=tmp_path,
            mode="window",
            start_url="u",
            spawn=spawn,
        )


async def test_launch_raises_auth_error_when_process_exits_without_lock(tmp_path):
    async def spawn(*args, **kwargs):
        return FakeProcess(returncode=1)

    with pytest.raises(AuthError) as info:
        await launch_login_browser(
            executable=Path("chrome"),
            profile_dir=tmp_path,
            mode="window",
            start_url="u",
            spawn=spawn,
        )
    assert info.value.message == "Браузер не запустился."


async def test_launch_timeout_kills_own_process(tmp_path):
    process = FakeProcess()

    async def spawn(*args, **kwargs):
        return process

    with pytest.raises(AuthError):
        await launch_login_browser(
            executable=Path("chrome"),
            profile_dir=tmp_path,
            mode="window",
            start_url="u",
            spawn=spawn,
            port_file_timeout=0.3,
        )
    assert "terminate" in process.calls


async def test_shut_down_closes_browser_via_devtools():
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


async def test_shut_down_is_safe_twice_and_after_exit():
    process = FakeProcess(returncode=0)
    browser = RunningLoginBrowser(websocket_url="ws://x", process=process)
    await browser.shut_down(None)
    await browser.shut_down(None)
    assert process.calls == []


async def test_launch_maps_spawn_os_error_to_auth_error_without_exception_text(
    tmp_path,
):
    async def spawn(*args, **kwargs):
        raise FileNotFoundError("LEAKME-secret-path")

    with pytest.raises(AuthError) as info:
        await launch_login_browser(
            executable=Path("chrome"),
            profile_dir=tmp_path,
            mode="window",
            start_url="u",
            spawn=spawn,
        )
    assert info.value.message == "Браузер не запустился."
    assert "LEAKME" not in info.value.message + (info.value.hint or "")
    assert info.value.__cause__ is None


LOGIN_URL = "https://accounts.google.com/ServiceLogin?service=youtube"


def test_sign_in_window_command_line_has_no_debugging_or_automation_flags():
    args = sign_in_window_command_line(Path("chrome"), Path("p"), LOGIN_URL)
    assert not any(
        a.startswith(("--remote-debugging", "--enable-automation")) for a in args
    )
    assert "--disable-background-mode" in args
    assert "--no-first-run" in args
    assert "--no-default-browser-check" in args
    assert "--user-data-dir=p" in args
    assert args[0] == "chrome" and args[-1] == LOGIN_URL


def test_sign_in_window_profile_with_spaces_and_cyrillic_is_one_argument():
    profile = Path(r"C:\Users\Антон Иванов\AppData\Local\lingotube\login-profile")
    args = sign_in_window_command_line(Path("chrome.exe"), profile, LOGIN_URL)
    assert f"--user-data-dir={profile}" in args


async def test_sign_in_window_deletes_profile_before_launch(tmp_path):
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


async def test_sign_in_window_profile_locked_during_delete_is_profile_busy(
    tmp_path, monkeypatch
):
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


async def test_sign_in_window_busy_profile_is_checked_before_delete(
    tmp_path, monkeypatch
):
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
