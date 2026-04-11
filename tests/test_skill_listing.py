from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import codex


def _write_skill(root: Path, skill_name: str, description: str) -> None:
    skill_dir = root / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {skill_name}\n"
        f"description: {description}\n"
        "---\n"
        f"Use {skill_name}.\n",
        encoding="utf-8",
    )


def test_list_visible_skills_includes_builtin_shared_and_user(monkeypatch, tmp_path):
    builtin_root = tmp_path / "builtin"
    shared_root = tmp_path / "shared"
    user_root = tmp_path / "user" / "default"

    _write_skill(builtin_root, "openai-docs", "Built-in OpenAI docs skill.")
    _write_skill(shared_root, "shared-skill-test", "Shared skill verification.")
    _write_skill(user_root, "default-skill-test", "Default user private skill.")

    monkeypatch.setattr(codex, "get_builtin_skill_root", lambda: builtin_root)
    monkeypatch.setattr(codex, "get_system_skill_root", lambda: shared_root)
    monkeypatch.setattr(codex, "get_user_skill_root", lambda user_id: user_root)

    skills = codex.list_visible_skills("default")

    assert skills == [
        {
            "name": "default-skill-test",
            "description": "Default user private skill.",
            "scope": "user",
        },
        {
            "name": "shared-skill-test",
            "description": "Shared skill verification.",
            "scope": "shared",
        },
        {
            "name": "openai-docs",
            "description": "Built-in OpenAI docs skill.",
            "scope": "builtin",
        },
    ]


def test_list_visible_skills_user_scope_overrides_shared_and_builtin(monkeypatch, tmp_path):
    builtin_root = tmp_path / "builtin"
    shared_root = tmp_path / "shared"
    user_root = tmp_path / "user" / "default"

    _write_skill(builtin_root, "skill-a", "builtin")
    _write_skill(shared_root, "skill-a", "shared")
    _write_skill(user_root, "skill-a", "user")

    monkeypatch.setattr(codex, "get_builtin_skill_root", lambda: builtin_root)
    monkeypatch.setattr(codex, "get_system_skill_root", lambda: shared_root)
    monkeypatch.setattr(codex, "get_user_skill_root", lambda user_id: user_root)

    skills = codex.list_visible_skills("default")

    assert skills == [
        {
            "name": "skill-a",
            "description": "user",
            "scope": "user",
        }
    ]


def test_read_skill_metadata_strips_yaml_quotes(tmp_path):
    skill_dir = tmp_path / "quoted-skill"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\n"
        'name: "imagegen"\n'
        'description: "Generate images."\n'
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )

    metadata = codex.read_skill_metadata(skill_file)

    assert metadata == {
        "name": "imagegen",
        "description": "Generate images.",
    }
