"""Secret redaction for any text that may reach output, logs or errors."""

from collections.abc import Iterable


def redact(
    text: str,
    secrets: Iterable[str],
) -> str:
    # Longest first so a secret containing another one is fully masked.
    for secret in sorted(
        {s for s in secrets if s},
        key=len,
        reverse=True,
    ):
        text = text.replace(
            secret,
            "***",
        )
    return text
