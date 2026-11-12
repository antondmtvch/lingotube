import os

import pytest

from lingotube.auth import FileCookieSource
from lingotube.errors import AuthError

H = "# Netscape HTTP Cookie File\n"


def row(domain, name, value):
    return f"{domain}\tTRUE\t/\tTRUE\t2000000000\t{name}\t{value}\n"


async def test_file_source_reads_netscape(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text(
        H
        + row(".youtube.com", "SAPISID", "a")
        + row(".google.com", "SID", "b")
        + row(".example.com", "X", "c")
    )
    creds = await FileCookieSource(p).load()
    assert set(creds.cookies) == {"SAPISID", "SID"}


async def test_httponly_and_bare_domains(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text(
        H
        + "\n"
        + row("#HttpOnly_.youtube.com", "HSID", "h")
        + row("www.youtube.com", "SAPISID", "a")
        + row("google.com", "G", "g")
        + row("accounts.google.com", "AG", "x")
        + row("evilyoutube.com", "E", "e")
        + "# comment\n"
    )
    creds = await FileCookieSource(p).load()
    assert set(creds.cookies) == {"HSID", "SAPISID", "G", "AG"}


async def test_file_missing_sapisid_is_auth_error(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text(H + row(".google.com", "SID", "b"))
    with pytest.raises(AuthError) as e:
        await FileCookieSource(p).load()
    assert e.value.exit_code == 4 and "cookies-file" in e.value.hint


async def test_file_not_found_is_auth_error(tmp_path):
    with pytest.raises(AuthError) as e:
        await FileCookieSource(tmp_path / "nope.txt").load()
    assert e.value.exit_code == 4


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
async def test_file_world_readable_warns(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text(H + row(".youtube.com", "SAPISID", "a"))
    p.chmod(0o644)
    msgs = []
    await FileCookieSource(p, warn=msgs.append).load()
    assert len(msgs) == 1
