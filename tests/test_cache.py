import asyncio
import dataclasses

from lingotube.cache import Cache, CacheKey

KEY = CacheKey(
    video_id="vid",
    kind="transcript",
    language="orig",
    mode="chat",
    prompt_version="v1",
)


async def test_put_get_roundtrip(tmp_path):
    cache = Cache(root=tmp_path / "c")
    await cache.put(
        key=KEY,
        value={"a": [1, 2], "t": "текст"},
    )
    assert await cache.get(key=KEY) == {"a": [1, 2], "t": "текст"}
    await cache.delete(key=KEY)
    assert await cache.get(key=KEY) is None
    await cache.delete(key=KEY)


async def test_get_missing_returns_none(tmp_path):
    assert await Cache(root=tmp_path).get(key=KEY) is None


async def test_keys_differ_by_every_field(tmp_path):
    cache = Cache(root=tmp_path)
    await cache.put(
        key=KEY,
        value={"x": 1},
    )
    for field, value in [
        ("video_id", "other"),
        ("kind", "summary"),
        ("language", "ru"),
        ("mode", "x"),
        ("prompt_version", "v2"),
        ("part", "1"),
    ]:
        assert (
            await cache.get(
                key=dataclasses.replace(
                    KEY,
                    **{field: value},
                )
            )
            is None
        )


async def test_key_fields_cannot_collide_or_escape(tmp_path):
    cache = Cache(root=tmp_path / "c")
    a = CacheKey(
        video_id="a/../b",
        kind="k",
        language="l",
        mode="m",
        prompt_version="v",
    )
    await cache.put(
        key=a,
        value={"x": 1},
    )
    assert all(
        p.parent == tmp_path / "c"
        for p in (tmp_path / "c").rglob(pattern="*")
        if p.is_file()
    )
    assert (
        await cache.get(
            key=CacheKey(
                video_id="a",
                kind="../bk",
                language="l",
                mode="m",
                prompt_version="v",
            )
        )
        is None
    )


async def test_corrupt_file_is_treated_as_missing(tmp_path):
    cache = Cache(root=tmp_path)
    await cache.put(
        key=KEY,
        value={"x": 1},
    )
    (file,) = tmp_path.glob(pattern="*.json")
    file.write_text(
        data="{обрыв",
        encoding="utf-8",
    )
    assert await cache.get(key=KEY) is None
    await cache.put(
        key=KEY,
        value={"x": 2},
    )
    assert await cache.get(key=KEY) == {"x": 2}


async def test_non_dict_json_is_missing(tmp_path):
    cache = Cache(root=tmp_path)
    await cache.put(
        key=KEY,
        value={"x": 1},
    )
    (file,) = tmp_path.glob(pattern="*.json")
    file.write_text(
        data="[1]",
        encoding="utf-8",
    )
    assert await cache.get(key=KEY) is None


async def test_no_temp_files_left_after_put(tmp_path):
    cache = Cache(root=tmp_path)
    await asyncio.gather(
        *(
            cache.put(
                key=dataclasses.replace(
                    KEY,
                    part=str(i),
                ),
                value={"i": i},
            )
            for i in range(5)
        )
    )
    assert len(list(tmp_path.iterdir())) == 5
    assert all(p.suffix == ".json" for p in tmp_path.iterdir())


async def test_failed_put_leaves_no_temp_files(tmp_path):
    cache = Cache(root=tmp_path)
    try:
        await cache.put(
            key=KEY,
            value={"x": object()},
        )
    except TypeError:
        pass
    assert list(tmp_path.iterdir()) == []


async def test_cache_never_contains_secrets(tmp_path):
    cache = Cache(root=tmp_path)
    await cache.put(
        key=KEY,
        value={"text": "hello"},
    )
    for p in tmp_path.rglob(pattern="*"):
        if p.is_file():
            assert "SAPISID" not in p.read_text(encoding="utf-8")
