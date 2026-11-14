"""Error hierarchy with stable codes and process exit codes."""


class LingotubeError(Exception):
    """Base error with a stable machine-readable code and a process exit code.

    Attributes:
        code: Identifier written to the JSON output.
        exit_code: Process exit code used for this error.
    """

    code: str = "error"
    exit_code: int = 1

    def __init__(
        self,
        message: str,
        hint: str | None = None,
    ) -> None:
        """Create the error.

        Args:
            message: Human-readable description of the problem.
            hint: Optional advice on how to fix it.
        """
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        """Return the message, so the error prints as plain text."""
        return self.message


class ChatUnavailableError(LingotubeError):
    """YouTube chat is unavailable for this video, account or country."""

    code = "chat_unavailable"
    exit_code = 3


class YouTubeChangedError(LingotubeError):
    """YouTube changed the page or the chat response in a way lingotube cannot read."""

    code = "youtube_changed"
    exit_code = 8


class AuthError(LingotubeError):
    """Cookies are missing or expired, or sign-in to YouTube failed."""

    code = "auth"
    exit_code = 4


class ProfileBusyError(LingotubeError):
    """The lingotube login profile is already open in another browser window."""

    code = "profile_busy"
    exit_code = 1


class IncompleteError(LingotubeError):
    """The result was written, but the transcript stops before the end of the video."""

    code = "incomplete"
    exit_code = 5


class NetworkError(LingotubeError):
    """A network failure remained after the retries."""

    code = "network"
    exit_code = 6


class ValidationError(LingotubeError):
    """The input (link, file or settings) is invalid."""

    code = "validation"
    exit_code = 7


class UsageError(LingotubeError):
    """Wrong or missing command-line parameters (same exit code as the parser's own errors)."""

    code = "usage"
    exit_code = 2
