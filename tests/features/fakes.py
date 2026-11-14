"""Test doubles for features: a scripted Ask chat."""

from collections.abc import Callable

from lingotube.ask.client import AskClient, AskSession
from lingotube.models import VideoInfo

Answer = Callable[[str], str | BaseException]


class FakeAskSession(AskSession):
    """Chat session that answers from a scripted fake client."""

    def __init__(self, client: FakeAskClient) -> None:
        """Create the session on top of a fake client.

        Args:
            client: Fake client that holds the answers and the prompt log.
        """
        self.info = client.info
        self._client = client

    async def ask(self, prompt: str) -> str:
        """Record the prompt and return the scripted answer, or raise it.

        Args:
            prompt: Prompt sent to the chat.

        Returns:
            The scripted answer text.
        """
        self._client.prompts.append(prompt)
        result = self._client.answer(prompt)
        if isinstance(
            result,
            BaseException,
        ):
            raise result
        return result


class FakeAskClient(AskClient):
    """Answers every prompt with `answer(prompt)`; a returned exception is raised.

    `.prompts` records every prompt sent, `.opened` every video id opened.
    """

    def __init__(
        self,
        info: VideoInfo,
        answer: Answer,
    ) -> None:
        """Create the fake client.

        Args:
            info: Facts about the video.
            answer: Function that returns the answer to a prompt, or an exception to raise.
        """
        self.info = info
        self.answer = answer
        self.prompts: list[str] = []
        self.opened: list[str] = []

    async def open(self, video_id: str) -> AskSession:
        """Record the video id and return a session.

        Args:
            video_id: YouTube video id.

        Returns:
            A session on this client.
        """
        self.opened.append(video_id)
        return FakeAskSession(client=self)
