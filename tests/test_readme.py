"""Checks that every README explains how to install the browser extension."""

from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
TRANSLATION_CODES = ["ru", "zh-Hans", "zh-Hant", "hi", "es", "fr", "ar", "bn", "pt", "th", "ja", "vi", "de"]
README_PATHS = [REPOSITORY_ROOT / "README.md"] + [
    REPOSITORY_ROOT / "docs" / "readme" / f"README.{code}.md" for code in TRANSLATION_CODES
]
INSTALLATION_MARKERS = ["chrome://extensions", "edge://extensions", "about:addons", ".xpi", "128", "releases"]
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


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_every_readme_explains_extension_installation(readme_path: Path) -> None:
    text = readme_path.read_text(encoding="utf-8")
    missing = [marker for marker in INSTALLATION_MARKERS if marker not in text]
    assert not missing, f"{readme_path.name} lacks: {missing}"


@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.name)
def test_every_readme_keeps_its_six_top_level_headings(readme_path: Path) -> None:
    text = readme_path.read_text(encoding="utf-8")
    assert count_top_level_headings(text) == EXPECTED_TOP_LEVEL_HEADINGS
