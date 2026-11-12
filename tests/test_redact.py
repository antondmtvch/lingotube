from lingotube.redact import redact


def test_redacts_all_occurrences():
    assert (
        redact(
            text="a SECRET b SECRET",
            secrets=["SECRET"],
        )
        == "a *** b ***"
    )


def test_empty_secret_ignored():
    assert (
        redact(
            text="abc",
            secrets=[""],
        )
        == "abc"
    )


def test_multiple_secrets():
    assert (
        redact(
            text="x A y B",
            secrets=["A", "B"],
        )
        == "x *** y ***"
    )


def test_overlapping_secrets_fully_masked():
    assert (
        redact(
            text="xabcdefx",
            secrets=["abcd", "cdef"],
        )
        == "x***x"
    )
