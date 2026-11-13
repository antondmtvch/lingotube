"""Credentials container and the CookieSource protocol. Values never leak via repr."""

from collections.abc import Mapping
from typing import Protocol

from lingotube.errors import AuthError

LOGIN_HINT = "Выполните lingotube login: откроется окно Chrome или Edge, войдите в YouTube."

EXPORT_HINT = (
    LOGIN_HINT + " Запасной путь — выгрузить cookies через режим инкогнито: откройте окно инкогнито, "
    "разрешите там расширение для экспорта, войдите на youtube.com, выгрузите cookies на "
    "странице https://www.youtube.com/robots.txt и сразу закройте окно инкогнито. "
    "Затем запустите с --cookies-file <путь> (путь запомнится)."
)

_ALLOWED_ROOTS = ("youtube.com", "google.com")


def is_allowed_domain(domain: str) -> bool:
    d = domain.lower().lstrip(".")
    return any(d == root or d.endswith("." + root) for root in _ALLOWED_ROOTS)


class Credentials:
    def __init__(self, cookies: Mapping[str, str]) -> None:
        self.cookies: dict[str, str] = dict(cookies)

    def secrets(self) -> list[str]:
        return list(self.cookies.values())

    def sapisid(self) -> str | None:
        return self.cookies.get("SAPISID") or self.cookies.get("__Secure-3PAPISID")

    def require_sapisid(self) -> str:
        value = self.sapisid()
        if not value:
            raise AuthError(
                message="В cookies нет SAPISID (вход в YouTube не найден).",
                hint=EXPORT_HINT,
            )
        return value

    def __repr__(self) -> str:
        return "Credentials(***)"


class CookieSource(Protocol):
    async def load(self) -> Credentials: ...
