import pytest
from fakes import FakeAskClient

from lingotube.cache import Cache, CacheKey
from lingotube.errors import ChatUnavailableError
from lingotube.features.summary import SummaryFeature
from lingotube.models import VideoInfo
from lingotube.prompts import PROMPT_VERSION

VID = "vid123"
INFO = VideoInfo(VID, 100.0, "t", "en")


def make(tmp_path, answer):
    client = FakeAskClient(INFO, answer)
    return client, SummaryFeature(client, Cache(tmp_path / "cache"))


async def test_summary_single_request_in_language(tmp_path):
    client, feature = make(tmp_path, lambda p: "# Итог\n- мысль")
    assert await feature.run(VID, "русский") == "# Итог\n- мысль"
    assert len(client.prompts) == 1
    assert "русский" in client.prompts[0]


async def test_summary_cached_per_language(tmp_path):
    client, feature = make(tmp_path, lambda p: "текст " + ("ru" if "русский" in p else "de"))
    assert await feature.run(VID, "русский") == "текст ru"
    assert await feature.run(VID, "русский") == "текст ru"
    assert len(client.prompts) == 1
    assert await feature.run(VID, "немецкий") == "текст de"
    assert len(client.prompts) == 2
    assert await feature.run(VID, "русский", use_cache=False) == "текст ru"
    assert len(client.prompts) == 3
    stored = await Cache(tmp_path / "cache").get(CacheKey(VID, "summary", "русский", "chat", PROMPT_VERSION))
    assert stored == {"text": "текст ru"}


@pytest.mark.parametrize("answer", ["", "  \n "])
async def test_summary_empty_answer_is_error(tmp_path, answer):
    _, feature = make(tmp_path, lambda p: answer)
    with pytest.raises(ChatUnavailableError):
        await feature.run(VID, "русский")
    key = CacheKey(VID, "summary", "русский", "chat", PROMPT_VERSION)
    assert await Cache(tmp_path / "cache").get(key) is None
