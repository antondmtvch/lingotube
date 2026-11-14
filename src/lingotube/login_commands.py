"""`login` and `logout`: sign in to YouTube in a lingotube-owned browser profile.

Cookie values never reach the output: the commands report only counts and paths.
"""

import asyncio
import shutil
from pathlib import Path

from lingotube.auth.login_browser import (
    LOGIN_BROWSERS,
    is_login_profile_in_use,
    profile_busy_error,
)
from lingotube.config import ENV_COOKIES_FILE, forget_remembered_cookie_sources
from lingotube.errors import (
    AuthError,
    LingotubeError,
    UsageError,
)

SETTINGS_CLEANUP_FAILED_WARNING = (
    "The sign-in succeeded, but the settings file could not be updated: "
    "check settings.toml and remove cookies_file and browser by hand."
)
ENV_OVERRIDES_LOGIN_WARNING = f"The variable {ENV_COOKIES_FILE} is set and takes priority over the lingotube sign-in; remove it to use the sign-in."


def _remove_profile_directory(profile_dir: Path) -> bool:
    """True if the directory existed and was removed; PermissionError means it is in use."""
    if not profile_dir.exists():
        return False
    try:
        shutil.rmtree(profile_dir)
    except PermissionError:
        raise profile_busy_error() from None
    except OSError:
        raise _removal_failed_error() from None
    return True


def _removal_failed_error() -> LingotubeError:
    # No exception text: it may contain paths.
    return LingotubeError(
        message="Could not delete the lingotube sign-in data.",
        hint="Close the programs that use these files and run lingotube logout again.",
    )


async def _delete_saved_cookies(store) -> bool:
    try:
        return await store.delete()
    except PermissionError:
        raise profile_busy_error() from None
    except OSError:
        raise _removal_failed_error() from None


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
            help=f"Browser for the sign-in: {', '.join(LOGIN_BROWSERS)}; by default the first one installed.",
        ),
    ]

    @app.command(
        name="login",
        help="Sign in to YouTube in a separate Chrome or Edge profile; the cookies are saved for lingotube.",
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
                    message=f"Unknown browser: {browser}.",
                    hint=f"Available: {', '.join(LOGIN_BROWSERS)}.",
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
                    message="Chrome or Edge was not found.",
                    hint=(
                        "Install Chrome or Edge, or sign in to YouTube in Firefox; "
                        "the fallback is a cookies.txt file (see the README)."
                    ),
                )
            paths = container.login_paths()
            if await asyncio.to_thread(is_login_profile_in_use, paths.profile_dir):
                raise profile_busy_error()
            sign_in = container.sign_in_flow()
            saved = await sign_in(
                browser=browser_name,
                executable=executable,
                paths=paths,
                store=container.login_store(),
                notify=container.warn(),
            )
            forgotten: list[str] = []
            warnings: tuple[str, ...] = ()
            if ctx.settings_path is not None:
                try:
                    forgotten = await forget_remembered_cookie_sources(settings_path=ctx.settings_path)
                except LingotubeError, OSError:
                    # The sign-in itself succeeded; only the settings cleanup failed.
                    warnings += (SETTINGS_CLEANUP_FAILED_WARNING,)
            if container.env().get(ENV_COOKIES_FILE):
                warnings += (ENV_OVERRIDES_LOGIN_WARNING,)
            text = f"Signed in ({browser_name}). Cookies saved: {paths.cookies_file}."
            if forgotten:
                text += f"\nRemoved from the settings: {', '.join(forgotten)}."
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
        help="Delete the lingotube sign-in profile and the saved cookies.",
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
                raise profile_busy_error()
            cookies_removed = await _delete_saved_cookies(container.login_store())
            profile_removed = await asyncio.to_thread(
                _remove_profile_directory,
                paths.profile_dir,
            )
            removed = cookies_removed or profile_removed
            return c.Outcome(
                result={"removed": removed},
                text=(
                    "The lingotube sign-in profile and cookies were deleted."
                    if removed
                    else "Nothing to delete: lingotube login was not run."
                ),
            )

        c.execute(
            get_context=get_context,
            common=c.Common(json=json_),
            video=None,
            body=body,
        )
