"""Error hierarchy with stable codes and process exit codes."""


class LingotubeError(Exception):
    code: str = "error"
    exit_code: int = 1

    def __init__(
        self,
        message: str,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        return self.message


class ChatUnavailableError(LingotubeError):
    code = "chat_unavailable"
    exit_code = 3


class AuthError(LingotubeError):
    code = "auth"
    exit_code = 4


class ProfileBusyError(LingotubeError):
    """The lingotube login profile is already open in another browser window."""

    code = "profile_busy"
    exit_code = 1


class IncompleteError(LingotubeError):
    code = "incomplete"
    exit_code = 5


class NetworkError(LingotubeError):
    code = "network"
    exit_code = 6


class ValidationError(LingotubeError):
    code = "validation"
    exit_code = 7


class UsageError(LingotubeError):
    """Wrong or missing command-line parameters (same exit code as the parser's own errors)."""

    code = "usage"
    exit_code = 2
