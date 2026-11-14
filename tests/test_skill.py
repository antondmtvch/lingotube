"""Checks of the lingotube skill: its front matter, rules and reference files."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "lingotube"


def read_frontmatter(path: Path) -> dict[str, str]:
    """Read the YAML front matter of a skill file.

    Args:
        path: Path of the skill file.

    Returns:
        The front matter as a dict.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---", "SKILL.md must start with YAML frontmatter"
    end = lines.index("---", 1)
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep and not line.startswith((" ", "\t")):
            fields[key.strip()] = value.strip()
    return fields


def skill_text(name: str) -> str:
    """Read a text file of the skill.

    Args:
        name: Path of the file, relative to the skill folder.

    Returns:
        The text of the file.
    """
    return (SKILL_DIR / name).read_text(encoding="utf-8")


def test_frontmatter_name_matches_folder():
    """Check that the skill name in the front matter matches the folder name."""
    fm = read_frontmatter(SKILL_DIR / "SKILL.md")
    assert fm["name"] == "lingotube" == SKILL_DIR.name


def test_description_length_and_single_line():
    """Check that the skill description is a single line of a reasonable length."""
    d = read_frontmatter(SKILL_DIR / "SKILL.md")["description"]
    assert 1 <= len(d) <= 1024
    assert "\n" not in d
    assert not d.startswith((">", "|"))


def test_description_is_a_valid_plain_yaml_scalar():
    """Check that the skill description is a valid plain YAML scalar."""
    d = read_frontmatter(SKILL_DIR / "SKILL.md")["description"]
    assert ": " not in d and " #" not in d and not d.startswith(("'", '"'))


def test_description_has_russian_keywords():
    """Check that the skill description contains the Russian keywords."""
    d = read_frontmatter(SKILL_DIR / "SKILL.md")["description"]
    for word in (
        "видео",
        "YouTube",
        "пересказ",
        "субтитры",
        "транскрипция",
        "найти момент",
    ):
        assert word in d


def test_skill_md_under_500_lines():
    """Check that the skill file has fewer than 500 lines."""
    assert len(skill_text("SKILL.md").splitlines()) <= 500


def test_no_vpn_anywhere():
    """Check that the skill does not mention VPNs."""
    for p in SKILL_DIR.rglob("*.md"):
        assert "vpn" not in p.read_text(encoding="utf-8").lower(), p


def test_every_exit_code_handled():
    """Check that the skill describes every exit code of the CLI."""
    t = skill_text("SKILL.md")
    for code in ("0", "1", "2", "3", "4", "5", "6", "7", "8"):
        assert f"| {code} " in t or f"| {code}," in t, code


def test_video_args_after_double_dash():
    """Check that the skill passes the video after a double dash."""
    assert " -- <url>" in skill_text("SKILL.md")


def test_long_run_guidance():
    """Check that the skill explains how to handle long runs."""
    t = skill_text("SKILL.md")
    assert "10 minutes" in t
    assert "background" in t


def test_output_outside_repo():
    """Check that the skill does not write output into the repository."""
    t = skill_text("SKILL.md")
    assert '"$HOME/lingotube/' in t
    assert 'New-Item -ItemType Directory -Force "$HOME/lingotube"' in t
    assert 'mkdir -p "$HOME/lingotube"' in t


def test_no_tilde_paths_in_commands():
    # lingotube does not expand "~" and Windows PowerShell passes it literally
    """Check that the commands in the skill do not use tilde paths."""
    for p in SKILL_DIR.rglob("*.md"):
        assert "~/" not in p.read_text(encoding="utf-8"), p


def test_cookies_path_is_absolute():
    """Check that the cookies path in the skill is absolute."""
    assert "absolute path" in skill_text("references/setup.md")


def test_find_moment_reads_utf8_on_windows():
    """Check that the find-moment reference explains reading UTF-8 on Windows."""
    assert "Get-Content -Encoding UTF8" in skill_text("references/find-moment.md")


def test_cookie_secrecy_rule():
    """Check that the skill keeps the rule that cookies are secret."""
    assert "never read" in skill_text("SKILL.md").lower()


def test_setup_exists_and_linked():
    """Check that the setup reference exists and is linked from the skill."""
    assert (SKILL_DIR / "references" / "setup.md").is_file()
    assert "references/setup.md" in skill_text("SKILL.md")


def test_setup_install_commands_verbatim():
    """Check that the install commands in the setup reference are exact."""
    t = skill_text("references/setup.md")
    assert 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"' in t
    assert "curl -LsSf https://astral.sh/uv/install.sh | sh" in t
    assert "uv tool install --python 3.14 git+https://github.com/antondmtvch/lingotube" in t


def test_setup_steps_in_order():
    """Check that the setup steps are in the right order."""
    t = skill_text("references/setup.md")
    headings = (
        "## 0. Consent",
        "## 1. uv",
        "## 2. lingotube",
        "## 3. Cookies",
        "## 4. Doctor",
    )
    idx = [t.index(h) for h in headings]
    assert idx == sorted(idx)


def test_setup_reentry_on_exit_4():
    """Check that the setup is started again after exit code 4."""
    t = skill_text("references/setup.md")
    assert "exit code 4" in t
    assert "only step 3" in t


def test_setup_chat_unavailable_stops():
    """Check that the setup stops when the chat is unavailable."""
    t = skill_text("references/setup.md").lower()
    assert "unavailable" in t
    assert "stop" in t


def test_find_moment_exists_and_linked():
    """Check that the find-moment reference exists and is linked from the skill."""
    assert (SKILL_DIR / "references" / "find-moment.md").is_file()
    assert "references/find-moment.md" in skill_text("SKILL.md")


def test_find_moment_link_format():
    """Check the link format in the find-moment reference."""
    t = skill_text("references/find-moment.md")
    assert "https://youtu.be/<id>?t=<seconds>" in t


def test_find_moment_honesty():
    """Check that the find-moment reference asks to mark timecodes as approximate."""
    t = skill_text("references/find-moment.md").lower()
    assert "approximately" in t
    assert "not found" in t


def test_find_moment_reads_in_parts():
    """Check that the find-moment reference reads large transcripts in parts."""
    t = skill_text("references/find-moment.md").lower()
    assert "do not read the whole" in t


def test_readme_install_commands():
    """Check that the install commands in the README match the skill."""
    t = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "npx skills add antondmtvch/lingotube" in t
    assert "~/.agents/skills/" in t
