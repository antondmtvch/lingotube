"""Feature registry: each feature module adds its own command; no global list."""

from collections.abc import Callable
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from lingotube.commands import AppContext

GetContext = Callable[[], "AppContext"]
Register = Callable[[typer.Typer, GetContext], None]


class FeatureRegistry:
    """Collect the command registrations of the feature modules.

    Each feature adds its own command. There is no global list of commands here.
    """

    def __init__(self) -> None:
        """Create an empty registry."""
        self._registrars: list[Register] = []

    def add(self, register: Register) -> None:
        """Add a registration function.

        Args:
            register: Function that adds one command to the application.
        """
        self._registrars.append(register)

    def apply(
        self,
        app: typer.Typer,
        get_context: GetContext,
    ) -> None:
        """Call every registration function, in the order they were added.

        Args:
            app: Typer application.
            get_context: Function that returns the shared context of the command.
        """
        for register in self._registrars:
            register(
                app,
                get_context,
            )
