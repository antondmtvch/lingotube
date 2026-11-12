import io
import json
import re
from pathlib import Path

import httpx
import pytest
from dependency_injector import providers

from lingotube import cli
from lingotube.ask.client import AskClient, AskSession
from lingotube.auth.base import Credentials
from lingotube.commands import AppContext
from lingotube.config import Settings, TranslatorSettings
from lingotube.container import build_container
from lingotube.errors import (
    AuthError,
    ChatUnavailableError,
    NetworkError,
    ValidationError,
)
from lingotube.features.build import BuildFeature
from lingotube.features.subtitles import SubtitlesFeature
from lingotube.features.summary import SummaryFeature
from lingotube.features.transcript import TranscriptFeature
from lingotube.models import VideoInfo
from lingotube.translate.openai_compat import OpenAICompatTranslator

VID = "abcdefghijk"
DASH_VID = "-n5MqamatXE"
URL = f"https://www.youtube.com/watch?v={VID}"
_RANGE = re.compile(pattern=r"с (\d+(?::\d\d)+) по (\d+(?::\d\d)+)")
SUMMARY = "Краткое содержание: Привет 日本 ✓"


def _secs(stamp: str) -> int:
    total = 0
    for part in stamp.split(":"):
        total = total * 60 + int(part)
    return total


def _stamp(t: int) -> str:
    return f"{t // 60}:{t % 60:02}"


def full_answer(prompt: str) -> str:
    """Every requested range is answered completely: a line every 10 s."""
    match = _RANGE.search(string=prompt)
    if match is None:
        return SUMMARY
    start, end = _secs(stamp=match.group(1)), _secs(stamp=match.group(2))
    return "\n".join(
        f"({_stamp(t=t)}) реплика {t}"
        for t in range(
            start,
            end,
            10,
        )
    )


def cut_answer(prompt: str) -> str:
    """Speech stops at 1:40 whatever is asked: the video stays incomplete."""
    match = _RANGE.search(string=prompt)
    assert match is not None
    start, end = _secs(stamp=match.group(1)), _secs(stamp=match.group(2))
    stop = min(
        end,
        100,
    )
    if start >= stop:
        return f"({_stamp(t=start)}) конец"
    return "\n".join(
        f"({_stamp(t=t)}) реплика {t}"
        for t in range(
            start,
            stop,
            10,
        )
    )


class FakeSession(AskSession):
    def __init__(self, client: "FakeAsk") -> None:
        self.info = client.info
        self._client = client

    async def ask(self, prompt: str) -> str:
        self._client.prompts.append(prompt)
        result = self._client.answer(prompt)
        if isinstance(
            result,
            BaseException,
        ):
            raise result
        return result


class FakeAsk(AskClient):
    def __init__(
        self,
        duration: float,
        answer,
    ) -> None:
        self.duration = duration
        self.answer = answer
        self.prompts: list[str] = []
        self.opened: list[str] = []
        self.info = VideoInfo(
            video_id=VID,
            duration=duration,
            title="Title",
            language="en",
        )

    async def open(self, video_id: str) -> AskSession:
        self.opened.append(video_id)
        self.info = VideoInfo(
            video_id=video_id,
            duration=self.duration,
            title="Title",
            language="en",
        )
        return FakeSession(client=self)


class FakeCookies:
    async def load(self) -> Credentials:
        return Credentials(cookies={"SAPISID": "x"})


