import io
import json
from pathlib import Path

from dependency_injector import providers

from lingotube import cli
from lingotube.auth.base import EXPORT_HINT, LOGIN_HINT
from lingotube.auth.login_browser import PROFILE_BUSY_HINT
from lingotube.auth.login_store import SavedLogin
from lingotube.commands import AppContext
from lingotube.config import LoginPaths, Settings
from lingotube.container import build_container
from lingotube.errors import ProfileBusyError

LEAK = "LEAKME"
EXECUTABLE = Path("chrome-fake")


class LoginHarness:
    def __init__(
        self,
        tmp_path: Path,
        *,
        env=None,
        installed: tuple[str, Path] | None = ("chrome", EXECUTABLE),
        flow_error: Exception | None = None,
        has_settings_path: bool = True,
    ) -> None:
        self.tmp = tmp_path
        self.env = env or {}
        self.installed = installed
        self.flow_error = flow_error
        self.has_settings_path = has_settings_path
        self.settings_path = tmp_path / "settings.toml"
        self.paths = LoginPaths(
            profile_dir=tmp_path / "login-profile",
            cookies_file=tmp_path / "login-cookies.json",
        )
        self.flow_calls: list[str] = []

    async def fake_sign_in(
        self,
        browser,
        executable,
        paths,
        store,
        notify,
    ) -> SavedLogin:
        self.flow_calls.append(browser)
        if self.flow_error is not None:
            raise self.flow_error
        saved = SavedLogin(
            browser=browser,
            cookies={"SAPISID": LEAK, "HSID": LEAK},
        )
        await store.write(saved)
        return saved

    def factory(self, out, err) -> AppContext:
        container = build_container(
            settings=Settings(),
            env=self.env,
            cache_dir=self.tmp / "cache",
            login_paths=self.paths,
            err=err,
        )
        container.sign_in_flow.override(providers.Object(self.fake_sign_in))
        container.browser_finder.override(providers.Object(lambda: self.installed))
        container.single_browser_finder.override(
            providers.Object(
                lambda browser: self.installed[1] if self.installed and self.installed[0] == browser else None
            )
        )
        return AppContext(
            container=container,
            out=out,
            err=err,
            cwd=self.tmp,
            settings_path=self.settings_path if self.has_settings_path else None,
        )

    def run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = cli.run(
            argv=list(argv),
            out=out,
            err=err,
            context_factory=self.factory,
        )
        return code, out.getvalue(), err.getvalue()


def test_login_saves_and_reports_without_cookie_values(tmp_path):
    h = LoginHarness(tmp_path)
    code, out, err = h.run("login")
    assert code == 0, err
    assert LEAK not in out + err
    assert "Вход выполнен (chrome)" in out
    assert h.paths.cookies_file.is_file()


def test_login_json_envelope(tmp_path):
    h = LoginHarness(tmp_path)
    code, out, err = h.run("login", "--json")
    assert code == 0, err
    envelope = json.loads(out)
    assert set(envelope["result"]) == {
        "browser",
        "cookies_count",
        "cookies_path",
        "forgotten_settings",
    }
    assert envelope["result"]["browser"] == "chrome"
    assert envelope["result"]["cookies_count"] == 2
    assert envelope["result"]["cookies_path"] == str(h.paths.cookies_file)
    assert LEAK not in out + err


def test_login_forgets_remembered_cookies_file_and_browser(tmp_path):
    h = LoginHarness(tmp_path)
    h.settings_path.write_text(
        'cookies_file = "c.txt"\nbrowser = "firefox"\nlang = "ru"\n',
        encoding="utf-8",
    )
    code, out, err = h.run("login", "--json")
    assert code == 0, err
    assert set(json.loads(out)["result"]["forgotten_settings"]) == {
        "cookies_file",
        "browser",
    }
    remaining = h.settings_path.read_text(encoding="utf-8")
    assert "cookies_file" not in remaining and "browser" not in remaining
    assert 'lang = "ru"' in remaining


def test_login_warns_when_env_cookies_file_is_set(tmp_path):
    h = LoginHarness(tmp_path, env={"LINGOTUBE_COOKIES_FILE": "x.txt"})
    code, out, err = h.run("login")
    assert code == 0, err
    assert "LINGOTUBE_COOKIES_FILE" in err and "важнее входа" in err


def test_login_without_settings_file_path_skips_settings_cleanup(tmp_path):
    h = LoginHarness(tmp_path, has_settings_path=False)
    code, out, err = h.run("login", "--json")
    assert code == 0, err
    envelope = json.loads(out)
    assert envelope["result"]["forgotten_settings"] == []
    assert envelope["warnings"] == []


def test_login_empty_env_cookies_file_does_not_warn(tmp_path):
    h = LoginHarness(tmp_path, env={"LINGOTUBE_COOKIES_FILE": ""})
    code, out, err = h.run("login")
    assert code == 0, err
    assert "LINGOTUBE_COOKIES_FILE" not in err


def test_login_settings_write_os_error_is_a_warning_not_an_error(tmp_path, monkeypatch):
    h = LoginHarness(tmp_path)

    async def read_only_settings(settings_path):
        raise PermissionError("LEAKME-path")

    monkeypatch.setattr(
        "lingotube.login_commands.forget_remembered_cookie_sources",
        read_only_settings,
    )
    code, out, err = h.run("login", "--json")
    assert code == 0, err
    assert any("настроек" in warning for warning in json.loads(out)["warnings"])
    assert LEAK not in out + err
    assert h.paths.cookies_file.is_file()


