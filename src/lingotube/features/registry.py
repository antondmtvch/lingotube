"""Feature registry: each feature module adds its own command; no global list."""

from collections.abc import Callable
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from lingotube.commands import AppContext

GetContext = Callable[[], "AppContext"]
Register = Callable[[typer.Typer, GetContext], None]


class FeatureRegistry:
    def __init__(self) -> None:
        self._registrars: list[Register] = []

    def add(self, register: Register) -> None:
        self._registrars.append(register)

    def apply(
        self,
        app: typer.Typer,
        get_context: GetContext,
    ) -> None:
        for register in self._registrars:
            register(
                app,
                get_context,
            )