class Harness:
    def __init__(
        self,
        tmp_path: Path,
        *,
        settings: Settings | None = None,
        duration: float = 30.0,
        answer=full_answer,
        env: dict[str, str] | None = None,
    ) -> None:
        self.tmp = tmp_path
        self.settings = settings or Settings()
        self.env = env or {}
        self.ask = FakeAsk(
            duration=duration,
            answer=answer,
        )
        self.asks_made = 0
        self.containers: list = []
        self.overrides: dict[str, providers.Provider] = {}

    def make_ask(self) -> FakeAsk:
        self.asks_made += 1
        return self.ask

    def factory(
        self,
        out,
        err,
    ) -> AppContext:
        container = build_container(
            settings=self.settings,
            env=self.env,
            cache_dir=self.tmp / "cache",
            err=err,
        )
        container.ask_client.override(provider=providers.Singleton(self.make_ask))
        container.cookie_source.override(provider=providers.Object(FakeCookies()))
        for name, provider in self.overrides.items():
            getattr(
                container,
                name,
            ).override(provider=provider)
        self.containers.append(container)
        return AppContext(
            container=container,
            out=out,
            err=err,
            cwd=self.tmp,
            settings_path=self.tmp / "settings.toml",
        )

    def run(
        self,
        *argv: str,
        out=None,
    ) -> tuple[int, str, str]:
        out = out if out is not None else io.StringIO()
        err = io.StringIO()
        code = cli.run(
            argv=list(argv),
            out=out,
            err=err,
            context_factory=self.factory,
        )
        return (
            code,
            (
                out.getvalue()
                if isinstance(
                    out,
                    io.StringIO,
                )
                else ""
            ),
            err.getvalue(),
        )


def test_subs_writes_srt_file_default_name(tmp_path):
    h = Harness(tmp_path=tmp_path)
    code, out, err = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
    )
    assert code == 0, err
    path = tmp_path / f"{VID}.ru.srt"
    text = path.read_bytes().decode("utf-8")
    assert text.startswith("1\n00:00:00,000 --> ")
    assert "реплика 10" in text
    assert out == ""
    assert "Traceback" not in err


def test_subs_stdout_with_dash_o(tmp_path):
    h = Harness(
        tmp_path=tmp_path,
        settings=Settings(chunk_seconds=10),
    )
    code, out, err = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
        "-o",
        "-",
    )
    assert code == 0, err
    assert out.startswith("1\n00:00:00,000 --> ")
    assert "реплика 20" in out
    assert "часть 1 из 3" in err and "часть 3 из 3" in err
    assert not list(tmp_path.glob(pattern="*.srt"))


def test_subs_incomplete_writes_file_and_exits_5(tmp_path):
    h = Harness(
        tmp_path=tmp_path,
        duration=600.0,
        answer=cut_answer,
    )
    code, out, err = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
    )
    assert code == 5
    path = tmp_path / f"{VID}.ru.srt"
    assert path.exists() and "реплика 10" in path.read_text(encoding="utf-8")
    assert "обрывается на" in err
    assert "Traceback" not in err


def test_offset_and_format_flags(tmp_path):
    h = Harness(tmp_path=tmp_path)
    code, _, err = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
        "--format",
        "vtt",
        "--offset",
        "1.5",
    )
    assert code == 0, err
    text = (tmp_path / f"{VID}.ru.vtt").read_text(encoding="utf-8")
    assert text.startswith("WEBVTT\n\n00:00:01.500 --> ")
    code, out, err = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
        "--format",
        "json",
        "--offset",
        "-0.5",
        "-o",
        "-",
    )
    assert code == 0, err
    data = json.loads(s=out)
    assert data["cues"][1]["start"] == 9.5
    code, _, err = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
        "--format",
        "docx",
    )
    assert code == 2 and "docx" in err


def test_lang_from_settings_when_flag_absent(tmp_path):
    h = Harness(
        tmp_path=tmp_path,
        settings=Settings(
            lang="de",
            format="vtt",
        ),
    )
    code, _, err = h.run(
        "subs",
        URL,
    )
    assert code == 0, err
    assert (tmp_path / f"{VID}.de.vtt").exists()
    assert "de" in h.ask.prompts[0]


def test_lang_missing_everywhere_is_usage_error(tmp_path):
    h = Harness(tmp_path=tmp_path)
    code, out, err = h.run(
        "subs",
        URL,
    )
    assert code == 2
    assert "--lang" in err
    assert h.asks_made == 0


