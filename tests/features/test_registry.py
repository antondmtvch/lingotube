import io

import typer

from lingotube import cli
from lingotube.features.registry import FeatureRegistry


def _hello_feature(
    app: typer.Typer,
    get_context,
) -> None:
    @app.command(name="hello")
    def hello() -> None:
        ctx = get_context()
        ctx.out.write("привет из новой возможности\n")


def _run(
    registry: FeatureRegistry,
    *argv: str,
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.run(
        argv=list(argv),
        out=out,
        err=err,
        context_factory=_no_container,
        registry=registry,
    )
    return code, out.getvalue(), err.getvalue()


def _no_container(
    out,
    err,
):
    from pathlib import Path

    from lingotube.commands import AppContext

    return AppContext(
        container=None,
        out=out,
        err=err,
        cwd=Path("."),
        settings_path=None,
    )  # type: ignore[arg-type]


def test_registry_adding_feature_needs_no_cli_change():
    registry = cli.build_registry()
    registry.add(register=_hello_feature)
    code, out, _ = _run(
        registry,
        "hello",
    )
    assert code == 0
    assert out == "привет из новой возможности\n"


def test_two_registries_are_independent():
    first, second = FeatureRegistry(), FeatureRegistry()
    first.add(register=_hello_feature)
    assert (
        _run(
            first,
            "hello",
        )[0]
        == 0
    )
    code, out, err = _run(
        second,
        "hello",
    )
    assert code == 2
    assert "hello" in err
    # the stock registry is not affected either
    assert (
        _run(
            cli.build_registry(),
            "hello",
        )[0]
        == 2
    )


def test_build_registry_lists_all_features():
    app = typer.Typer()
    cli.build_registry().apply(
        app=app,
        get_context=lambda: None,
    )  # type: ignore[arg-type]
    names = {c.name for c in app.registered_commands}
    assert names == {
        "transcript",
        "subs",
        "summary",
        "build",
        "doctor",
        "login",
        "logout",
    }
