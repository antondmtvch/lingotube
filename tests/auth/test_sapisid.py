import hashlib

import pytest

from lingotube.auth import Credentials, auth_headers, sapisidhash
from lingotube.errors import AuthError


def test_sapisidhash_format():
    digest = hashlib.sha1(b"1700000000 SID123 https://www.youtube.com").hexdigest()
    assert (
        sapisidhash("SID123", "https://www.youtube.com", 1700000000)
        == f"SAPISIDHASH 1700000000_{digest}"
    )


def test_auth_headers():
    h = auth_headers(Credentials({"SAPISID": "SID123"}), 1700000000)
    assert h["Origin"] == h["X-Origin"] == "https://www.youtube.com"
    assert h["Authorization"].startswith("SAPISIDHASH 1700000000_")
    assert "Cookie" not in h


def test_fallback_to_3papisid():
    a = auth_headers(Credentials({"__Secure-3PAPISID": "P"}), 5)
    assert (
        a["Authorization"]
        == f"SAPISIDHASH 5_{hashlib.sha1(b'5 P https://www.youtube.com').hexdigest()}"
    )


def test_missing_both_is_auth_error():
    with pytest.raises(AuthError) as e:
        auth_headers(Credentials({"SID": "x"}), 5)
    assert e.value.exit_code == 4
