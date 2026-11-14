"""Checks that every README explains the browser extension and keeps the same header."""

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
    """Read a README file as UTF-8 text.

    Args:
        readme_path: Path of the README.

    Returns:
        The text of the file.
    """
    return readme_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
@pytest.mark.parametrize("artifact", [r"chromium\.zip", r"firefox\.xpi"])
def test_readme_names_the_extension_download_file(readme_path: Path, artifact: str) -> None:
    """Check that every README names the extension download files."""
    assert re.search(rf"lingotube-<version>-{artifact}", read_readme(readme_path))


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
@pytest.mark.parametrize("page", EXTENSION_PAGES)
def test_readme_mentions_browser_extension_page(readme_path: Path, page: str) -> None:
    """Check that every README names the extension page of each browser."""
    assert page in read_readme(readme_path)


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_readme_states_minimum_firefox_version(readme_path: Path) -> None:
    """Check that every README states the minimum Firefox version."""
    assert "140" in extension_section(read_readme(readme_path))


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_readme_links_to_releases_page(readme_path: Path) -> None:
    """Check that every README links to the releases page."""
    assert RELEASES_URL in read_readme(readme_path)


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
@pytest.mark.parametrize("browser", UNTESTED_BROWSERS)
def test_readme_notes_browser_is_untested(readme_path: Path, browser: str) -> None:
    """Check that every README says which browsers are not tested."""
    assert browser in extension_section(read_readme(readme_path))


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_every_readme_keeps_its_six_top_level_headings(readme_path: Path) -> None:
    """Check that every README keeps the six top-level headings."""
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
    """Check that the header badges of every README match the root README."""
    assert badge_lines(read_readme(readme_path)) == badge_lines(read_readme(README_PATHS[0]))


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_language_selector_links_to_every_other_readme(readme_path: Path) -> None:
    """Check that the language selector links to every other README."""
    selector = language_selector(read_readme(readme_path))
    links = set(re.findall(r"\]\(([^)]+)\)", selector))
    expected = {repository_path(path) for path in README_PATHS if path != readme_path}
    assert links == expected
    assert selector.count("**") == 2


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_readme_exit_table_has_row_8(readme_path: Path) -> None:
    """Check that every README's exit table documents exit code 8."""
    assert re.search(r"^\| `8` \|", read_readme(readme_path), flags=re.MULTILINE)


WARNING_BLOCK = re.compile(r"^> \[!WARNING\]\n((?:>.*\n?)+)", flags=re.MULTILINE)


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_readme_warning_block_states_account_risk(readme_path: Path) -> None:
    """Check that every README has a warning block about the account risk."""
    match = WARNING_BLOCK.search(read_readme(readme_path))
    assert match is not None
    assert len(match.group(1).strip()) > 0


def test_root_readme_warning_names_terms_and_restriction() -> None:
    """Check that the root README warning names YouTube's terms and the restriction risk."""
    match = WARNING_BLOCK.search(read_readme(REPOSITORY_ROOT / "README.md"))
    assert match is not None
    block = re.sub(r"\s+", " ", match.group(1).replace(">", " "))
    assert "Terms of Service" in block
    assert "restricted" in block


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_readme_first_install_command_is_pypi(readme_path: Path) -> None:
    """Check that the first install command in every README installs from PyPI."""
    commands = [line for line in read_readme(readme_path).splitlines() if line.startswith("uv tool install")]
    assert commands[0] == "uv tool install --python 3.14 lingotube"

