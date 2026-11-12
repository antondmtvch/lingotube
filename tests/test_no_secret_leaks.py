"""No secret ever reaches stdout, stderr, the cache or result files.

Real implementations run end to end (container, file/browser cookie sources, the
YouTube chat client, the OpenAI-compatible translator); only the network is
replaced by respx and the browser cookie store by a loader. Every secret carries
the marker LEAKME exactly where the real code would see it: cookie values in the
cookies file and the browser store, chat tokens and visitor data inside YouTube's
responses (and inside transport-error texts), the model key in the environment.
"""

import io
import json
import re
from pathlib import Path

import httpx
import pytest
import respx
from dependency_injector import providers

from lingotube import cli
from lingotube.commands import AppContext
from lingotube.config import Settings, TranslatorSettings
from lingotube.container import build_container

MARK = "LEAKME"
SAPISID = "LEAKME_SAPISID"
SID = "LEAKME_SID"
TOKEN = "LEAKME_TOKEN"
KEY = "LEAKME_KEY"
KEY_ENV = "LT_TEST_KEY"
VID = "abcdefghijk"
URL = f"https://www.youtube.com/watch?v={VID}"
FIX = Path(__file__).parent / "fixtures"
YT = "https://www.youtube.com"
MODEL_URL = "https://model.test/v1/chat/completions"
_RANGE = re.compile(r"с (\d+(?::\d\d)+) по (\d+(?::\d\d)+)")


def _secs(stamp: str) -> int:
    total = 0
    for part in stamp.split(":"):
        total = total * 60 + int(part)
    return total


def _stamp(t: int) -> str:
    return f"{t // 60}:{t % 60:02}"


def _answer(prompt: str, stop: int | None) -> str:
    match = _RANGE.search(prompt)
    if match is None:
        return "Краткое содержание видео."
    start, end = _secs(match.group(1)), _secs(match.group(2))
    end = min(end, stop) if stop is not None else end
    if start >= end:
        return f"({_stamp(start)}) конец"
    return "\n".join(f"({_stamp(t)}) реплика {t}" for t in range(start, end, 10))


def watch_page(duration: int) -> str:
    cfg = {
        "LOGGED_IN": True,
        "INNERTUBE_CONTEXT": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20260101.00.00",
                "hl": "ru",
                "visitorData": f"{TOKEN}_VISITOR",
            }
        },
    }
    player = {
        "videoDetails": {
            "videoId": VID,
            "title": "Видео",
            "lengthSeconds": str(duration),
        },
        "captions": {
            "playerCaptionsTracklistRenderer": {
                "captionTracks": [
                    {
                        "languageCode": "en",
                        "kind": "asr",
                        "baseUrl": "https://www.youtube.com/api/timedtext?v=x",
                    }
                ]
            }
        },
    }
    return (
        f"<html><body><script>ytcfg.set({json.dumps(cfg)});</script>"
        f"<script>var ytInitialPlayerResponse = {json.dumps(player)};</script></body></html>"
    )


def next_response(name: str = "next_eligible.json") -> dict:
    text = (FIX / name).read_text(encoding="utf-8")
    return json.loads(
        text.replace("FAKE_CONTINUATION_1", f"{TOKEN}_CONT").replace(
            "FAKE_CTP_1", f"{TOKEN}_CTP"
        )
    )


def panel_response(answer: str) -> dict:
    return {
        "responseContext": {"mainAppWebResponseContext": {"loggedOut": False}},
        "items": [
            {"youChatItemViewModel": {"id": "a", "text": {"content": answer}}},
            {"chips": {"continuation": f"{TOKEN}_CHIP"}},
        ],
        "footer": {
            "sendUserQueryCommand": {
                "innertubeCommand": {
                    "clickTrackingParams": f"{TOKEN}_CTP2",
                    "continuationCommand": {"token": f"{TOKEN}_NEXT"},
                }
            }
        },
    }


def prompt_of(request: httpx.Request) -> str:
    return json.loads(request.content)["formData"]["inputComposerFormData"][
        "userInputText"
    ]


