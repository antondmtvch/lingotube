# First-time setup

Walk the person through these steps in order. Skip a step that already works. Explain each
step in one or two plain sentences: the person may never have used a terminal tool before.
Run any install command only after the person says "yes" to the exact command you showed.

## 0. Consent

Before installing anything, tell the person:

- lingotube works by asking YouTube's own chat about the video, from their YouTube account.
  Every question it sends stays in that account's YouTube chat history.
- The YouTube chat is not available in every country (for example, not in Russia and most of
  the EU) and not for every video or account. You can only check this after sign-in (step 4).
- YouTube's Terms of Service do not allow automated access. The tool uses the person's account
  at their own risk.
- The account can be restricted, and lingotube cannot prevent it.
- Recommend a separate, ordinary Google account (not a brand account) for this, not the main one.
- The owner supports lingotube in free time, best effort, with no deadlines. Fixes come when
  possible; YouTube may change the chat without notice.

Ask whether to proceed.

## 1. uv

lingotube is installed with `uv`, a tool that installs Python programs. Check with
`uv --version`. If it is missing, explain that, show the official installer for their system
and run it only after "yes":

- Windows (PowerShell):
  `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- macOS / Linux:
  `curl -LsSf https://astral.sh/uv/install.sh | sh`

If `uv` is still not found after installing, the terminal does not see it yet: ask the person
to open a new terminal (or restart the agent) and continue from here.

## 2. lingotube

Check with `lingotube --help`. If it is missing, show and (after "yes") run:

```
uv tool install --python 3.14 git+https://github.com/antondmtvch/lingotube
```

Keep `--python 3.14`: without it uv uses the first Python it finds, and on Python 3.15 a
dependency (`lz4`) has no prebuilt package and fails to build. uv downloads Python 3.14 itself
if it is missing.

## 3. Cookies

lingotube signs in to YouTube with the person's browser cookies. Run
`lingotube doctor --json` and ask which browser they use.

- **Firefox:** ask them to sign in to youtube.com in Firefox, then rerun
  `lingotube doctor --json`. lingotube reads Firefox directly.
- **Chrome or Edge:** use `lingotube login` first (add `--browser edge` or `--browser chrome`
  if the person names one). Show the exact command and say what it does: it opens a separate
  lingotube browser window, saves YouTube cookies locally in lingotube's data folder, and
  removes any remembered `cookies_file` / `browser` from lingotube's settings. Run it only after
  the person says "yes". Tell them that a browser window will
  open (a separate lingotube profile, not their own), that they sign in to YouTube there and then
  CLOSE the browser window themselves (it does not close by itself; lingotube saves the
  cookies only after that), that Chrome or Edge is launched without a debugging port, and
  that Google may ask for an identity check such as a selfie, which can be skipped. The command waits up to 10 minutes for the sign-in. If you can run
  commands in the background, run `lingotube login` that way and wait for it to finish;
  otherwise run it with the longest timeout you have; if neither works, ask the person to run
  `lingotube login` in their own terminal and tell you when it is done. Then run
  `lingotube doctor --json`. You only run the command: do not open, close or touch the browser
  window yourself.
  - Exit code 1 with a message that the login profile is open (`Профиль входа lingotube сейчас открыт.`):
    ask the person to close the lingotube login window (or end its lingering background browser process) and retry.
  - If `lingotube login` fails (for example, no Chrome or Edge is found) or the person prefers
    not to use it, fall back to the `cookies.txt` export below.
- **Another browser, or the fallback for Chrome and Edge:** these cannot be read directly (on
  Windows the browser encrypts cookies), so the person exports a `cookies.txt` file. Guide them
  step by step:
  1. Install a browser extension that exports cookies in Netscape `cookies.txt` format (for
     example, "Get cookies.txt LOCALLY").
  2. Open an incognito / InPrivate window (Ctrl+Shift+N) and allow the extension to run in
     incognito in its settings.
  3. Sign in to YouTube in that window.
  4. Open `https://www.youtube.com/robots.txt` and export the cookies with the extension.
  5. Close the incognito window right away (otherwise YouTube rotates the cookies and the
     export goes stale quickly).
  6. Save the file in their home folder, not in a project folder and not in a synced folder
     (it gives access to their account).
  Then run `lingotube doctor --cookies-file "<absolute path>" --json` (for example
  `"$HOME/cookies.txt"`; lingotube does not expand `~`). lingotube remembers the path.

Never open, print or check the contents of the cookies file yourself; only pass its path.
Tell the person that exported cookies can expire after a while (sometimes within an hour);
when that happens, only this step is repeated. Sign-in via `lingotube login` can also stop
working later; the fix is the same.

## 4. Doctor

Read the `lingotube doctor --json` result (`result.checks`, each with `name`, `ok`, `detail`,
`hint`):

- `"ok": true` — ready. Tell the person they can now ask for summaries, transcripts,
  subtitles or a moment in a video.
- Sign-in works but the chat check (`чат на тестовом видео`) is not ok — the YouTube chat is
  unavailable for this country or account. Say so plainly and stop: this cannot be fixed by
  any setting.
- Sign-in does not work — go back to step 3 and use the `hint` text to explain what to do.
- A network error — suggest trying again later.

## Coming back later

If a lingotube command ends with exit code 4 after setup has worked once, the cookies have
expired. Redo only step 3 (and step 4 to confirm); everything else is already in place. If the
person signed in with `lingotube login`, first repeat the step-3 consent: show the
command `lingotube login`, say what it does, and run it only after the person says "yes".
