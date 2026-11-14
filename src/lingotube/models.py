"""Domain models. Transcript JSON format: spec section 8."""

import math
from dataclasses import dataclass
from typing import Any

from lingotube.errors import ValidationError


@dataclass(
    frozen=True,
    slots=True,
)
class Cue:
    """One timed line of a transcript.

    Attributes:
        id: Sequence number of the line.
        start: Start time in seconds from the beginning of the video.
        end: End time in seconds, or None if unknown.
        text: Text of the line.
    """

    id: int
    start: float
    end: float | None
    text: str


@dataclass(
    frozen=True,
    slots=True,
)
class VideoInfo:
    """Basic facts about a video, read from its YouTube page.

    Attributes:
        video_id: YouTube video id.
        duration: Length of the video in seconds.
        title: Title of the video.
        language: Language code of the automatic captions, or None.
    """

    video_id: str
    duration: float
    title: str
    language: str | None


def _is_int(v: object) -> bool:
    return isinstance(
        v,
        int,
    ) and not isinstance(
        v,
        bool,
    )


def _is_num(v: object) -> bool:
    return (
        isinstance(
            v,
            int | float,
        )
        and not isinstance(
            v,
            bool,
        )
        and (isinstance(v, int) or math.isfinite(v))
    )


def _fail(what: str) -> ValidationError:
    return ValidationError(message=f"Invalid transcript: {what}")


@dataclass(
    frozen=True,
    slots=True,
)
class Transcript:
    """Transcript of one video, in the original or a translated language.

    Attributes:
        video_id: YouTube video id.
        duration: Length of the video in seconds.
        language: Language code of the text, or None if unknown.
        prompt_version: Version of the prompts that produced the text.
        cues: Timed lines, in order.
    """

    video_id: str
    duration: float
    language: str | None
    prompt_version: str
    cues: tuple[Cue, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the transcript as a JSON-serializable dict.

        Returns:
            A dict in the transcript JSON format.
        """
        return {
            "video_id": self.video_id,
            "duration": self.duration,
            "language": self.language,
            "prompt_version": self.prompt_version,
            "cues": [{"id": c.id, "start": c.start, "end": c.end, "text": c.text} for c in self.cues],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Transcript:
        """Build a transcript from parsed JSON, checking every field.

        Args:
            d: Parsed JSON object in the transcript format.

        Returns:
            The validated transcript.

        Raises:
            ValidationError: If the data does not match the transcript format.
        """
        if not isinstance(
            d,
            dict,
        ):
            raise _fail(what="expected an object")
        if not isinstance(
            d.get("video_id"),
            str,
        ):
            raise _fail(what="video_id must be a string")
        if not _is_num(v=d.get("duration")):
            raise _fail(what="duration must be a number")
        language = d.get("language")
        if language is not None and not isinstance(
            language,
            str,
        ):
            raise _fail(what="language must be a string or null")
        if not isinstance(
            d.get("prompt_version"),
            str,
        ):
            raise _fail(what="prompt_version must be a string")
        raw = d.get("cues")
        if not isinstance(
            raw,
            list,
        ):
            raise _fail(what="cues must be a list")
        cues: list[Cue] = []
        for i, c in enumerate(raw):
            if not isinstance(
                c,
                dict,
            ):
                raise _fail(what=f"cue #{i} must be an object")
            if not _is_int(v=c.get("id")):
                raise _fail(what=f"cue #{i}: id must be an integer")
            if not _is_num(v=c.get("start")):
                raise _fail(what=f"cue #{i}: start must be a number")
            end = c.get("end")
            if end is not None and not _is_num(v=end):
                raise _fail(what=f"cue #{i}: end must be a number or null")
            if not isinstance(
                c.get("text"),
                str,
            ):
                raise _fail(what=f"cue #{i}: text must be a string")
            cues.append(
                Cue(
                    id=c["id"],
                    start=c["start"],
                    end=end,
                    text=c["text"],
                )
            )
        return cls(
            video_id=d["video_id"],
            duration=d["duration"],
            language=language,
            prompt_version=d["prompt_version"],
            cues=tuple(cues),
        )