# --- YouTube scenarios ---

YT_SCENARIOS = [
    "ok",
    "incomplete",
    "signed_out",
    "forbidden",
    "no_chat",
    "http_500",
    "transport",
    "not_json",
    "internal",
    "empty_answer",
    "no_cookies",
    "browser_ok",
    "browser_fails",
]
TR_SCENARIOS = [
    "tr_ok",
    "tr_401",
    "tr_500",
    "tr_transport",
    "tr_redirect",
    "tr_garbage",
]


def failure(request: httpx.Request, scenario: str, known: str) -> httpx.Response | None:
    """The response (or raised error) of a failing endpoint; None when it should work.

    `known`: a chat token the client already holds when this endpoint is called."""
    if scenario == "http_500":
        return httpx.Response(500, text=f"oops {known} {SAPISID}")
    if scenario == "transport":
        raise httpx.ConnectError(
            f"connect failed {known} {SAPISID} {SID}", request=request
        )
    if scenario == "not_json":
        return httpx.Response(200, text=f"<html>{known}</html>")
    if scenario == "internal":
        raise RuntimeError(f"unexpected {known} {SAPISID}")
    return None


def route_youtube(
    router: respx.MockRouter, scenario: str, fail_at: str = "get_panel"
) -> None:
    """`fail_at`: which endpoint the transport/HTTP/internal failures hit."""
    duration = 600 if scenario == "incomplete" else 30
    if scenario == "forbidden":
        router.get(f"{YT}/watch").mock(
            return_value=httpx.Response(403, text=f"denied {TOKEN}")
        )
    else:
        router.get(f"{YT}/watch").mock(
            return_value=httpx.Response(200, text=watch_page(duration))
        )
    nxt = {"signed_out": "next_signed_out.json", "no_chat": "next_no_chat.json"}.get(
        scenario, "next_eligible.json"
    )

    def next_(request: httpx.Request) -> httpx.Response:
        failed = (
            failure(request, scenario, f"{TOKEN}_VISITOR")
            if fail_at == "next"
            else None
        )
        return failed or httpx.Response(200, json=next_response(nxt))

    def panel(request: httpx.Request) -> httpx.Response:
        failed = (
            failure(request, scenario, f"{TOKEN}_CONT")
            if fail_at == "get_panel"
            else None
        )
        if failed is not None:
            return failed
        if scenario == "empty_answer":
            return httpx.Response(200, json=panel_response("Не могу ответить."))
        stop = 100 if scenario == "incomplete" else None
        return httpx.Response(
            200, json=panel_response(_answer(prompt_of(request), stop))
        )

    router.post(f"{YT}/youtubei/v1/next").mock(side_effect=next_)
    router.post(f"{YT}/youtubei/v1/get_panel").mock(side_effect=panel)


def route_translator(router: respx.MockRouter, scenario: str) -> None:
    def model(request: httpx.Request) -> httpx.Response:
        if scenario == "tr_401":
            return httpx.Response(401, json={"error": f"bad key {KEY}"})
        if scenario == "tr_500":
            return httpx.Response(500, text=f"server error {KEY}")
        if scenario == "tr_transport":
            raise httpx.ConnectError(f"cannot reach model with {KEY}", request=request)
        if scenario == "tr_redirect":
            return httpx.Response(
                302, headers={"location": f"https://evil.test/?k={KEY}"}
            )
        if scenario == "tr_garbage":
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "не перевод"}}]}
            )
        user = json.loads(request.content)["messages"][1]["content"]
        lines = [line.split("\t", 1) for line in user.split("\n")]
        content = "\n".join(f"{n}\tперевод {text}" for n, text in lines)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}]}
        )

    router.post(MODEL_URL).mock(side_effect=model)


# --- harness ---


