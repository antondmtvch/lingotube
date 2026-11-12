from lingotube.redact import redact


def test_redacts_all_occurrences():
    assert redact("a SECRET b SECRET", ["SECRET"]) == "a *** b ***"


def test_empty_secret_ignored():
    assert redact("abc", [""]) == "abc"


def test_multiple_secrets():
    assert redact("x A y B", ["A", "B"]) == "x *** y ***"