def test_transcript_outputs_json_format(tmp_path):
    h = Harness(tmp_path=tmp_path)
    code, out, err = h.run(
        "transcript",
        URL,
        "-o",
        "-",
    )
    assert code == 0, err
    data = json.loads(s=out)
    assert data["video_id"] == VID
    assert data["language"] == "en"
    assert [c["id"] for c in data["cues"]] == [1, 2, 3]
    code, _, err = h.run(
        "transcript",
        URL,
    )
    assert code == 0, err
    assert (
        json.loads(s=(tmp_path / f"{VID}.en.json").read_text(encoding="utf-8"))[
            "video_id"
        ]
        == VID
    )


def test_build_reads_file_and_validates(tmp_path):
    h = Harness(tmp_path=tmp_path)
    assert (
        h.run(
            "transcript",
            URL,
            "-o",
            "orig.json",
        )[0]
        == 0
    )
    data = json.loads(s=(tmp_path / "orig.json").read_text(encoding="utf-8"))
    data["language"] = "ru"
    for cue in data["cues"]:
        cue["text"] = f"перевод {cue['id']}"
    (tmp_path / "ru.json").write_text(
        data=json.dumps(
            obj=data,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    code, _, err = h.run(
        "build",
        URL,
        "--lang",
        "ru",
        "--from",
        "ru.json",
    )
    assert code == 0, err
    assert "перевод 2" in (tmp_path / f"{VID}.ru.srt").read_text(encoding="utf-8")

    data["cues"].pop()
    (tmp_path / "bad.json").write_text(
        data=json.dumps(
            obj=data,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    code, _, err = h.run(
        "build",
        URL,
        "--lang",
        "ru",
        "--from",
        "bad.json",
    )
    assert code == 7
    assert "отсутствуют id: 3" in err

    (tmp_path / "broken.json").write_text(
        data="{not json",
        encoding="utf-8",
    )
    assert (
        h.run(
            "build",
            URL,
            "--lang",
            "ru",
            "--from",
            "broken.json",
        )[0]
        == 7
    )
    assert (
        h.run(
            "build",
            URL,
            "--lang",
            "ru",
            "--from",
            "missing.json",
        )[0]
        == 7
    )


def test_summary_prints_text(tmp_path):
    h = Harness(tmp_path=tmp_path)
    code, out, err = h.run(
        "summary",
        URL,
        "--lang",
        "ru",
    )
    assert code == 0, err
    assert out == SUMMARY + "\n"


@pytest.mark.parametrize(
    argnames="exc,code",
    argvalues=[
        (ChatUnavailableError, 3),
        (AuthError, 4),
        (NetworkError, 6),
        (ValidationError, 7),
    ],
)
def test_exit_codes(
    tmp_path,
    exc,
    code,
):
    h = Harness(
        tmp_path=tmp_path,
        answer=lambda prompt: exc(
            message="что-то сломалось",
            hint="сделайте так",
        ),
    )
    rc, out, err = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
    )
    assert rc == code
    assert "что-то сломалось" in err and "сделайте так" in err
    assert "Traceback" not in err and out == ""


def test_unexpected_error_is_generic_exit_1(tmp_path):
    h = Harness(
        tmp_path=tmp_path,
        answer=lambda prompt: RuntimeError("secret-token-123"),
    )
    rc, out, err = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
        "--json",
    )
    assert rc == 1
    assert "secret-token-123" not in out + err
    assert "Traceback" not in out + err
    assert json.loads(s=out)["error"]["code"] == "error"


def test_json_envelope_success_and_error(tmp_path):
    h = Harness(tmp_path=tmp_path)
    code, out, err = h.run(
        "summary",
        URL,
        "--lang",
        "ru",
        "--json",
    )
    assert code == 0, err
    doc = json.loads(s=out)
    assert doc == {
        "ok": True,
        "result": {"video_id": VID, "language": "ru", "text": SUMMARY},
        "warnings": [],
        "error": None,
    }

    code, out, _ = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
        "--json",
    )
    doc = json.loads(s=out)
    assert code == 0 and doc["ok"] is True
    assert doc["result"]["path"] == str(tmp_path / f"{VID}.ru.srt")
    assert doc["result"]["complete"] is True

    h2 = Harness(
        tmp_path=tmp_path,
        answer=lambda prompt: AuthError(
            message="нет входа",
            hint="войдите",
        ),
    )
    code, out, _ = h2.run(
        "subs",
        URL,
        "--lang",
        "ru",
        "--no-cache",
        "--json",
    )
    assert code == 4
    doc = json.loads(s=out)
    assert doc["ok"] is False and doc["result"] is None
    assert doc["error"] == {"code": "auth", "message": "нет входа", "hint": "войдите"}

    code, out, _ = h.run(
        "subs",
        "--json",
    )  # usage error: still exactly one JSON document
    assert code == 2
    assert json.loads(s=out)["error"]["code"] == "usage"


def test_json_envelope_incomplete(tmp_path):
    h = Harness(
        tmp_path=tmp_path,
        duration=600.0,
        answer=cut_answer,
    )
    code, out, _ = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
        "--json",
    )
    assert code == 5
    doc = json.loads(s=out)
    assert doc["ok"] is False
    assert doc["error"]["code"] == "incomplete"
    assert doc["result"]["complete"] is False
    assert any("обрывается на" in w for w in doc["warnings"])