def write_cookies(path: Path, with_sapisid: bool = True) -> None:
    lines = ["# Netscape HTTP Cookie File"]
    if with_sapisid:
        lines.append(f".youtube.com\tTRUE\t/\tTRUE\t2000000000\tSAPISID\t{SAPISID}")
    lines.append(f"#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t2000000000\tSID\t{SID}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class Leak:
    def __init__(self, tmp_path: Path, scenario: str) -> None:
        self.tmp = tmp_path
        self.scenario = scenario
        self.cookies = tmp_path / "secret.cookies.txt"
        write_cookies(
            self.cookies, with_sapisid=scenario not in ("no_cookies", "browser_fails")
        )
        translator = (
            TranslatorSettings(
                base_url="https://model.test/v1", model="m", api_key_env=KEY_ENV
            )
            if scenario.startswith("tr_")
            else None
        )
        self.settings = Settings(
            cookies_file=self.cookies,
            min_interval=0.0,
            max_retries=1,
            translator=translator,
        )
        self.env = {KEY_ENV: KEY}
        self.loaded_browsers: list[str] = []

    def browser_loader(self, browser: str) -> dict[str, str]:
        self.loaded_browsers.append(browser)
        if self.scenario == "browser_ok" or (
            self.scenario == "ok" and browser == "firefox"
        ):
            return {"SAPISID": SAPISID, "SID": SID}
        raise OSError(f"cannot decrypt {SID} in C:/profiles/{SAPISID}/Cookies")

    def factory(self, out, err) -> AppContext:
        container = build_container(
            settings=self.settings, env=self.env, cache_dir=self.tmp / "cache", err=err
        )
        # never touch a real browser profile in tests
        container.browser_loader.override(providers.Object(self.browser_loader))
        return AppContext(
            container=container,
            out=out,
            err=err,
            cwd=self.tmp,
            settings_path=self.tmp / "settings.toml",
        )

    def run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = cli.run(list(argv), out=out, err=err, context_factory=self.factory)
        return code, out.getvalue(), err.getvalue()

    def assert_clean(self, code: int, out: str, err: str, json_mode: bool) -> None:
        assert MARK not in out, out
        assert MARK not in err, err
        for path in self.tmp.rglob("*"):
            if path.is_file() and path != self.cookies:
                assert MARK not in path.read_text(
                    encoding="utf-8", errors="replace"
                ), path
        assert "Traceback" not in out + err
        if json_mode:
            doc = json.loads(out)
            assert doc["ok"] is (code == 0)


def browser_args(scenario: str) -> list[str]:
    return ["--browser", "firefox"] if scenario.startswith("browser_") else []


def youtube_saw_cookies(router: respx.MockRouter) -> bool:
    return any(SAPISID in c.request.headers.get("cookie", "") for c in router.calls)


MODES = [pytest.param(False, id="plain"), pytest.param(True, id="json")]


@pytest.fixture
def router():
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        yield mock


@pytest.mark.parametrize("json_mode", MODES)
@pytest.mark.parametrize("scenario", YT_SCENARIOS + TR_SCENARIOS)
def test_subs_never_leaks(tmp_path, router, scenario, json_mode):
    route_youtube(router, "ok" if scenario.startswith("tr_") else scenario)
    route_translator(router, scenario)
    leak = Leak(tmp_path, scenario)
    argv = [
        "subs",
        URL,
        "--lang",
        "ru",
        *browser_args(scenario),
        *(["--json"] if json_mode else []),
    ]
    code, out, err = leak.run(*argv)
    leak.assert_clean(code, out, err, json_mode)
    if scenario not in ("no_cookies", "browser_fails"):
        assert youtube_saw_cookies(router)  # the secrets really were in play
    if scenario.startswith("tr_"):
        model_calls = [c for c in router.calls if c.request.url.host == "model.test"]
        assert (
            model_calls
            and model_calls[0].request.headers["authorization"] == f"Bearer {KEY}"
        )
    expected = {"ok": 0, "tr_ok": 0, "browser_ok": 0, "incomplete": 5}.get(scenario)
    if expected is not None:
        assert code == expected, err
    else:
        assert code != 0


@pytest.mark.parametrize("json_mode", MODES)
@pytest.mark.parametrize("scenario", YT_SCENARIOS)
def test_transcript_never_leaks(tmp_path, router, scenario, json_mode):
    route_youtube(router, scenario)
    leak = Leak(tmp_path, scenario)
    argv = [
        "transcript",
        URL,
        *browser_args(scenario),
        *(["--json"] if json_mode else []),
    ]
    code, out, err = leak.run(*argv)
    leak.assert_clean(code, out, err, json_mode)
    assert (code == 0) is (scenario in ("ok", "browser_ok"))


@pytest.mark.parametrize("json_mode", MODES)
@pytest.mark.parametrize("scenario", [s for s in YT_SCENARIOS if s != "incomplete"])
def test_summary_never_leaks(tmp_path, router, scenario, json_mode):
    route_youtube(router, scenario)
    leak = Leak(tmp_path, scenario)
    argv = [
        "summary",
        URL,
        "--lang",
        "ru",
        *browser_args(scenario),
        *(["--json"] if json_mode else []),
    ]
    code, out, err = leak.run(*argv)
    leak.assert_clean(code, out, err, json_mode)
    assert (code == 0) is (scenario in ("ok", "browser_ok", "empty_answer"))


BUILD_CASES = [
    "ok",
    "missing_ids",
    "broken_json",
    "missing_file",
    "no_original",
    "wrong_video",
]


@pytest.mark.parametrize("json_mode", MODES)
@pytest.mark.parametrize("case", BUILD_CASES)
def test_build_never_leaks(tmp_path, router, case, json_mode):
    route_youtube(router, "ok")
    leak = Leak(tmp_path, "ok")
    if case != "no_original":
        assert leak.run("transcript", URL, "-o", "orig.json")[0] == 0
        data = json.loads((tmp_path / "orig.json").read_text(encoding="utf-8"))
    else:
        data = {
            "video_id": VID,
            "duration": 30,
            "language": "en",
            "prompt_version": "1",
            "cues": [{"id": 1, "start": 0.0, "end": 2.0, "text": "a"}],
        }
    data["language"] = "ru"
    for cue in data["cues"]:
        cue["text"] = f"перевод {cue['id']}"
    if case == "missing_ids":
        data["cues"].pop()
    if case == "wrong_video":
        data["video_id"] = "zzzzzzzzzzz"
    source = tmp_path / "ru.json"
    if case == "broken_json":
        source.write_text("{not json", encoding="utf-8")
    elif case != "missing_file":
        source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    code, out, err = leak.run(
        "build",
        URL,
        "--lang",
        "ru",
        "--from",
        "ru.json",
        *(["--json"] if json_mode else []),
    )
    leak.assert_clean(code, out, err, json_mode)
    assert (code == 0) is (case == "ok")


DOCTOR_SCENARIOS = [
    "ok",
    "signed_out",
    "forbidden",
    "no_chat",
    "http_500",
    "transport",
    "not_json",
    "internal",
    "no_cookies",
    "browser_ok",
    "browser_fails",
]


@pytest.mark.parametrize("json_mode", MODES)
@pytest.mark.parametrize("scenario", DOCTOR_SCENARIOS)
def test_doctor_never_leaks(tmp_path, router, scenario, json_mode):
    route_youtube(router, scenario, fail_at="next")  # doctor only opens the chat
    leak = Leak(tmp_path, scenario)
    argv = [
        "doctor",
        "--video",
        VID,
        *browser_args(scenario),
        *(["--json"] if json_mode else []),
    ]
    code, out, err = leak.run(*argv)
    leak.assert_clean(code, out, err, json_mode)
    assert (
        leak.loaded_browsers
    )  # browser sources were checked with secret-bearing failures
    if scenario not in ("no_cookies", "browser_fails"):
        assert youtube_saw_cookies(router)
    assert not any(
        c.request.url.path.endswith("get_panel") for c in router.calls
    )  # open() only, never ask
    expected = {
        "ok": 0,
        "browser_ok": 0,
        "no_chat": 3,
        "signed_out": 4,
        "forbidden": 4,
        "no_cookies": 4,
        "browser_fails": 4,
        "http_500": 6,
        "transport": 6,
        "not_json": 6,
        "internal": 1,
    }
    assert code == expected[scenario], out + err
