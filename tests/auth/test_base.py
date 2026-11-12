import pytest

from lingotube.auth import Credentials
from lingotube.errors import AuthError


def test_credentials_repr_hides_values():
    assert "s3cret" not in repr(Credentials(cookies={"SAPISID": "s3cret"}))


def test_secrets_lists_values():
    assert Credentials(cookies={"A": "1", "B": "2"}).secrets() == ["1", "2"]


def test_require_sapisid_missing():
    with pytest.raises(expected_exception=AuthError) as e:
        Credentials(cookies={"SID": "x"}).require_sapisid()
    assert e.value.exit_code == 4 and "cookies-file" in e.value.hint
