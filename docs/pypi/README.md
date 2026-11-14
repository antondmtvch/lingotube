# lingotube

lingotube gets subtitles, transcripts and summaries of YouTube videos through YouTube's own chat.
It is a command-line tool for AI agents (Claude Code, Codex, Cursor and others) and for people.

## What it does

- Asks YouTube's chat about a video and returns its transcript, subtitles and summary.
- Writes subtitle files and finds the moment in a video where something is said.
- Works with a YouTube account you sign in to in your own browser.

## Limits

- YouTube's chat is not available in every country (for example, not in Russia and most of the EU)
  and not for every video or account. Check it with `lingotube doctor` before you rely on it.
- The tool uses an internal, undocumented YouTube request. YouTube may change it without notice, and
  then lingotube stops working until it is updated.
- YouTube's Terms of Service do not allow automated access. You use the tool at your own risk, and
  your account can be restricted. Use a separate, ordinary Google account.
- Support is best effort, in free time, with no deadlines.

## Install

```sh
uv tool install --python 3.14 lingotube
```

`--python 3.14` is required until the `lz4` dependency ships Python 3.15 wheels. The latest code on
`main` can be installed with:

```sh
uv tool install --python 3.14 git+https://github.com/antondmtvch/lingotube
```

## First run

```sh
lingotube login
lingotube doctor
```

`lingotube login` opens a browser window to sign in to YouTube. `lingotube doctor` checks the
setup and the chat availability.

## More

The full documentation, the exit codes and the agent skill are in the
[project README](https://github.com/antondmtvch/lingotube#readme).
