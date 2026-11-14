"""Tests of the redaction of secrets in text."""

from lingotube.redact import redact


def test_redacts_all_occurrences():
    """Check that every occurrence of a secret is hidden."""
    assert (
        redact(
            text="a SECRET b SECRET",
            secrets=["SECRET"],
        )
        == "a *** b ***"
    )


def test_empty_secret_ignored():
    """Check that an empty secret is ignored."""
    assert (
        redact(
            text="abc",
            secrets=[""],
        )
        == "abc"
    )


def test_multiple_secrets():
    """Check that several secrets are hidden."""
    assert (
        redact(
            text="x A y B",
            secrets=["A", "B"],
        )
        == "x *** y ***"
    )


def test_overlapping_secrets_fully_masked():
    """Check that overlapping secrets are hidden as one mask."""
    assert (
        redact(
            text="xabcdefx",
            secrets=["abcd", "cdef"],
        )
        == "x***x"
    )
