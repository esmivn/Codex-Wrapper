from pathlib import Path

import pytest

from app import codex


def test_prepare_codex_process_launch_no_isolation(monkeypatch, tmp_path):
    monkeypatch.setattr(
        codex.settings, "codex_isolate_user_workspace", False, raising=False
    )

    cmd, env, cwd = codex._prepare_codex_process_launch(
        ["codex", "exec", "hi"],
        workdir=tmp_path,
        env={"CODEX_HOME": "/home/codex/.codex"},
        user_id="alice",
    )

    assert cmd == ["codex", "exec", "hi"]
    assert env["CODEX_HOME"] == "/home/codex/.codex"
    assert cwd == str(tmp_path)


def test_prepare_codex_process_launch_wraps_with_bwrap(monkeypatch, tmp_path):
    user_root = tmp_path / "alice"
    workdir = user_root / "chat-1"
    isolated_home = user_root / ".codex-runner"
    user_skills_root = tmp_path / "user-skills" / "alice"
    system_skills_root = tmp_path / "system-skills"
    isolated_home.mkdir(parents=True)
    workdir.mkdir(parents=True)
    user_skills_root.mkdir(parents=True)
    system_skills_root.mkdir(parents=True)

    monkeypatch.setattr(
        codex.settings, "codex_isolate_user_workspace", True, raising=False
    )
    monkeypatch.setattr(
        codex.settings, "codex_user_skills_root", str(tmp_path / "user-skills"), raising=False
    )
    monkeypatch.setattr(
        codex.settings, "codex_system_skills_dir", str(system_skills_root), raising=False
    )
    monkeypatch.setattr(codex, "get_user_workspace_root", lambda _user_id: user_root)
    monkeypatch.setattr(
        codex,
        "_prepare_isolated_codex_home",
        lambda _user_id: isolated_home,
    )
    monkeypatch.setattr(
        codex,
        "_existing_system_bind_mounts",
        lambda: [("/usr", "/usr"), ("/etc", "/etc")],
    )
    monkeypatch.setattr(codex.shutil, "which", lambda name: "/usr/bin/bwrap")

    cmd, env, cwd = codex._prepare_codex_process_launch(
        ["codex", "exec", "hi"],
        workdir=workdir,
        env={"CODEX_HOME": "/host/.codex", "HOME": "/host-home"},
        user_id="alice",
    )

    rendered = " ".join(cmd)
    assert cmd[0] == "/usr/bin/bwrap"
    assert "--bind" in cmd
    assert f"{user_root} {user_root}" in rendered
    assert f"{user_skills_root} /home/codex/.agents/skills" in rendered
    assert f"{isolated_home} /home/codex/.codex" in rendered
    assert f"{system_skills_root} /etc/codex/skills" in rendered
    assert f"--chdir {workdir}" in rendered
    assert env["CODEX_HOME"] == "/home/codex/.codex"
    assert env["HOME"] == "/home/codex"
    assert env["TMPDIR"] == "/tmp"
    assert cwd is None


def test_prepare_codex_process_launch_rejects_workdir_escape(monkeypatch, tmp_path):
    alice_root = tmp_path / "alice"
    bob_workdir = tmp_path / "bob" / "chat-2"
    isolated_home = alice_root / ".codex-runner"
    isolated_home.mkdir(parents=True)
    bob_workdir.mkdir(parents=True)

    monkeypatch.setattr(
        codex.settings, "codex_isolate_user_workspace", True, raising=False
    )
    monkeypatch.setattr(
        codex.settings, "codex_user_skills_root", str(tmp_path / "user-skills"), raising=False
    )
    monkeypatch.setattr(codex, "get_user_workspace_root", lambda _user_id: alice_root)
    monkeypatch.setattr(
        codex,
        "_prepare_isolated_codex_home",
        lambda _user_id: isolated_home,
    )
    monkeypatch.setattr(
        codex,
        "_existing_system_bind_mounts",
        lambda: [("/usr", "/usr")],
    )
    monkeypatch.setattr(codex.shutil, "which", lambda name: "/usr/bin/bwrap")

    with pytest.raises(codex.CodexError):
        codex._prepare_codex_process_launch(
            ["codex", "exec", "hi"],
            workdir=bob_workdir,
            env={"CODEX_HOME": "/host/.codex"},
            user_id="alice",
        )


def test_prepare_isolated_codex_home_copies_auth_and_config(monkeypatch, tmp_path):
    source_home = tmp_path / "shared-home"
    source_home.mkdir(parents=True)
    (source_home / "auth.json").write_text('{"token":"x"}', encoding="utf-8")
    (source_home / "config.toml").write_text('model = "gpt-5.1"', encoding="utf-8")
    user_root = tmp_path / "alice"
    user_root.mkdir(parents=True)

    monkeypatch.setattr(codex, "get_user_workspace_root", lambda _user_id: user_root)
    monkeypatch.setattr(
        codex, "_candidate_source_codex_home_dirs", lambda: [source_home]
    )

    isolated_home = codex._prepare_isolated_codex_home("alice")

    assert isolated_home == user_root / ".codex-runner"
    assert (isolated_home / "auth.json").read_text(encoding="utf-8") == '{"token":"x"}'
    assert (isolated_home / "config.toml").read_text(encoding="utf-8") == 'model = "gpt-5.1"'


def test_get_user_skill_root_uses_per_user_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(
        codex.settings, "codex_user_skills_root", str(tmp_path / "user-skills"), raising=False
    )

    skill_root = codex.get_user_skill_root("alice")

    assert skill_root == tmp_path / "user-skills" / "alice"
    assert skill_root.is_dir()


def test_build_cmd_and_env_uses_inner_danger_mode_when_outer_isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(codex.settings, "codex_path", "codex", raising=False)
    monkeypatch.setattr(codex.settings, "sandbox_mode", "workspace-write", raising=False)
    monkeypatch.setattr(codex.settings, "hide_reasoning", False, raising=False)
    monkeypatch.setattr(codex.settings, "approval_policy", "never", raising=False)
    monkeypatch.setattr(codex.settings, "reasoning_effort", "medium", raising=False)
    monkeypatch.setattr(codex, "_resolve_codex_executable", lambda: "codex")
    monkeypatch.setattr(codex, "_resolve_workdir_state", lambda *_args, **_kwargs: (tmp_path, True))

    cmd = codex._build_cmd_and_env(
        "prompt",
        workdir=tmp_path,
        outer_workspace_isolated=True,
    )

    assert 'sandbox_mode="danger-full-access"' in cmd
    assert 'sandbox_mode="workspace-write"' not in cmd
