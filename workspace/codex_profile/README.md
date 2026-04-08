# Codex プロファイル上書きディレクトリ

- `codex_agents.sample.md` と `codex_config.sample.toml` はサンプルです。
- `system_prompt.sample.md` はラッパーが各リクエストに自動注入するシステムプロンプトのサンプルです。
- 実際に適用したい内容は `codex_agents.md`、`codex_config.toml` としてこのディレクトリに配置してください。
- システムプロンプトを追加したい場合は `system_prompt.sample.md` を `system_prompt.md` にコピーして編集してください。
- サーバー起動時にこれらのファイルが存在する場合のみ、Codex のホームディレクトリにある `AGENTS.md` と `config.toml` を上書きします。
- `system_prompt.md` は Codex ホームへコピーされず、ラッパー側が毎回のリクエストで読み込んで先頭に注入します。
- 片方だけ配置した場合は、存在するファイルのみがコピーされます。
- 互換性のために旧名称 (`agent.md` / `config.toml`) も読み込みますが、起動時に警告が表示されるので新名称への移行を推奨します。

カスタムファイルをコミットしないために `.gitignore` で `codex_agents.md` / `codex_config.toml` / `system_prompt.md`（および旧名称）を除外しています。
