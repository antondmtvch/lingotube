"""`login` and `logout`: sign in to YouTube in a lingotube-owned browser profile.

Cookie values never reach the output: the commands report only counts and paths.
"""

import asyncio
import shutil

from lingotube.auth.login_browser import (
    LOGIN_BROWSERS,
    PROFILE_BUSY_HINT,
    is_login_profile_in_use,
)
from lingotube.config import forget_remembered_cookie_sources
from lingotube.errors import AuthError, ProfileBusyError, UsageError

COOKIES_FILE_ENV = "LINGOTUBE_COOKIES_FILE"
ENV_OVERRIDES_LOGIN_WARNING = (
    f"Переменная {COOKIES_FILE_ENV} задана и важнее входа lingotube; "
    "уберите её, чтобы использовать вход."
)


def _profile_busy_error() -> ProfileBusyError:
    return ProfileBusyError(
        message="Профиль входа lingotube сейчас открыт.",
        hint=PROFILE_BUSY_HINT,
    )


def _remove_profile_directory(profile_dir) -> bool:
    """True if the directory existed and was removed; PermissionError means it is in use."""
    if not profile_dir.exists():
        return False
    try:
        shutil.rmtree(profile_dir)
    except PermissionError:
        raise _profile_busy_error() from None
    return True


def register(
    app,
    get_context,
) -> None:
    """Adds the `login` and `logout` commands."""
    from typing import Annotated

    import typer

    from lingotube import commands as c

    LoginBrowserOpt = Annotated[
        str | None,
        typer.Option(
            default="--browser",
            help=f"Браузер для входа: {', '.join(LOGIN_BROWSERS)}; по умолчанию первый установленный.",
        ),
    ]

    @app.command(
        name="login",
        help="Войти в YouTube в отдельном профиле Chrome или Edge; cookies сохраняются для lingotube.",
    )
    def login(
        browser: LoginBrowserOpt = None,
        json_: c.JsonOpt = False,
    ) -> None:
        async def body(
            ctx: c.AppContext,
            video_id: str | None,
        ) -> c.Outcome:
            if browser is not None and browser not in LOGIN_BROWSERS:
                raise UsageError(
                    message=f"Неизвестный браузер: {browser}.",
                    hint=f"Доступны: {', '.join(LOGIN_BROWSERS)}.",
                )
            container = ctx.container
            if browser is None:
                found = container.browser_finder()()
                browser_name, executable = found if found is not None else (None, None)
            else:
                browser_name = browser
                executable = container.single_browser_finder()(browser)
            if executable is None:
                raise AuthError(
                    message="Не найден Chrome или Edge.",
                    hint=(
                        "Установите Chrome или Edge либо войдите в YouTube в Firefox; "
                        "запасной путь — файл cookies.txt (см. README)."
                    ),
                )
            paths = container.login_paths()
            if await asyncio.to_thread(is_login_profile_in_use, paths.profile_dir):
                raise _profile_busy_error()
            sign_in = container.sign_in_flow()
            saved = await sign_in(
                browser=browser_name,
                executable=executable,
                paths=paths,
                store=container.login_store(),
                notify=container.warn(),
            )
            forgotten: list[str] = []
            if ctx.settings_path is not None:
                forgotten = await forget_remembered_cookie_sources(
                    settings_path=ctx.settings_path
                )
            warnings = (
                (ENV_OVERRIDES_LOGIN_WARNING,)
                if container.env().get(COOKIES_FILE_ENV)
                else ()
            )
            text = f"Вход выполнен ({browser_name}). Cookies сохранены: {paths.cookies_file}."
            if forgotten:
                text += f"\nИз настроек убраны: {', '.join(forgotten)}."
            return c.Outcome(
                result={
                    "browser": browser_name,
                    "cookies_count": len(saved.cookies),
                    "cookies_path": str(paths.cookies_file),
                    "forgotten_settings": forgotten,
                },
                text=text,
                warnings=warnings,
            )

        c.execute(
            get_context=get_context,
            common=c.Common(json=json_),
            video=None,
            body=body,
        )

    @app.command(
        name="logout",
        help="Удалить профиль входа и сохранённые cookies lingotube.",
    )
    def logout(
        json_: c.JsonOpt = False,
    ) -> None:
        async def body(
            ctx: c.AppContext,
            video_id: str | None,
        ) -> c.Outcome:
            container = ctx.container
            paths = container.login_paths()
            if await asyncio.to_thread(is_login_profile_in_use, paths.profile_dir):
                raise _profile_busy_error()
            cookies_removed = await container.login_store().delete()
            profile_removed = await asyncio.to_thread(
                _remove_profile_directory,
                paths.profile_dir,
            )
            removed = cookies_removed or profile_removed
            return c.Outcome(
                result={"removed": removed},
                text=(
                    "Профиль входа и cookies lingotube удалены."
                    if removed
                    else "Нечего удалять: вход через lingotube login не выполнялся."
                ),
            )

        c.execute(
            get_context=get_context,
            common=c.Common(json=json_),
            video=None,
            body=body,
        )
