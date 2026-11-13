import asyncio
import contextlib
import dataclasses
import os

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
    assert all(p.parent == tmp_path / "c" for p in (tmp_path / "c").rglob(pattern="*") if p.is_file())
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
    with contextlib.suppress(TypeError):
        await cache.put(
            key=KEY,
            value={"x": object()},
        )
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


NOW = 1_800_000_000.0
DAY = 86_400.0


def _touch(
    path,
    age: float,
) -> None:
    path.write_text(
        data="x",
        encoding="utf-8",
    )
    os.utime(
        path,
        (NOW - age, NOW - age),
    )


async def test_stale_temp_files_are_removed_on_first_use(tmp_path):
    stale = tmp_path / ".tmp-old.part"
    fresh = tmp_path / ".tmp-new.part"
    old_result = tmp_path / ("a" * 64 + ".json")
    _touch(
        path=stale,
        age=2 * DAY,
    )
    _touch(
        path=fresh,
        age=DAY / 2,
    )
    _touch(
        path=old_result,
        age=30 * DAY,
    )
    cache = Cache(
        root=tmp_path,
        clock=lambda: NOW,
    )
    assert await cache.get(key=KEY) is None
    assert not stale.exists()
    assert fresh.exists() and old_result.exists()


async def test_stale_temp_cleanup_is_best_effort(tmp_path):
    cache = Cache(
        root=tmp_path / "missing",
        clock=lambda: NOW,
    )
    assert await cache.get(key=KEY) is None  # no directory yet: no error
    await cache.put(
        key=KEY,
        value={"x": 1},
    )
    assert await cache.get(key=KEY) == {"x": 1}
