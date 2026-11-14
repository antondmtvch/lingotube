"""Checks of the API documentation: pdoc is a dev dependency and the Pages workflow builds and deploys it."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "docs.yml"


def test_pdoc_is_a_dev_dependency() -> None:
    """Check that pdoc is in the dev dependency group."""
    groups = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["dependency-groups"]
    assert any(dep.startswith("pdoc") for dep in groups["dev"])


def test_docs_workflow_builds_google_style_api() -> None:
    """Check that the workflow renders the package with pdoc in Google docstring format."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "uv run pdoc -o site -d google lingotube" in text


def test_docs_workflow_deploys_to_pages_with_oidc() -> None:
    """Check that the workflow deploys with the Pages actions and the pages and id-token permissions."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pages: write" in text
    assert "id-token: write" in text
    assert "actions/upload-pages-artifact@v5" in text
    assert "actions/deploy-pages@v5" in text
    assert "environment:" in text and "github-pages" in text


def test_docs_workflow_runs_on_main_only() -> None:
    """Check that the site is published from main and not from feature branches."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "branches: [main]" in text
