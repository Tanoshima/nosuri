# CONTRIBUTING

このプロジェクトは devcontainer + Nix flake (`nix-direnv`) でローカル環境を完全に再現できる構成になっています。本書はその起動・更新・拡張方法をまとめたものです。

---

## 前提

ホスト側に必要なもの：

- Docker（または互換ランタイム）
- VS Code + Dev Containers 拡張、もしくは [`devcontainer` CLI](https://github.com/devcontainers/cli)
- ホストの `~/.claude` ディレクトリ（Claude Code を使う場合。コンテナにバインドマウントされる）

## 初回セットアップ

1. リポジトリを clone
2. VS Code で開く → 右下のポップアップから **Reopen in Container**
   （CLI 派なら `devcontainer up --workspace-folder .`）
3. 初回はイメージ pull と Nix 依存ダウンロードで **10〜20 分**かかる（postgres, postgis, claude-code, uv などをビルド）
4. ビルド完了後、コンテナ内ターミナルで動作確認：
   ```bash
   pg-up                                       # 初回は initdb から DB 作成まで一気に走る
   psql $DATABASE_URL -c 'select postgis_version();'
   ```

direnv によって `cd` するだけで flake の dev shell が有効化されるため、特別な activate コマンドは不要です。`direnv: error .envrc is blocked` が出た場合は `direnv allow` を実行（postCreate.sh で自動許可していますが、flake.nix を編集すると再許可が必要になることがあります）。

## 日々の作業フロー

- コンテナ起動時に `nohup nix develop -c pg-up &` がバックグラウンドで走り PostgreSQL が起動（ログは `/tmp/pg.log`）
- ターミナルを開けば direnv 経由で `DATABASE_URL` などの環境変数が自動でセット済み
- Python venv (`.venv/`) も `uv sync` で自動有効化済み（`which python` で確認可）

### CLI からコンテナに入るショートカット（任意）

ホストから `devcontainer exec --workspace-folder . zsh` を毎回打つのが面倒なら、プロジェクト直下に `bin/in` を置いて direnv で PATH に追加できます。

`bin/in`（実行権限を付与）:

```bash
#!/usr/bin/env bash
exec devcontainer exec --workspace-folder "$(git rev-parse --show-toplevel)" zsh "$@"
```

`.envrc` には既に `PATH_add bin` が記載済み。`direnv allow` で承認後、プロジェクト配下にいる間だけ `in` というコマンドでコンテナに入れます。`bin/` は gitignore 済みなので、コマンド名やシェル（`bash` 等）は好みで変更可。

---

## 環境を更新する

### Nix inputs（nixpkgs）を新しくする

```bash
nix flake update
```

`flake.lock` が更新されるので **コミット対象**。チームで再現性を保つために必須。

### Python ライブラリを追加・更新

[uv](https://docs.astral.sh/uv/) で管理しています。dev shell に入った時点で `uv sync` が自動実行され、venv は `.venv/` に作られます。

```bash
uv add requests              # 依存を追加（pyproject.toml と uv.lock を更新）
uv add --dev pytest          # 開発用依存（dependency-groups.dev）に追加
uv remove requests           # 削除
uv sync                      # 手動で同期（通常は自動実行されるので不要）
uv lock --upgrade            # ロックファイルを最新版に更新
uv run python scripts/foo.py # venv 内で実行
```

`pyproject.toml` を直接編集してもよいが、その場合は `uv lock` でロックを再生成すること。`uv.lock` は **コミット対象**。

### CLI ツールを追加（Nix 経由）

1. パッケージを検索：
   - https://search.nixos.org/packages
   - もしくは `nix search nixpkgs <名前>`
2. `flake.nix` の `mkShell` の `packages = [ ... ]` に `pkgs.<名前>` を追加
3. 例：
   ```nix
   packages = [
     pkgs.git
     pkgs.curl
     pkgs.claude-code
     pkgs.uv
     postgres
     pg-up
     pg-down
     pkgs.jq        # ← 追加
     pkgs.ripgrep   # ← 追加
   ];
   ```
4. dev shell を再入室すると反映される（direnv が自動再ビルド）

> unfree ライセンスのパッケージ（claude-code 等）は flake.nix 側で `config.allowUnfree = true` を設定済み。

### PostgreSQL の extension を追加

`flake.nix` の `postgres` 定義を編集：

```nix
postgres = pkgs.postgresql_16.withPackages (p: [
  p.postgis
  p.pg_cron     # ← 追加例
]);
```

**既存の cluster には自動適用されない**ので、追加後にいずれか：

- 既存 DB に手動で `CREATE EXTENSION pg_cron;` 実行
- もしくは cluster ごと作り直す（後述「DB を完全リセット」）

### 別のサービスを追加（Redis、Elasticsearch、MinIO 等）

flake には devenv のような宣言的なサービス管理機構はないため、PostgreSQL と同じパターンで進めます：

1. `flake.nix` にパッケージを追加（例：`pkgs.redis`）
2. 対応する `*-up` / `*-down` スクリプトを `writeShellScriptBin` で定義
3. 必要なら `.devcontainer/devcontainer.json` の `postStartCommand` に並列起動を追加

複数サービスが増えてきたら `juspay/services-flake` 等の宣言的サービス管理 flake への移行を検討。

### Python のバージョンを上げる

`pyproject.toml` の `requires-python` を編集：

```toml
[project]
requires-python = ">=3.15"  # ← ここ
```

uv がこの制約に従って自動で適切な Python を取得します。flake.nix 側に Python は含めておらず、すべて uv 経由なので flake は触らなくて OK。

---

## DB 関連

### 接続

```bash
psql $DATABASE_URL
```

VS Code を使う場合は SQLTools 拡張（devcontainer に同梱）からも接続可。

### スキーマ変更（`db/init.sql` 編集後）

`db/init.sql` は `pg-up` の **初回 DB 作成時の一度しか実行されない**。既存 DB への適用方法は2つ：

**A. 手動で実行（既存データを残す）**
```bash
psql $DATABASE_URL -f db/init.sql
```

**B. DB を完全リセット（既存データを破棄）**
```bash
pg-down
rm -rf .local/state/postgres
pg-up
```

### 開発中の任意 SQL ファイル管理

スキーマ変更が増えてきたら `db/migrations/` のような構成への移行を検討（今は単一の `init.sql` のみ）。

---

## コミット対象の整理

| ファイル | コミット |
|---|---|
| `flake.nix` | ✅ する |
| `flake.lock` | ✅ する（再現性のため） |
| `.envrc` | ✅ する |
| `pyproject.toml`, `uv.lock` | ✅ する |
| `db/*.sql` | ✅ する |
| `.devcontainer/**` | ✅ する |
| `.direnv/`, `.local/`, `.venv/` | ❌ しない（gitignore 済） |
| `.claude/settings.local.json` | ❌ しない（gitignore 済） |
| `bin/` | ❌ しない（個人用ヘルパー、gitignore 済） |
| `.claude/skills/` | プロジェクト共有用なら ✅ |

---

## トラブルシューティング

### コンテナ起動後、PostgreSQL に接続できない

```bash
tail -50 /tmp/pg.log
```

`pg-up` のログでエラー原因を確認。ポート競合やデータ破損の場合は cluster リセット（上記「B. DB を完全リセット」）。

### `direnv: error .envrc is blocked`

```bash
direnv allow
```

### Nix キャッシュが古い／壊れている疑い

```bash
nix store gc           # 不要なエントリを削除
nix flake update       # 入力を更新し直す
```

### flake が "not tracked by Git" と言われる

flake.nix が新規ファイルで未 stage の場合に出ます。`git add flake.nix` で解決（commit までは不要、stage されていれば Nix は読み込む）。

### コンテナを完全にクリーンアップして作り直す

VS Code: コマンドパレット → **Dev Containers: Rebuild Container Without Cache**
CLI: `devcontainer up --workspace-folder . --remove-existing-container`
