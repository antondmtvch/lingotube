"""Sign-in to YouTube: cookie sources and the request authorization headers."""

from lingotube.auth.base import CookieSource, Credentials
from lingotube.auth.browser import BrowserCookieSource, ChainCookieSource
from lingotube.auth.file import FileCookieSource
from lingotube.auth.sapisid import auth_headers, sapisidhash

__all__ = [
    "BrowserCookieSource",
    "ChainCookieSource",
    "CookieSource",
    "Credentials",
    "FileCookieSource",
    "auth_headers",
    "sapisidhash",
]
