"""Checks of the release workflow: it publishes on a version tag with Trusted Publishing, without a token."""

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "publish.yml"


def test_workflow_file_exists() -> None:
    """Check that the publish workflow file exists."""
    assert WORKFLOW.is_file()


def test_workflow_uses_trusted_publishing() -> None:
    """Check that the job requests an OIDC token and runs in the pypi environment."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "id-token: write" in text
    assert "environment: pypi" in text
    assert "uv publish --trusted-publishing always" in text


def test_workflow_runs_on_version_tags() -> None:
    """Check that the workflow starts on a push of a version tag."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "tags:" in text
    assert "'v*'" in text or '"v*"' in text or "- v*" in text


def test_workflow_has_no_password_or_token() -> None:
    """Check that the workflow does not store a PyPI password or token."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "password" not in text.lower()
    assert "PYPI_TOKEN" not in text


def test_workflow_checks_tag_against_package_version() -> None:
    """Check that the workflow refuses a tag whose version differs from pyproject.toml."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "GITHUB_REF_NAME" in text
    assert "pyproject.toml" in text


def test_workflow_runs_tests_before_publishing() -> None:
    """Check that the test suite runs before the publish step."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "uv run pytest" in text
    assert text.index("uv run pytest") < text.index("uv publish")
