import asyncio
import dataclasses

from lingotube.cache import Cache, CacheKey

KEY = CacheKey("vid", "transcript", "orig", "chat", "v1")


async def test_put_get_roundtrip(tmp_path):
    cache = Cache(tmp_path / "c")
    await cache.put(KEY, {"a": [1, 2], "t": "текст"})
    assert await cache.get(KEY) == {"a": [1, 2], "t": "текст"}
    await cache.delete(KEY)
    assert await cache.get(KEY) is None
    await cache.delete(KEY)


async def test_get_missing_returns_none(tmp_path):
    assert await Cache(tmp_path).get(KEY) is None


async def test_keys_differ_by_every_field(tmp_path):
    cache = Cache(tmp_path)
    await cache.put(KEY, {"x": 1})
    for field, value in [
        ("video_id", "other"),
        ("kind", "summary"),
        ("language", "ru"),
        ("mode", "x"),
        ("prompt_version", "v2"),
        ("part", "1"),
    ]:
        assert await cache.get(dataclasses.replace(KEY, **{field: value})) is None


async def test_key_fields_cannot_collide_or_escape(tmp_path):
    cache = Cache(tmp_path / "c")
    a = CacheKey("a/../b", "k", "l", "m", "v")
    await cache.put(a, {"x": 1})
    assert all(
        p.parent == tmp_path / "c" for p in (tmp_path / "c").rglob("*") if p.is_file()
    )
    assert await cache.get(CacheKey("a", "../bk", "l", "m", "v")) is None


async def test_corrupt_file_is_treated_as_missing(tmp_path):
    cache = Cache(tmp_path)
    await cache.put(KEY, {"x": 1})
    (file,) = tmp_path.glob("*.json")
    file.write_text("{обрыв", encoding="utf-8")
    assert await cache.get(KEY) is None
    await cache.put(KEY, {"x": 2})
    assert await cache.get(KEY) == {"x": 2}


async def test_non_dict_json_is_missing(tmp_path):
    cache = Cache(tmp_path)
    await cache.put(KEY, {"x": 1})
    (file,) = tmp_path.glob("*.json")
    file.write_text("[1]", encoding="utf-8")
    assert await cache.get(KEY) is None


async def test_no_temp_files_left_after_put(tmp_path):
    cache = Cache(tmp_path)
    await asyncio.gather(
        *(cache.put(dataclasses.replace(KEY, part=str(i)), {"i": i}) for i in range(5))
    )
    assert len(list(tmp_path.iterdir())) == 5
    assert all(p.suffix == ".json" for p in tmp_path.iterdir())


async def test_failed_put_leaves_no_temp_files(tmp_path):
    cache = Cache(tmp_path)
    try:
        await cache.put(KEY, {"x": object()})
    except TypeError:
        pass
    assert list(tmp_path.iterdir()) == []


async def test_cache_never_contains_secrets(tmp_path):
    cache = Cache(tmp_path)
    await cache.put(KEY, {"text": "hello"})
    for p in tmp_path.rglob("*"):
        if p.is_file():
            assert "SAPISID" not in p.read_text(encoding="utf-8")
