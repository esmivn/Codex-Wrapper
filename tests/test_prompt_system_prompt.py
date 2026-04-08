from pathlib import Path

from app import prompt


def test_load_wrapper_system_prompt_parts_include_builtin_rules(monkeypatch, tmp_path):
    monkeypatch.setattr(prompt.settings, "codex_profile_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(prompt.settings, "codex_system_prompt_file", None, raising=False)
    monkeypatch.setattr(prompt.settings, "codex_system_prompt", None, raising=False)

    parts = prompt.load_wrapper_system_prompt_parts()

    assert parts
    assert "current working directory" in parts[0]
    assert "public URL" in parts[0]
    assert "HTML fragment" in parts[0]
    assert "Do not wrap the response in Markdown fences" in parts[0]


def test_load_wrapper_system_prompt_parts_append_profile_and_env(monkeypatch, tmp_path):
    prompt_file = tmp_path / "system_prompt.md"
    prompt_file.write_text("Profile prompt rule.", encoding="utf-8")

    monkeypatch.setattr(prompt.settings, "codex_profile_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(prompt.settings, "codex_system_prompt_file", None, raising=False)
    monkeypatch.setattr(prompt.settings, "codex_system_prompt", "Env prompt rule.", raising=False)

    parts = prompt.load_wrapper_system_prompt_parts()

    assert parts[-2] == "Profile prompt rule."
    assert parts[-1] == "Env prompt rule."


def test_build_prompt_and_images_prefixes_injected_system_parts():
    prompt_text, images = prompt.build_prompt_and_images(
        [{"role": "user", "content": "hello"}],
        injected_system_parts=["Rule A", "Rule B"],
    )

    assert prompt_text.startswith("Rule A\nRule B\n\nUser: hello")
    assert images == []