def test_bad_url_fails_before_any_network(tmp_path):
    h = Harness(tmp_path=tmp_path)
    code, _, err = h.run(
        "subs",
        "https://example.com/watch?v=abcdefghijk",
        "--lang",
        "ru",
    )
    assert code == 7
    assert h.asks_made == 0
    assert all(not c.http.initialized for c in h.containers)


def test_no_cache_flag_passes_use_cache_false(tmp_path):
    calls: list[bool] = []

    class Spy:
        async def run(
            self,
            video_id,
            language,
            *,
            use_cache=True,
        ):
            calls.append(use_cache)
            raise NetworkError(message="стоп")

    h = Harness(tmp_path=tmp_path)
    h.overrides["subtitles_feature"] = providers.Object(Spy())
    h.run(
        "subs",
        URL,
        "--lang",
        "ru",
        "--no-cache",
    )
    h.run(
        "subs",
        URL,
        "--lang",
        "ru",
    )
    assert calls == [False, True]


def test_cyrillic_to_cp1251_stream_does_not_crash(tmp_path):
    raw = io.BytesIO()
    out = io.TextIOWrapper(
        buffer=raw,
        encoding="cp1251",
        errors="strict",
    )
    h = Harness(tmp_path=tmp_path)
    code, _, err = h.run(
        "summary",
        URL,
        "--lang",
        "ru",
        out=out,
    )
    assert code == 0, err
    out.flush()
    assert SUMMARY in raw.getvalue().decode("utf-8")


def test_stream_without_reconfigure_falls_back_to_replace(tmp_path):
    class Strict(io.TextIOBase):
        encoding = "cp1251"

        def __init__(self) -> None:
            self.parts: list[str] = []

        def write(self, s: str) -> int:
            s.encode("cp1251")  # strict
            self.parts.append(s)
            return len(s)

    out = Strict()
    h = Harness(tmp_path=tmp_path)
    code = cli.run(
        argv=["summary", URL, "--lang", "ru"],
        out=out,
        err=io.StringIO(),
        context_factory=h.factory,
    )
    assert code == 0
    assert "Краткое содержание" in "".join(out.parts)


