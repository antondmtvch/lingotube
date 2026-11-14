"""On-disk result cache: one JSON file per key, atomic writes, corruption-tolerant.

Holds only results (transcripts, summaries); never account data or secrets.
"""

import asyncio
import contextlib
import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CacheKey:
    """Identifies one cached result.

    Attributes:
        video_id: YouTube video id.
        kind: Kind of result, for example a transcript or a summary.
        language: Language code, or "orig" for the original language.
        mode: How the result was produced.
        prompt_version: Version of the prompts used.
        part: Optional name of a part of a long result.
    """

    video_id: str
    kind: str
    language: str  # "orig" for the original
    mode: str
    prompt_version: str
    part: str = ""

    def digest(self) -> str:
        # JSON-encoded list is unambiguous: no field can collide into another.
        """Return a stable SHA-256 digest of the key, used as the file name.

        Returns:
            A 64-character lowercase hex string.
        """
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


STALE_TEMP_AGE = 86_400.0  # seconds: leftover temp files older than this are removed


class Cache:
    """Stores results as JSON files in one folder.

    Each key maps to one file. Writes are atomic, and a damaged file is read as a miss.
    """

    def __init__(
        self,
        root: Path,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Create a cache in a folder.

        Args:
            root: Folder that holds the cache files. It is created on the first write.
            clock: Function that returns the current time in seconds.
        """
        self._root = root
        self._clock = clock
        self._swept = False

    async def _sweep_once(self) -> None:
        """Best effort, once per instance: remove temp files left by crashed writes."""
        if self._swept:
            return
        self._swept = True
        await asyncio.to_thread(
            self._sweep,
            self._clock(),
        )

    def _sweep(self, now: float) -> None:
        try:
            for path in self._root.glob(pattern=".tmp-*.part"):
                try:
                    if now - path.stat().st_mtime > STALE_TEMP_AGE:
                        path.unlink()
                except OSError:
                    continue
        except OSError:
            return

    def _path(self, key: CacheKey) -> Path:
        return self._root / f"{key.digest()}.json"

    async def get(self, key: CacheKey) -> dict | None:
        """Return the cached value for a key.

        Args:
            key: Key to look up.

        Returns:
            The stored dict, or None if the key is missing or unreadable.
        """
        await self._sweep_once()
        return await asyncio.to_thread(
            self._read,
            self._path(key=key),
        )

    async def put(
        self,
        key: CacheKey,
        value: dict,
    ) -> None:
        """Store a value under a key, replacing any previous value.

        Args:
            key: Key to store the value under.
            value: JSON-serializable dict to store.

        Raises:
            OSError: If the file cannot be written.
        """
        await self._sweep_once()
        await asyncio.to_thread(
            self._write,
            self._path(key=key),
            value,
        )

    async def delete(self, key: CacheKey) -> None:
        """Remove the cached value for a key, if there is one.

        Args:
            key: Key to remove.
        """
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
            with contextlib.suppress(FileNotFoundError):
                os.unlink(path=tmp)


async def put_best_effort(
    cache: Cache,
    key: CacheKey,
    value: dict,
) -> str | None:
    """Store a value in the cache, turning a failed write into a warning.

    A cache write must not lose a result that was already obtained, so the OSError
    is not raised.

    Args:
        cache: Cache to write to.
        key: Key to store the value under.
        value: JSON-serializable dict to store.

    Returns:
        None on success, or a warning that names only the error type.
    """
    try:
        await cache.put(
            key=key,
            value=value,
        )
    except OSError as e:
        return f"could not save to the cache: {type(e).__name__}"
    return None
