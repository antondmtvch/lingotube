# Find a moment in a video

The person describes something ("where does he talk about taxes?") and wants to know where in
the video it is.

## 1. Get the transcript into a file

```
lingotube transcript --format json -o <file> --json -- <url>
```

This file is only a working copy for your search, not something the person asked for. Do
not apply "Where to save files" from SKILL.md: put it in a temporary folder (your scratchpad
or the system temp folder, e.g. `$TEMP/lingotube-<id>.json`), never in the person's home
folder or the current repository. Delete it when you have answered, and do not mention it as a
result. Save a transcript to a visible place only if the person asked for the transcript
itself. If you already made this transcript in the conversation, reuse the file; repeated
runs come from lingotube's cache and send nothing to YouTube.

The file looks like:

```json
{"video_id": "...", "duration": 3484.0, "language": "ru",
 "cues": [{"id": 1, "start": 0.0, "end": 1.5, "text": "..."}, ...]}
```

`start` and `end` are seconds from the beginning of the video. `language` is the language of
YouTube's auto-generated caption track, and it can differ from the real speech (for example
`ar` for an English video). Do not trust it: before searching, read the first 10-20 cues,
decide the language of the text from the text itself, and search in that language.

## 2. Search without flooding your context

Do not read the whole transcript at once: an hour of video is tens of thousands of words.

1. Search the file for words that would be said about the topic, in the transcript's
   language: the words themselves, their other forms (for example, other word endings), and
   synonyms. Use your terminal's text search (for example `grep -n -i` or `Select-String`).
   The file is UTF-8: in Windows PowerShell read it with `Get-Content -Encoding UTF8`, otherwise
   non-Latin text (for example Russian) comes back garbled. The file is indented JSON, about
   six lines per cue.
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
