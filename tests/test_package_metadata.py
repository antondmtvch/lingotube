"""Checks of the package metadata that PyPI shows: description, readme, links and classifiers."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load() -> dict:
    """Read the project table of pyproject.toml.

    Returns:
        The `project` table as a dictionary.
    """
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_description_names_the_chat_not_live_chat() -> None:
    """Check that the description says chat and does not say live-chat."""
    assert "live-chat" not in load()["description"]
    assert "chat" in load()["description"].lower()


def test_readme_is_the_pypi_page_and_has_no_relative_links() -> None:
    """Check that the PyPI readme exists and has only absolute, anchor or mail links."""
    project = load()
    assert project["readme"] == "docs/pypi/README.md"
    text = (ROOT / project["readme"]).read_text(encoding="utf-8")
    assert not re.search(r"\]\((?!https?://|#|mailto:)", text)


def test_urls_and_classifiers_present() -> None:
    """Check that the project URLs, keywords and classifiers are filled in."""
    project = load()
    assert {"Homepage", "Repository", "Issues"} <= set(project["urls"])
    assert project["classifiers"]
    assert project["keywords"]
