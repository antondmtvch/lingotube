"""Format and safety-wording checks for the agent skill in skills/lingotube/."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "lingotube"


def read_frontmatter(path: Path) -> dict[str, str]:
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
    return (SKILL_DIR / name).read_text(encoding="utf-8")


def test_frontmatter_name_matches_folder():
    fm = read_frontmatter(SKILL_DIR / "SKILL.md")
    assert fm["name"] == "lingotube" == SKILL_DIR.name


def test_description_length_and_single_line():
    d = read_frontmatter(SKILL_DIR / "SKILL.md")["description"]
    assert 1 <= len(d) <= 1024
    assert "\n" not in d
    assert not d.startswith((">", "|"))


def test_description_has_russian_keywords():
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
    assert len(skill_text("SKILL.md").splitlines()) <= 500


def test_no_vpn_anywhere():
    for p in SKILL_DIR.rglob("*.md"):
        assert "vpn" not in p.read_text(encoding="utf-8").lower(), p


def test_every_exit_code_handled():
    t = skill_text("SKILL.md")
    for code in ("0", "1", "2", "3", "4", "5", "6", "7"):
        assert f"| {code} " in t or f"| {code}," in t, code


def test_video_args_after_double_dash():
    assert " -- <url>" in skill_text("SKILL.md")


def test_long_run_guidance():
    t = skill_text("SKILL.md")
    assert "10 minutes" in t
    assert "background" in t


def test_output_outside_repo():
    assert "~/lingotube/" in skill_text("SKILL.md")


def test_cookie_secrecy_rule():
    assert "never read" in skill_text("SKILL.md").lower()


def test_readme_install_commands():
    t = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "npx skills add antondmtvch/lingotube" in t
    assert "~/.agents/skills/" in t