def test_cookies_file_flag_is_remembered_in_settings(tmp_path):
    cookies = tmp_path / "my.cookies.txt"
    cookies.write_text(
        data="# Netscape HTTP Cookie File\n",
        encoding="utf-8",
    )
    h = Harness(tmp_path=tmp_path)
    code, _, err = h.run(
        "summary",
        URL,
        "--lang",
        "ru",
        "--cookies-file",
        "my.cookies.txt",
    )
    assert code == 0, err
    settings_text = (tmp_path / "settings.toml").read_text(encoding="utf-8")
    assert "cookies_file" in settings_text
    assert (
        str(cookies.resolve()).replace(
            "\\",
            "\\\\",
        )
        in settings_text
    )
    effective = h.containers[-1].settings()
    assert effective.cookies_file == cookies and effective.browser is None


def test_cookies_file_and_browser_together_is_usage_error(tmp_path):
    h = Harness(tmp_path=tmp_path)
    code, _, err = h.run(
        "summary",
        URL,
        "--lang",
        "ru",
        "--cookies-file",
        "a.txt",
        "--browser",
        "firefox",
    )
    assert code == 2
    code, _, err = h.run(
        "summary",
        URL,
        "--lang",
        "ru",
        "--browser",
        "netscape",
    )
    assert code == 2 and "netscape" in err


def test_leading_dash_video_id_and_url(tmp_path):
    h = Harness(tmp_path=tmp_path)
    code, _, err = h.run(
        "subs",
        DASH_VID,
        "--lang",
        "ru",
    )
    assert code == 0, err
    code, _, err = h.run(
        "subs",
        "--lang",
        "ru",
        DASH_VID,
        "--no-cache",
    )
    assert code == 0, err
    code, _, err = h.run(
        "subs",
        "--lang",
        "ru",
        "--",
        DASH_VID,
    )
    assert code == 0, err
    code, _, err = h.run(
        "subs",
        f"https://youtu.be/{DASH_VID}",
        "--lang",
        "ru",
        "--no-cache",
    )
    assert code == 0, err
    assert h.ask.opened == [DASH_VID, DASH_VID, DASH_VID]  # third run served from cache
    assert (tmp_path / f"{DASH_VID}.ru.srt").exists()


def test_negative_offset_value_is_not_taken_for_an_id(tmp_path):
    h = Harness(tmp_path=tmp_path)
    code, out, err = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
        "--format",
        "json",
        "-o",
        "-",
        "--offset",
        "-1000000000",
    )
    assert code == 0, err
    assert json.loads(s=out)["cues"] == []  # every cue ends before the shifted zero


def test_translator_key_missing_is_auth_error(tmp_path):
    settings = Settings(
        translator=TranslatorSettings(
            base_url="http://127.0.0.1:9/v1",
            model="m",
        )
    )
    h = Harness(
        tmp_path=tmp_path,
        settings=settings,
        env={"OTHER": "x"},
    )
    code, out, err = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
    )
    assert code == 4
    assert "LINGOTUBE_API_KEY" in err


# --- container ---


def _container(
    tmp_path,
    settings=None,
    env=None,
):
    return build_container(
        settings=settings or Settings(),
        env=env or {},
        cache_dir=tmp_path / "cache",
        err=io.StringIO(),
    )


async def _get(provider):
    value = provider()
    return (
        await value
        if hasattr(
            value,
            "__await__",
        )
        else value
    )


async def _shutdown(container):
    result = container.shutdown_resources()
    if result is not None:
        await result


async def test_container_builds_all_features(tmp_path):
    container = _container(tmp_path=tmp_path)
    try:
        assert isinstance(
            await _get(provider=container.transcript_feature),
            TranscriptFeature,
        )
        assert isinstance(
            await _get(provider=container.subtitles_feature),
            SubtitlesFeature,
        )
        assert isinstance(
            await _get(provider=container.summary_feature),
            SummaryFeature,
        )
        assert isinstance(
            await _get(provider=container.build_feature),
            BuildFeature,
        )
        http = await _get(provider=container.http)
        tr_http = await _get(provider=container.translator_http)
        assert http is not tr_http
        assert http.follow_redirects is False and tr_http.follow_redirects is False
        assert http.cookies.jar.__class__.__name__ == "CookieJar"
    finally:
        await container.shutdown_resources()
    assert http.is_closed


