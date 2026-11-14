"""Tests of the SAPISIDHASH authorization headers."""

import hashlib

import pytest

from lingotube.auth import Credentials, auth_headers, sapisidhash
from lingotube.errors import AuthError


def test_sapisidhash_format():
    """Check the format of the SAPISIDHASH value."""
    digest = hashlib.sha1(data=b"1700000000 SID123 https://www.youtube.com").hexdigest()
    assert (
        sapisidhash(
            sapisid="SID123",
            origin="https://www.youtube.com",
            now=1700000000,
        )
        == f"SAPISIDHASH 1700000000_{digest}"
    )


def test_auth_headers():
    """Check the authorization headers of a request."""
    h = auth_headers(
        creds=Credentials(cookies={"SAPISID": "SID123"}),
        now=1700000000,
    )
    assert h["Origin"] == h["X-Origin"] == "https://www.youtube.com"
    assert h["Authorization"].startswith("SAPISIDHASH 1700000000_")
    assert "Cookie" not in h


def test_fallback_to_3papisid():
    """Check that the __Secure-3PAPISID cookie is used when SAPISID is missing."""
    a = auth_headers(
        creds=Credentials(cookies={"__Secure-3PAPISID": "P"}),
        now=5,
    )
    assert a["Authorization"] == f"SAPISIDHASH 5_{hashlib.sha1(data=b'5 P https://www.youtube.com').hexdigest()}"


def test_missing_both_is_auth_error():
    """Check that AuthError is raised when both SAPISID cookies are missing."""
    with pytest.raises(expected_exception=AuthError) as e:
        auth_headers(
            creds=Credentials(cookies={"SID": "x"}),
            now=5,
        )
    assert e.value.exit_code == 4
