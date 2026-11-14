# lingotube

![version](https://img.shields.io/badge/version-0.1.0-blue)
![extension release](https://img.shields.io/github/v/release/antondmtvch/lingotube?filter=extension-v*&label=extension)
![python](https://img.shields.io/badge/python-%E2%89%A53.14-3776AB?logo=python&logoColor=white)
![coverage cli](https://img.shields.io/badge/coverage_cli-96%25-brightgreen)
![coverage extension](https://img.shields.io/badge/coverage_extension-99%25-brightgreen)
[![skills.sh](https://skills.sh/b/antondmtvch/lingotube)](https://skills.sh/antondmtvch/lingotube)

**English** · [Русский](/docs/readme/README.ru.md) · [简体中文](/docs/readme/README.zh-Hans.md) · [繁體中文](/docs/readme/README.zh-Hant.md) · [हिन्दी](/docs/readme/README.hi.md) · [Español](/docs/readme/README.es.md) · [Français](/docs/readme/README.fr.md) · [العربية](/docs/readme/README.ar.md) · [বাংলা](/docs/readme/README.bn.md) · [Português](/docs/readme/README.pt.md) · [ไทย](/docs/readme/README.th.md) · [日本語](/docs/readme/README.ja.md) · [Tiếng Việt](/docs/readme/README.vi.md) · [Deutsch](/docs/readme/README.de.md)

lingotube gets subtitles, a transcript and a summary of a YouTube video. The project has three parts: a command-line tool, a skill for AI agents and a browser extension (in development) that shows translated subtitles over the player.
The text comes from YouTube's built-in chat ("Ask", Gemini) on the video page.
All requests are made on behalf of your YouTube account.

> [!WARNING]
> The tool uses an **internal, undocumented** YouTube chat request. YouTube may change it
> without notice, and the tool will stop working until it is updated. YouTube's Terms of
> Service do not allow automated access: you use the tool at your own risk. Requests are sent
> one at a time with a pause between them, but there is no guarantee that your account will
> not be restricted.

> [!NOTE]
> Questions and answers stay in your account's chat history. The chat is not available in
> Russia and most of the EU, nor under some videos.

**Contents**

- [What's inside](#whats-inside)
- [Command-line tool (CLI)](#command-line-tool-cli)
  - [Features](#features)
  - [Installation](#installation)
  - [Quick start](#quick-start)
  - [Commands](#commands)
  - [Cookies and sign-in](#cookies-and-sign-in)
  - [Translation modes](#translation-modes)
  - [Exit codes](#exit-codes)
- [Skill for AI agents](#skill-for-ai-agents)
- [Browser extension](#browser-extension)
- [Limitations](#limitations)
- [Development](#development)

## What's inside

| Component | What it does |
|---|---|
| [Command-line tool (CLI)](#command-line-tool-cli) | The `lingotube` command: gets subtitles, a transcript and a summary of a video, as files or JSON. |
| [Skill for AI agents](#skill-for-ai-agents) | Lets an AI agent (Claude Code, Codex, Cursor and others) summarize a video, make a transcript or subtitles and find a moment by description. It runs the command-line tool. |
| [Browser extension](#browser-extension) | Translated subtitles over the YouTube player, in any language. In development. |

## Command-line tool (CLI)

Everything in this section is about the `lingotube` command. The skill and the extension have their own sections below.

### Features

- **Subtitles** in any language, in `srt`, `vtt` and `json` formats.
- **Transcript** in the original language with timecodes.
- **Summary** of the video.
- **Three translation modes**: YouTube's built-in chat, your own model with an OpenAI-compatible API,
  or an AI agent that translates the transcript itself.
- **Cache and resume**: long videos are processed in parts, and after a failure work continues where it stopped.
- **Machine-readable output** with `--json` for scripts and AI agents.

### Installation

You need [uv](https://docs.astral.sh/uv/). uv downloads the right Python version itself.

```sh
uv tool install git+https://github.com/antondmtvch/lingotube
```

Or from a local copy of the repository:

```sh
uv tool install .
```

Update and uninstall:

```sh
uv tool upgrade lingotube
uv tool uninstall lingotube
```

### Quick start

1. Sign in to YouTube. In Chrome or Edge the easiest way is:

   ```sh
   lingotube login
   ```

   A browser window opens with a separate lingotube profile. Sign in to your account and **close the
   browser window**: the command waits until you close it. In Firefox, just sign in to YouTube as usual.

2. Check that everything is ready:

   ```sh
   lingotube doctor
   ```

   `doctor` checks the cookie sources, the account sign-in and chat availability on a test video.
   It only opens the chat and writes nothing to it.

3. Get subtitles:

   ```sh
   lingotube subs https://www.youtube.com/watch?v=XXXXXXXXXXX --lang ru
   ```

### Commands

| Command | What it does |
|---|---|
| `lingotube subs <link> --lang ru` | Creates a subtitle file in the chosen language. |
| `lingotube summary <link> --lang ru` | Prints a summary in the chosen language. |
| `lingotube transcript <link>` | Makes a transcript in the original language with timecodes (JSON by default). |
| `lingotube build <link> --lang ru --from <file>` | Takes a ready translation, checks it against the original and builds subtitles. |
| `lingotube login [--browser chrome\|edge]` | Opens a YouTube sign-in window and saves the cookies. |
| `lingotube logout` | Deletes the sign-in profile and the saved cookies. |
| `lingotube doctor` | Checks readiness: cookies, account sign-in and chat on a test video. |

`<link>` is any YouTube video link or a video ID.

Main options:

- `--lang <code>` — result language (`ru`, `en`, `es`, etc.). Without it the language comes from the settings.
- `--format srt|vtt|json` — subtitle format, `srt` by default.
- `-o <path>` — where to write the result. With `-o -` the result goes to standard output.
- `--offset <seconds>` — shift all subtitles; fractional and negative numbers are allowed.
- `--cookies-file <path>` / `--browser <name>` — cookie source.
- `--no-cache` — do not use the cache.
- `--json` — a single JSON document `{"ok", "result", "warnings", "error"}`.

Pass an ID that starts with a hyphen after `--`:

```sh
lingotube subs --lang ru -- -n5MqamatXE
```

### Cookies and sign-in

The tool takes the first suitable source in this order:

1. A `cookies.txt` file: the `--cookies-file` option, the `LINGOTUBE_COOKIES_FILE` variable or the path from the settings.
2. A browser chosen explicitly: the `--browser` option or `browser` in the settings.
3. The lingotube sign-in profile, if it was created by `lingotube login`.
4. Otherwise Firefox, Chrome, Edge and Brave are tried in turn.

On Windows, Chrome and Edge protect their cookies, and they usually cannot be read directly.
For them, use `lingotube login`. Exporting a file remains a fallback.

> [!CAUTION]
> The `cookies.txt` file gives access to your account. Keep it like a password and do not put
> it in repositories or shared folders. Cookies, tokens and authorization headers never appear
> in the output, error messages or `--json`: `***` is printed instead.

If the cookies stop working (exit code `4`), run `lingotube login` again or export a fresh file.

### Translation modes

| Mode | When it is on | Who translates |
|---|---|---|
| **Chat** (default) | nothing is configured | YouTube's chat returns the text in the needed language right away |
| **Own model** | the `[translator]` section is set in the settings | your model with an OpenAI-compatible API |
| **Agent** | `transcript` → translation → `build` | an AI agent or you by hand; lingotube only checks the translation and builds the subtitles |

The settings are in `settings.toml`:

- Windows: `%LOCALAPPDATA%\lingotube\settings.toml`
- macOS: `~/Library/Application Support/lingotube/settings.toml`
- Linux: `~/.config/lingotube/settings.toml`

Example of the "own model" mode:

```toml
lang = "ru"

[translator]
base_url = "https://api.openai.com/v1"   # or a local model, e.g. http://127.0.0.1:11434/v1
model = "gpt-4o-mini"
api_key_env = "LINGOTUBE_API_KEY"        # name of the environment variable with the key
batch_size = 40
```

The key is never written to the settings file: the tool reads it only from the environment variable.

"Agent" mode:

```sh
lingotube transcript <link> -o orig.json          # the original as JSON
# translate the text field of every line, leaving id and time unchanged, and save it as ru.json
lingotube build <link> --lang ru --from ru.json   # check and build the subtitles
```

> [!TIP]
> To keep the translation literal, use the "own model" or "agent" mode: they first get the original,
> and the translation is checked by line numbers. The chat may paraphrase or merge phrases.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | Other error. |
| `2` | Invalid command options. |
| `3` | The chat is unavailable for this video or account. |
| `4` | Sign-in problem: cookies not found or expired, or the model key is not set. |
| `5` | Incomplete result: the file is written, but the transcript does not reach the end of the video. |
| `6` | Network failure after retries ran out. |
| `7` | Data failed validation. |
| `130` | Interrupted by the user (Ctrl+C). |

## Skill for AI agents

The skill runs the [command-line tool](#command-line-tool-cli) for the agent, so install the tool first, then the skill.


The repository has a skill in the open Agent Skills format. With it an AI agent (Claude Code, Codex,
Cursor, Gemini CLI and others) summarizes videos, makes transcripts and subtitles, finds
a moment by description and helps with installation and sign-in.

```sh
npx skills add antondmtvch/lingotube
```

Without Node.js, copy the `skills/lingotube/` folder into your agent's skills folder
(`~/.claude/skills/` for Claude Code or `~/.agents/skills/` for most others).

## Browser extension

A Manifest V3 extension for Chrome, Edge and Firefox that shows translated subtitles over the YouTube player. It is under development.

- A button in the player turns the subtitles on; the panel with the text can be dragged.
- You choose one of 30 languages or type your own.
- Timing and source text come from YouTube's own subtitles; the chat only translates them.
- It works in the browser where you are already signed in to YouTube, so no cookie setup is needed.

It is not in a web store yet. Download the files for your browser from the [releases page](https://github.com/antondmtvch/lingotube/releases):

- Chrome: download `lingotube-<version>-chromium.zip` and unzip it into a folder you will keep. Open `chrome://extensions`, turn on "Developer mode", click "Load unpacked" and choose that folder. Chrome reminds you about extensions in developer mode at startup. To update, replace the files in the folder and click the reload button on the extension's card.
- Edge: use the same archive. Open `edge://extensions`, turn on "Developer mode", click "Load unpacked" and choose the folder.
- Firefox 140 or newer: download `lingotube-<version>-firefox.xpi`, drag the file into the Firefox window (or open `about:addons`, click the gear icon and choose "Install Add-on From File...") and confirm the installation.

Brave, Opera and Vivaldi have not been tested.

## Limitations

These limits apply to all three components, because they all rely on YouTube's chat.


- The chat works only for signed-in users over 13, is not available in every country
  and is not under every video.
- Brand accounts are not supported: the browser's main account is used.
- An hour of video takes several minutes: requests go one at a time.
- Line timing is set by the chat. On long videos individual lines can drift by a few
  seconds; a constant shift is fixed with the `--offset` option.
- The text of long videos is not guaranteed to be verbatim: the chat sometimes answers with a
  text close in meaning, and the tool cannot see this. For important uses, check the result against the recording.
- There is no proxy support.

## Development

Dependencies and the environment are managed with uv:

```sh
uv sync
uv run pytest
uv run ruff check
```

Test coverage (the values in the badges above were measured with these commands and are updated by hand):

```sh
uv run --with pytest-cov pytest --cov=lingotube
cd extension && node --test --experimental-test-coverage --test-coverage-exclude='tests/**' tests/
```

Project structure:

- `src/lingotube/` — the core: CLI, authorization, chat, translation, cache and result writing.
- `skills/lingotube/` — the skill for AI agents.
- `extension/` — the browser extension.
- `tests/` — Python tests.
- `docs/readme/` — translations of this README.