async def test_youtube_client_never_stores_set_cookie(tmp_path):
    container = _container(tmp_path=tmp_path)
    try:
        http = await _get(provider=container.http)
        response = httpx.Response(
            status_code=200,
            headers={"set-cookie": "SID=leak; Domain=.youtube.com; Path=/"},
            request=httpx.Request(
                method="GET",
                url="https://www.youtube.com/",
            ),
        )
        http.cookies.extract_cookies(response=response)
        assert len(http.cookies.jar) == 0
    finally:
        await container.shutdown_resources()


def test_http_resource_closed_after_command(tmp_path):
    seen: list[httpx.AsyncClient] = []
    h = Harness(tmp_path=tmp_path)

    def make(http):
        seen.append(http)
        return h.ask

    original_factory = h.factory

    def factory(
        out,
        err,
    ):
        ctx = original_factory(
            out=out,
            err=err,
        )
        # the fake chat now depends on the real YouTube http resource
        ctx.container.ask_client.override(
            provider=providers.Singleton(
                make,
                http=ctx.container.http,
            )
        )
        return ctx

    h.factory = factory  # type: ignore[method-assign]
    code, _, err = h.run(
        "summary",
        URL,
        "--lang",
        "ru",
    )
    assert code == 0, err
    assert len(seen) == 1 and seen[0].is_closed

    h.ask.answer = lambda prompt: NetworkError(message="сеть")
    code, _, _ = h.run(
        "summary",
        URL,
        "--lang",
        "ru",
        "--no-cache",
    )
    assert code == 6
    assert len(seen) == 2 and seen[1].is_closed


async def test_translator_selected_only_when_configured(tmp_path):
    plain = _container(tmp_path=tmp_path)
    assert await _get(provider=plain.translator) is None
    await _shutdown(container=plain)  # nothing initialized: shutdown is synchronous

    tr = TranslatorSettings(
        base_url="http://127.0.0.1:9/v1",
        model="m",
        api_key_env="MY_KEY",
    )
    configured = _container(
        tmp_path=tmp_path,
        settings=Settings(translator=tr),
        env={"MY_KEY": "k-secret"},
    )
    try:
        assert isinstance(
            await _get(provider=configured.translator),
            OpenAICompatTranslator,
        )
    finally:
        await configured.shutdown_resources()

    missing = _container(
        tmp_path=tmp_path,
        settings=Settings(translator=tr),
        env={"MY_KEY": "  "},
    )
    try:
        with pytest.raises(expected_exception=AuthError) as info:
            await _get(provider=missing.translator)
        assert "MY_KEY" in (info.value.hint or "")
    finally:
        await _shutdown(container=missing)


# --- fix round 1 ---


def _broken_settings_factory(tmp_path):
    from lingotube.config import load_settings

    bad = tmp_path / "settings.toml"
    bad.write_text(
        data="format = 'docx'\n",
        encoding="utf-8",
    )
    calls: list[int] = []

    def factory(
        out,
        err,
    ):
        calls.append(1)
        settings = load_settings(
            path=bad,
            env={},
        )  # raises ValidationError
        raise AssertionError(f"unreachable {settings}")

    return factory, calls


def test_broken_settings_do_not_break_help(tmp_path):
    factory, calls = _broken_settings_factory(tmp_path=tmp_path)
    out, err = io.StringIO(), io.StringIO()
    assert (
        cli.run(
            argv=["--help"],
            out=out,
            err=err,
            context_factory=factory,
        )
        == 0
    )
    assert (
        cli.run(
            argv=["subs", "--help"],
            out=out,
            err=err,
            context_factory=factory,
        )
        == 0
    )
    assert calls == []  # the context is built only when a command actually runs


