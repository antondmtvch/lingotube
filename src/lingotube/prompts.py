"""Версионированные тексты промптов, поставляемые внутри пакета."""

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
    """Читает ``prompts/<name>.v<версия>.txt`` и подставляет ``{имя}``-переменные.

    Заменяются только плейсхолдеры вида ``{слово}`` за один проход (``str.format``
    не используется, остальные фигурные скобки, TAB и т.п. сохраняются; значения
    переменных повторно не обрабатываются). Плейсхолдер без переданной переменной
    даёт ``KeyError``; лишние переменные игнорируются.

    Синхронная: читает ресурс пакета (не пользовательский ввод-вывод).
    """
    path = resources.files(anchor="lingotube") / "prompts" / f"{name}.v{PROMPT_VERSION}.txt"
    template = path.read_text(encoding="utf-8")
    return _PLACEHOLDER.sub(
        repl=lambda m: variables[m.group(1)],
        string=template,
    )
