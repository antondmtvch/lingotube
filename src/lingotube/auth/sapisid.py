"""SAPISIDHASH authorization headers for YouTube."""

import hashlib

from lingotube.auth.base import Credentials

ORIGIN = "https://www.youtube.com"


def sapisidhash(
    sapisid: str,
    origin: str,
    now: int,
) -> str:
    digest = hashlib.sha1(data=f"{now} {sapisid} {origin}".encode()).hexdigest()
    return f"SAPISIDHASH {now}_{digest}"


def auth_headers(
    creds: Credentials,
    now: int,
) -> dict[str, str]:
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
