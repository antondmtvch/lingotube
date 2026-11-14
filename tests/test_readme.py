"""Checks that every README explains how to install the browser extension."""

import re
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
TRANSLATION_CODES = ["ru", "zh-Hans", "zh-Hant", "hi", "es", "fr", "ar", "bn", "pt", "th", "ja", "vi", "de"]
README_PATHS = [REPOSITORY_ROOT / "README.md"] + [
    REPOSITORY_ROOT / "docs" / "readme" / f"README.{code}.md" for code in TRANSLATION_CODES
]
RELEASES_URL = "https://github.com/antondmtvch/lingotube/releases"
EXTENSION_PAGES = ["chrome://extensions", "edge://extensions", "about:addons"]
UNTESTED_BROWSERS = ["Brave", "Opera", "Vivaldi"]
EXPECTED_TOP_LEVEL_HEADINGS = 6


def count_top_level_headings(text: str) -> int:
    """Count `## ` headings that are outside fenced code blocks."""
    count = 0
    inside_code_block = False
    for line in text.splitlines():
        if line.startswith("```"):
            inside_code_block = not inside_code_block
        elif not inside_code_block and line.startswith("## "):
            count += 1
    return count


def extension_section(text: str) -> str:
    """Return the `## ` section that contains the extension installation steps."""
    for section in re.split(r"^(?=## )", text, flags=re.MULTILINE):
        if "chrome://extensions" in section:
            return section
    return ""


def read_readme(readme_path: Path) -> str:
    return readme_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
@pytest.mark.parametrize("artifact", [r"chromium\.zip", r"firefox\.xpi"])
def test_readme_names_the_extension_download_file(readme_path: Path, artifact: str) -> None:
    assert re.search(rf"lingotube-<version>-{artifact}", read_readme(readme_path))


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
@pytest.mark.parametrize("page", EXTENSION_PAGES)
def test_readme_mentions_browser_extension_page(readme_path: Path, page: str) -> None:
    assert page in read_readme(readme_path)


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_readme_states_minimum_firefox_version(readme_path: Path) -> None:
    assert "140" in extension_section(read_readme(readme_path))


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_readme_links_to_releases_page(readme_path: Path) -> None:
    assert RELEASES_URL in read_readme(readme_path)


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
@pytest.mark.parametrize("browser", UNTESTED_BROWSERS)
def test_readme_notes_browser_is_untested(readme_path: Path, browser: str) -> None:
    assert browser in extension_section(read_readme(readme_path))


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_every_readme_keeps_its_six_top_level_headings(readme_path: Path) -> None:
    text = readme_path.read_text(encoding="utf-8")
    assert count_top_level_headings(text) == EXPECTED_TOP_LEVEL_HEADINGS


def badge_lines(text: str) -> list[str]:
    """Return the badge lines of the header, the `![...]` lines before the first heading."""
    return [line for line in text.split("\n")[:12] if line.startswith("![")]


def language_selector(text: str) -> str:
    """Return the language selector line of the header (the line with ` · ` separators)."""
    return next(line for line in text.split("\n")[:14] if " · " in line)


def repository_path(readme_path: Path) -> str:
    """Return the root-relative link target of a README, as the header links it."""
    return "/" + readme_path.relative_to(REPOSITORY_ROOT).as_posix()


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_header_badges_match_root_readme(readme_path: Path) -> None:
    assert badge_lines(read_readme(readme_path)) == badge_lines(read_readme(README_PATHS[0]))


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_language_selector_links_to_every_other_readme(readme_path: Path) -> None:
    selector = language_selector(read_readme(readme_path))
    links = set(re.findall(r"\]\(([^)]+)\)", selector))
    expected = {repository_path(path) for path in README_PATHS if path != readme_path}
    assert links == expected
    assert selector.count("**") == 2
