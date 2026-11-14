"""Tests of the Netscape cookies.txt source."""

import os

import pytest

from lingotube.auth import FileCookieSource
from lingotube.errors import AuthError

H = "# Netscape HTTP Cookie File\n"


def row(
    domain,
    name,
    value,
):
    """Build one line of a cookies.txt file.

    Args:
        domain: Cookie domain.
        name: Cookie name.
        value: Cookie value.

    Returns:
        The line, with tab-separated fields.
    """
    return f"{domain}\tTRUE\t/\tTRUE\t2000000000\t{name}\t{value}\n"


async def test_file_source_reads_netscape(tmp_path):
    """Check that a Netscape cookies file is read."""
    p = tmp_path / "c.txt"
    p.write_text(
        data=H
        + row(
            domain=".youtube.com",
            name="SAPISID",
            value="a",
        )
        + row(
            domain=".google.com",
            name="SID",
            value="b",
        )
        + row(
            domain=".example.com",
            name="X",
            value="c",
        )
    )
    creds = await FileCookieSource(path=p).load()
    assert set(creds.cookies) == {"SAPISID", "SID"}


async def test_httponly_and_bare_domains(tmp_path):
    """Check that HttpOnly lines and bare domains are read."""
    p = tmp_path / "c.txt"
    p.write_text(
        data=H
        + "\n"
        + row(
            domain="#HttpOnly_.youtube.com",
            name="HSID",
            value="h",
        )
        + row(
            domain="www.youtube.com",
            name="SAPISID",
            value="a",
        )
        + row(
            domain="google.com",
            name="G",
            value="g",
        )
        + row(
            domain="accounts.google.com",
            name="AG",
            value="x",
        )
        + row(
            domain="evilyoutube.com",
            name="E",
            value="e",
        )
        + "# comment\n"
    )
    creds = await FileCookieSource(path=p).load()
    assert set(creds.cookies) == {"HSID", "SAPISID", "G", "AG"}


async def test_file_missing_sapisid_is_auth_error(tmp_path):
    """Check that a file without SAPISID raises AuthError."""
    p = tmp_path / "c.txt"
    p.write_text(
        data=H
        + row(
            domain=".google.com",
            name="SID",
            value="b",
        )
    )
    with pytest.raises(expected_exception=AuthError) as e:
        await FileCookieSource(path=p).load()
    assert e.value.exit_code == 4 and "cookies-file" in e.value.hint


async def test_file_not_found_is_auth_error(tmp_path):
    """Check that a missing file raises AuthError."""
    with pytest.raises(expected_exception=AuthError) as e:
        await FileCookieSource(path=tmp_path / "nope.txt").load()
    assert e.value.exit_code == 4


@pytest.mark.skipif(
    condition=os.name == "nt",
    reason="POSIX permissions",
)
async def test_file_world_readable_warns(tmp_path):
    """Check that a cookies file readable by other users produces a warning."""
    p = tmp_path / "c.txt"
    p.write_text(
        data=H
        + row(
            domain=".youtube.com",
            name="SAPISID",
            value="a",
        )
    )
    p.chmod(mode=0o644)
    msgs = []
    await FileCookieSource(
        path=p,
        warn=msgs.append,
    ).load()
    assert len(msgs) == 1


async def test_cookie_with_control_characters_is_dropped(tmp_path):
    """Check that a cookie with control characters is dropped."""
    p = tmp_path / "c.txt"
    p.write_text(
        data=H
        + row(
            domain=".youtube.com",
            name="SAPISID",
            value="a",
        )
        + row(
            domain=".youtube.com",
            name="SID",
            value="ab\x01cd",
        ),
        encoding="utf-8",
    )
    creds = await FileCookieSource(path=p).load()
    assert "SID" not in creds.cookies
    assert "ab" not in repr(creds) and "cd" not in repr(creds)


@pytest.mark.skipif(
    condition=os.name == "nt",
    reason="POSIX permissions",
)
async def test_file_0600_gives_no_warning(tmp_path):
    """Check that a cookies file with owner-only permissions gives no warning."""
    p = tmp_path / "c.txt"
    p.write_text(
        data=H
        + row(
            domain=".youtube.com",
            name="SAPISID",
            value="a",
        )
    )
    p.chmod(mode=0o600)
    msgs = []
    await FileCookieSource(
        path=p,
        warn=msgs.append,
    ).load()
    assert msgs == []
