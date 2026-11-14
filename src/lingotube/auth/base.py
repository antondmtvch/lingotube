"""Credentials container and the CookieSource protocol. Values never leak via repr."""

from collections.abc import Mapping
from typing import Protocol

from lingotube.errors import AuthError

LOGIN_HINT = "Run lingotube login: a Chrome or Edge window opens; sign in to YouTube there."

EXPORT_HINT = (
    LOGIN_HINT + " Fallback: export the cookies in a private window: open a private window, "
    "allow the export extension there, sign in to youtube.com, export the cookies on "
    "the page https://www.youtube.com/robots.txt and close the private window right away. "
    "Then run again with --cookies-file <path> (the path is remembered)."
)

_ALLOWED_ROOTS = ("youtube.com", "google.com")


def is_allowed_domain(domain: str) -> bool:
    """Check whether a cookie domain belongs to YouTube or Google.

    Args:
        domain: Cookie domain, with or without a leading dot.

    Returns:
        True for youtube.com, google.com and their subdomains.
    """
    d = domain.lower().lstrip(".")
    return any(d == root or d.endswith("." + root) for root in _ALLOWED_ROOTS)


class Credentials:
    """Cookies of one browser or file, kept without ever printing their values.

    Attributes:
        cookies: Cookie names mapped to their values.
    """

    def __init__(self, cookies: Mapping[str, str]) -> None:
        """Create the credentials from a cookie mapping.

        Args:
            cookies: Cookie names mapped to their values. A copy is kept.
        """
        self.cookies: dict[str, str] = dict(cookies)

    def secrets(self) -> list[str]:
        """Return all cookie values, so that logs and errors can hide them.

        Returns:
            The list of cookie values.
        """
        return list(self.cookies.values())

    def sapisid(self) -> str | None:
        """Return the cookie that authorizes YouTube requests.

        Returns:
            The SAPISID value, or None if neither SAPISID nor __Secure-3PAPISID is present.
        """
        return self.cookies.get("SAPISID") or self.cookies.get("__Secure-3PAPISID")

    def require_sapisid(self) -> str:
        """Return the SAPISID cookie or fail.

        Returns:
            The SAPISID value.

        Raises:
            AuthError: If there is no SAPISID cookie, so the sign-in to YouTube was not found.
        """
        value = self.sapisid()
        if not value:
            raise AuthError(
                message="The cookies have no SAPISID (no sign-in to YouTube found).",
                hint=EXPORT_HINT,
            )
        return value

    def __repr__(self) -> str:
        """Hide the cookie values in the representation."""
        return "Credentials(***)"


class CookieSource(Protocol):
    """A source that can load credentials, such as browser cookies or a file."""

    async def load(self) -> Credentials:
        """Load credentials from this source.

        Returns:
            The loaded credentials.

        Raises:
            AuthError: If the source has no usable sign-in.
        """
        ...