def test_login_busy_profile_is_checked_before_the_flow_starts(tmp_path, monkeypatch):
    h = LoginHarness(tmp_path)
    monkeypatch.setattr(
        "lingotube.login_commands.is_login_profile_in_use",
        lambda profile_dir: True,
    )
    code, out, err = h.run("login")
    assert code == 1
    assert "Закройте окно входа" in err
    assert h.flow_calls == []


def test_login_explicit_browser_that_is_not_installed_is_exit_4(tmp_path):
    h = LoginHarness(tmp_path, installed=("chrome", EXECUTABLE))
    code, out, err = h.run("login", "--browser", "edge")
    assert code == 4
    assert "Не найден Chrome или Edge." in err
    assert h.flow_calls == []


def test_login_unknown_browser_is_usage_error(tmp_path):
    h = LoginHarness(tmp_path)
    code, out, err = h.run("login", "--browser", "firefox")
    assert code == 2
    assert "Неизвестный браузер: firefox." in err
    assert h.flow_calls == []


def test_login_explicit_browser_is_passed_to_the_flow(tmp_path):
    h = LoginHarness(tmp_path, installed=("edge", EXECUTABLE))
    code, out, err = h.run("login", "--browser", "edge")
    assert code == 0, err
    assert h.flow_calls == ["edge"]


def test_login_no_browser_installed_is_exit_4(tmp_path):
    h = LoginHarness(tmp_path, installed=None)
    code, out, err = h.run("login")
    assert code == 4
    assert "Не найден Chrome или Edge." in err
    assert h.flow_calls == []


def test_login_profile_busy_is_exit_1_with_close_hint(tmp_path):
    h = LoginHarness(
        tmp_path,
        flow_error=ProfileBusyError(
            message="Профиль входа lingotube сейчас открыт.",
            hint=PROFILE_BUSY_HINT,
        ),
    )
    code, out, err = h.run("login")
    assert code == 1
    assert "Закройте окно входа" in err


def test_logout_removes_profile_and_cookies(tmp_path):
    h = LoginHarness(tmp_path)
    h.paths.profile_dir.mkdir()
    (h.paths.profile_dir / "Cookies").write_text("x", encoding="utf-8")
    h.paths.cookies_file.write_text("{}", encoding="utf-8")
    code, out, err = h.run("logout", "--json")
    assert code == 0, err
    assert json.loads(out)["result"] == {"removed": True}
    assert not h.paths.profile_dir.exists()
    assert not h.paths.cookies_file.exists()


def test_logout_with_nothing_is_success(tmp_path):
    h = LoginHarness(tmp_path)
    code, out, err = h.run("logout")
    assert code == 0, err
    assert "Нечего удалять" in out


def test_logout_busy_profile_is_exit_1(tmp_path, monkeypatch):
    h = LoginHarness(tmp_path)
    h.paths.profile_dir.mkdir()
    monkeypatch.setattr(
        "lingotube.login_commands.is_login_profile_in_use",
        lambda profile_dir: True,
    )
    code, out, err = h.run("logout")
    assert code == 1
    assert "Закройте окно входа" in err
    assert h.paths.profile_dir.exists()


def test_logout_permission_error_while_removing_is_exit_1(tmp_path, monkeypatch):
    h = LoginHarness(tmp_path)
    h.paths.profile_dir.mkdir()

    def locked(path):
        raise PermissionError

    monkeypatch.setattr("lingotube.login_commands.shutil.rmtree", locked)
    code, out, err = h.run("logout")
    assert code == 1


def test_logout_other_os_error_while_removing_profile_is_fixed_text_exit_1(tmp_path, monkeypatch):
    h = LoginHarness(tmp_path)
    h.paths.profile_dir.mkdir()

    def broken(path):
        raise OSError("LEAKME-path")

    monkeypatch.setattr("lingotube.login_commands.shutil.rmtree", broken)
    code, out, err = h.run("logout")
    assert code == 1
    assert "LEAKME" not in err
    assert "Не удалось удалить" in err
    assert "Внутренняя ошибка" not in err


def test_logout_permission_error_on_cookies_file_is_profile_busy(tmp_path, monkeypatch):
    h = LoginHarness(tmp_path)
    h.paths.cookies_file.write_text("{}", encoding="utf-8")

    def locked(self, *args, **kwargs):
        raise PermissionError("LEAKME-path")

    monkeypatch.setattr("pathlib.Path.unlink", locked)
    code, out, err = h.run("logout")
    assert code == 1
    assert "Закройте окно входа" in err
    assert "LEAKME" not in err


def test_logout_other_os_error_on_cookies_file_is_fixed_text(tmp_path, monkeypatch):
    h = LoginHarness(tmp_path)
    h.paths.cookies_file.write_text("{}", encoding="utf-8")

    def broken(self, *args, **kwargs):
        raise OSError("LEAKME-path")

    monkeypatch.setattr("pathlib.Path.unlink", broken)
    code, out, err = h.run("logout")
    assert code == 1
    assert "Не удалось удалить" in err
    assert "LEAKME" not in err


def test_login_settings_cleanup_failure_is_a_warning_not_an_error(tmp_path):
    h = LoginHarness(tmp_path)
    h.settings_path.write_text("this is = = not toml\n", encoding="utf-8")
    code, out, err = h.run("login", "--json")
    assert code == 0, err
    result = json.loads(out)["result"]
    assert result["forgotten_settings"] == []
    assert h.paths.cookies_file.is_file()
    assert any("настроек" in warning for warning in json.loads(out)["warnings"])
    assert LEAK not in out + err


def test_export_hint_starts_with_login():
    assert EXPORT_HINT.startswith(LOGIN_HINT)
    assert "инкогнито" in EXPORT_HINT
