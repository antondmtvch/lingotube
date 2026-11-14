"""SAPISIDHASH authorization headers for YouTube."""

import hashlib

from lingotube.auth.base import Credentials

ORIGIN = "https://www.youtube.com"


def sapisidhash(
    sapisid: str,
    origin: str,
    now: int,
) -> str:
    """Build a SAPISIDHASH authorization value.

    Args:
        sapisid: Value of the SAPISID cookie.
        origin: Origin that the request is sent to.
        now: Current Unix time in seconds.

    Returns:
        The header value, in the form ``SAPISIDHASH <time>_<digest>``.
    """
    digest = hashlib.sha1(data=f"{now} {sapisid} {origin}".encode()).hexdigest()
    return f"SAPISIDHASH {now}_{digest}"


def auth_headers(
    creds: Credentials,
    now: int,
) -> dict[str, str]:
    """Build the headers that authorize a YouTube request.

    Args:
        creds: Credentials with a SAPISID cookie.
        now: Current Unix time in seconds.

    Returns:
        The Authorization, Origin and X-Origin headers.

    Raises:
        AuthError: If there is no SAPISID cookie.
    """
    sapisid = creds.require_sapisid()
    return {
        "Authorization": sapisidhash(
            sapisid=sapisid,
            origin=ORIGIN,
            now=now,
        ),
        "Origin": ORIGIN,
        "X-Origin": ORIGIN,
    }
