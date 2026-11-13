---
name: lingotube
description: Summarize, transcribe, subtitle or find a moment in a YouTube video with the lingotube CLI (it asks YouTube's own chat about the video). Use when the person shares a YouTube link or asks what a video is about, wants its text, subtitles in some language, or wants to know where in the video something is said. Also covers first-time setup of lingotube and its YouTube sign-in. Ключевые слова — видео, YouTube, пересказ, субтитры, транскрипция, найти момент.
---

# lingotube

`lingotube` is a command-line tool that gets a transcript, subtitles or a summary of a YouTube
video by asking YouTube's built-in chat. You run it in the terminal and work with its output.

## Hard rules

- **Cookies are secrets.** You never read, print, copy or summarize the cookies file or any
  cookie value. You only pass its path to `lingotube`.
- **Consent first.** You install or change nothing without the person's explicit "yes" to the
  exact command you showed them.
- **Hands off the browser.** You never open, close or change the person's browser, its profiles,
  processes, policies or flags.
- **Chat unavailable means stop.** If lingotube says the YouTube chat is unavailable for this
  video, account or country, say so plainly and stop. Do not suggest workarounds.
- **Reply in the person's language** (the language they write to you in), unless they ask for
  another.
- **Be honest about accuracy.** Timecodes and text come from YouTube's chat. On long videos a
  timecode can be off by several seconds and some lines may not match the speech. Present a
  summary as the chat's summary, a found moment as "approximately here", and never present
  chat text as an exact quote of the speaker.

## Before first use

Run `lingotube doctor --json`. If the command is not found, or the result has `"ok": false`,
follow [references/setup.md](references/setup.md) before doing anything else.

## How to run commands

- Always pass the video after `--`, because video ids may start with `-`:
  `lingotube summary --lang en -o - --json -- <url>`.
- Always add `--json`. The output is one JSON document:
  `{"ok": bool, "result": ..., "warnings": [str], "error": {"code", "message", "hint"} | null}`.
  Show `warnings` to the person briefly; they explain gaps or incomplete results.
- **Long videos take time:** about a few minutes per hour of video. Tell the person they will
  have to wait. If you can run commands in the background, do that and wait for it to finish;
  otherwise run it with a timeout of up to 10 minutes.
- Repeated questions about the same video are answered from lingotube's cache, so they are
  fast and send nothing new to YouTube.

## Where to save files

If the person named a folder, use it. If not, and the current folder is a git repository,
do not write into it: save to `"$HOME/lingotube/<file>"` with `-o` and tell the person the full
path. Otherwise lingotube's default (current folder) is fine.

- lingotube does not expand `~` and does not create folders. Always give `-o` an absolute path;
  `"$HOME/..."` (in double quotes) works in both PowerShell and sh.
- Create the folder first: `New-Item -ItemType Directory -Force "$HOME/lingotube"`
  (PowerShell) or `mkdir -p "$HOME/lingotube"` (sh).

## Summary

```
lingotube summary --lang <lang> -o - --json -- <url>
```

`<lang>` is the language the person writes in (a code such as `en`, `ru`, `es`) unless they ask
for another. `--lang` is required. Retell `result` in your own words, mention that it is
YouTube chat's summary of the video.

## Transcript and subtitles

- Original-language transcript with timecodes:
  `lingotube transcript --json -o <path> -- <url>` (JSON by default; `--format srt|vtt|json`).
- Subtitles in a chosen language:
  `lingotube subs --lang <lang> --format srt --json -o <path> -- <url>` (`srt` or `vtt`).

Tell the person where the file is and give a short gist (a few sentences). Never paste a long
transcript into the conversation; show at most a short excerpt if they ask.

## Find a moment

When the person asks where in the video something is said or shown, follow
[references/find-moment.md](references/find-moment.md).

## Exit codes

| Code | What it means | What you do |
|---|---|---|
| 0 | Success | Work with the result. |
| 1 | Other error (e.g. a file could not be written) | Show the person lingotube's error message (it never contains secrets). |
| 2 | Wrong command options | Fix the command (often a missing `--lang`) and retry once. |
| 3 | YouTube chat unavailable for this video, account or country | Say so plainly. Do not retry, do not suggest workarounds. |
| 4 | Sign-in problem: cookies missing or expired, or a translation model key is missing | Cookies: go to step "3. Cookies" in [references/setup.md](references/setup.md). Model key: explain that the key from the person's lingotube settings is missing and point to the README section "Перевод: три режима"; do not set it up yourself. |
| 5 | Result incomplete (file written, transcript stops before the end) | Tell the person where it stops (see `warnings`) and offer to rerun; a rerun fetches only the missing part. |
| 6 | Network failure after retries | Suggest trying again later. |
| 7 | Invalid input (link, file, settings) | Check the link and arguments, fix and retry once; otherwise explain the message. |

Code 130 means the run was interrupted (Ctrl+C); just tell the person.
