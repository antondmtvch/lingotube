"""Versioned prompt texts shipped inside the package."""

import re
from importlib import resources
from typing import Literal

PROMPT_VERSION = "1"

PromptName = Literal["transcript", "transcript_translated", "summary", "translate_batch"]

_PLACEHOLDER = re.compile(pattern=r"\{(\w+)\}")


def load_prompt(
    name: PromptName,
    **variables: str,
) -> str:
    """Load a versioned prompt from the package and fill in its variables.

    Only placeholders of the form ``{word}`` are replaced, in a single pass. ``str.format``
    is not used, so other curly braces and tabs are kept, and the values of the variables
    are not processed again. A placeholder without a value raises ``KeyError``; extra
    variables are ignored.

    The function is synchronous on purpose: it reads a package resource, not user input.

    Args:
        name: Prompt name, without the version and the extension.
        **variables: Values for the ``{name}`` placeholders.

    Returns:
        The prompt text with the placeholders filled in.
    """
    path = resources.files(anchor="lingotube") / "prompts" / f"{name}.v{PROMPT_VERSION}.txt"
    template = path.read_text(encoding="utf-8")
    return _PLACEHOLDER.sub(
        repl=lambda m: variables[m.group(1)],
        string=template,
    )
