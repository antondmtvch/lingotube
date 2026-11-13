# Find a moment in a video

The person describes something ("where does he talk about taxes?") and wants to know where in
the video it is.

## 1. Get the transcript into a file

```
lingotube transcript --format json -o <file> --json -- <url>
```

Choose `<file>` by the rules in SKILL.md ("Where to save files"). If you already made this
transcript in the conversation, reuse the file; repeated runs come from lingotube's cache and
send nothing to YouTube.

The file looks like:

```json
{"video_id": "...", "duration": 3484.0, "language": "ru",
 "cues": [{"id": 1, "start": 0.0, "end": 1.5, "text": "..."}, ...]}
```

`start` and `end` are seconds from the beginning of the video. `language` is the language of
the speech; the text is in that language.

## 2. Search without flooding your context

Do not read the whole transcript at once: an hour of video is tens of thousands of words.

1. Search the file for words that would be said about the topic, in the transcript's
   language: the words themselves, their other forms (for example, other word endings), and
   synonyms. Use your terminal's text search (for example `grep -n -i` or `Select-String`).
2. Read the cues around each hit (a few before and after) to understand the context.
3. If nothing matches, read the cues in order in chunks (for example 100 cues at a time) and
   look for the topic by meaning, not by exact words.

Decide by meaning: a word match in an unrelated sentence is not a hit.

## 3. Answer

For each matching place give:

- the time as `m:ss` (or `h:mm:ss` for videos longer than an hour), from the cue's `start`;
- a short quote from the transcript, in the original language, plus a translation if the
  person writes in another language;
- a link that opens the video at that place: `https://youtu.be/<id>?t=<seconds>`, where
  `<seconds>` is the cue's `start` rounded down to a whole number.

Say it is approximately here: timecodes can be off by several seconds, and the text is
YouTube chat's transcription, not an exact record of the speech.

If there are several matching places, list them all (most relevant first). If nothing in the
transcript matches, say plainly that it was not found. Never offer the nearest unrelated
place as if it were the answer.
