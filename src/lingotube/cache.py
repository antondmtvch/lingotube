"""On-disk result cache: one JSON file per key, atomic writes, corruption-tolerant.

Holds only results (transcripts, summaries); never account data or secrets.
"""

import asyncio
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CacheKey:
    video_id: str
    kind: str
    language: str  # "orig" for the original
    mode: str
    prompt_version: str
    part: str = ""

    def digest(self) -> str:
        # JSON-encoded list is unambiguous: no field can collide into another.
        raw = json.dumps(
            obj=[
                self.video_id,
                self.kind,
                self.language,
                self.mode,
                self.prompt_version,
                self.part,
            ],
            ensure_ascii=True,
        )
        return hashlib.sha256(data=raw.encode("ascii")).hexdigest()


class Cache:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, key: CacheKey) -> Path:
        return self._root / f"{key.digest()}.json"

    async def get(self, key: CacheKey) -> dict | None:
        return await asyncio.to_thread(
            self._read,
            self._path(key=key),
        )

    async def put(
        self,
        key: CacheKey,
        value: dict,
    ) -> None:
        await asyncio.to_thread(
            self._write,
            self._path(key=key),
            value,
        )

    async def delete(self, key: CacheKey) -> None:
        await asyncio.to_thread(
            self._path(key=key).unlink,
            True,
        )

    @staticmethod
    def _read(path: Path) -> dict | None:
        try:
            data = json.loads(s=path.read_text(encoding="utf-8"))
        except OSError, ValueError:  # missing, unreadable, truncated, bad encoding
            return None
        return (
            data
            if isinstance(
                data,
                dict,
            )
            else None
        )

    def _write(
        self,
        path: Path,
        value: dict,
    ) -> None:
        payload = json.dumps(
            obj=value,
            ensure_ascii=False,
        )
        self._root.mkdir(
            parents=True,
            exist_ok=True,
        )
        fd, tmp = tempfile.mkstemp(
            dir=self._root,
            prefix=".tmp-",
            suffix=".part",
        )
        try:
            with os.fdopen(
                fd=fd,
                mode="w",
                encoding="utf-8",
            ) as f:
                f.write(payload)
            os.replace(
                src=tmp,
                dst=path,
            )
        finally:
            try:
                os.unlink(path=tmp)
            except FileNotFoundError:
                pass


async def put_best_effort(
    cache: Cache,
    key: CacheKey,
    value: dict,
) -> str | None:
    """Cache writes must not lose a result already obtained: returns a warning
    (error type only, no paths) instead of raising."""
    try:
        await cache.put(
            key=key,
            value=value,
        )
    except OSError as e:
        return f"не удалось сохранить в кэш: {type(e).__name__}"
    return None