def test_broken_settings_fail_the_command_with_exit_7(tmp_path):
    factory, calls = _broken_settings_factory(tmp_path=tmp_path)
    out, err = io.StringIO(), io.StringIO()
    assert (
        cli.run(
            argv=["subs", VID, "--lang", "ru"],
            out=out,
            err=err,
            context_factory=factory,
        )
        == 7
    )
    assert "format" in err.getvalue() and "Traceback" not in err.getvalue()
    assert out.getvalue() == ""

    out, err = io.StringIO(), io.StringIO()
    assert (
        cli.run(
            argv=["subs", VID, "--lang", "ru", "--json"],
            out=out,
            err=err,
            context_factory=factory,
        )
        == 7
    )
    doc = json.loads(s=out.getvalue())
    assert doc["ok"] is False and doc["error"]["code"] == "validation"
    assert len(calls) == 2


def test_context_built_once_per_invocation(tmp_path):
    h = Harness(tmp_path=tmp_path)
    assert (
        h.run(
            "summary",
            URL,
            "--lang",
            "ru",
        )[0]
        == 0
    )
    assert len(h.containers) == 1


def test_unexpected_failure_outside_command_body_is_generic_exit_1(tmp_path):
    def factory(
        out,
        err,
    ):
        raise RuntimeError("secret-xyz")

    out, err = io.StringIO(), io.StringIO()
    assert (
        cli.run(
            argv=["summary", URL, "--lang", "ru"],
            out=out,
            err=err,
            context_factory=factory,
        )
        == 1
    )
    assert "RuntimeError" in err.getvalue()
    assert "secret-xyz" not in out.getvalue() + err.getvalue()

    class Broken(io.StringIO):
        def write(self, s):
            raise OSError("pipe closed secret-xyz")

    h = Harness(tmp_path=tmp_path)
    code = cli.run(
        argv=["summary", URL, "--lang", "ru"],
        out=Broken(),
        err=Broken(),
        context_factory=h.factory,
    )
    assert code == 1


def test_failed_write_keeps_previous_file(
    tmp_path,
    monkeypatch,
):
    import lingotube.commands as commands_module

    h = Harness(tmp_path=tmp_path)
    target = tmp_path / f"{VID}.ru.srt"
    target.write_text(
        data="old content",
        encoding="utf-8",
    )

    real_fdopen = commands_module.os.fdopen

    def half_then_fail(
        fd,
        *args,
        **kwargs,
    ):
        f = real_fdopen(
            fd,
            *args,
            **kwargs,
        )
        # only the output writer (the cache writes stay real)
        if kwargs.get("newline") != "":
            return f
        real_write = f.write

        def write(s):
            real_write(s[: len(s) // 2])
            raise OSError(
                28,
                "No space left on device",
            )

        f.write = write
        return f

    monkeypatch.setattr(
        target=commands_module.os,
        name="fdopen",
        value=half_then_fail,
    )
    code, _, err = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
    )
    assert code == 1
    assert "Не удалось записать файл" in err
    assert target.read_text(encoding="utf-8") == "old content"
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == [target.name]
    monkeypatch.undo()

    real_replace = commands_module.os.replace

    def fail_replace(
        src,
        dst,
    ):
        if Path(dst) != target:
            return real_replace(
                src=src,
                dst=dst,
            )
        raise PermissionError(
            13,
            "Access is denied",
        )

    monkeypatch.setattr(
        target=commands_module.os,
        name="replace",
        value=fail_replace,
    )
    code, _, _ = h.run(
        "subs",
        URL,
        "--lang",
        "ru",
    )
    assert code == 1
    assert target.read_text(encoding="utf-8") == "old content"
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == [target.name]
