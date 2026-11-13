"""Test doubles for features: a scripted Ask chat."""

from collections.abc import Callable

from lingotube.ask.client import AskClient, AskSession
from lingotube.models import VideoInfo

Answer = Callable[[str], str | BaseException]


class FakeAskSession(AskSession):
    def __init__(self, client: FakeAskClient) -> None:
        self.info = client.info
        self._client = client

    async def ask(self, prompt: str) -> str:
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
        self.info = info
        self.answer = answer
        self.prompts: list[str] = []
        self.opened: list[str] = []

    async def open(self, video_id: str) -> AskSession:
        self.opened.append(video_id)
        return FakeAskSession(client=self)
