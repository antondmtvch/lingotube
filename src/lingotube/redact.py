"""Secret redaction for any text that may reach output, logs or errors."""

from collections.abc import Iterable


def redact(
    text: str,
    secrets: Iterable[str],
) -> str:
    """Replace every occurrence of the secrets in a text with ``***``.

    Args:
        text: Text that may contain secrets.
        secrets: Secret values to hide. Empty values are ignored.

    Returns:
        The text with the secrets masked. Overlapping secrets become one mask.
    """
    spans: list[tuple[int, int]] = []
    for secret in {s for s in secrets if s}:
        start = text.find(secret)
        while start != -1:
            spans.append((start, start + len(secret)))
            start = text.find(
                secret,
                start + 1,
            )
    if not spans:
        return text
    spans.sort()
    out: list[str] = []
    pos = 0
    cur_start, cur_end = spans[0]
    for start, end in spans[1:]:
        if start <= cur_end:  # overlapping or adjacent: merge into one mask
            cur_end = max(
                cur_end,
                end,
            )
            continue
        out += [text[pos:cur_start], "***"]
        pos = cur_end
        cur_start, cur_end = start, end
    out += [text[pos:cur_start], "***", text[cur_end:]]
    return "".join(out)
