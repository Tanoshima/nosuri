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
- Python venv (`ingest/.venv/`) も `uv sync` で自動有効化済み（`cd ingest && which python` で確認可）

### CLI からコンテナに入るショートカット

ホストから `devcontainer exec --workspace-folder . zsh` を毎回打つのが面倒なら、リポジトリ同梱の `bin/devcontainer-exec` が使えます。`.envrc` に `PATH_add bin` が記載済みなので、`direnv allow` 後はプロジェクト配下にいる間だけ `devcontainer-exec` コマンドでコンテナに入れます（コンテナ未起動なら `devcontainer up` も自動で行います）。

```bash
devcontainer-exec          # コンテナに入る（zsh）
devcontainer-exec -c "..."  # 引数は in-container の zsh にそのまま渡る
```

`bin/` 配下のその他のファイルは gitignore 済みなので、個人用のヘルパースクリプトを置く場所としても使えます（共有したいツールは `.gitignore` で個別に un-ignore する）。

---

## 環境を更新する

### Nix inputs（nixpkgs）を新しくする

```bash
nix flake update
```

`flake.lock` が更新されるので **コミット対象**。チームで再現性を保つために必須。

### Python ライブラリを追加・更新

[uv](https://docs.astral.sh/uv/) で管理しています。Python 関連一式は `ingest/` 配下にあります（`pyproject.toml`、`uv.lock`、`ingest/` パッケージ、`scripts/`、`tests/`、`.venv/`）。dev shell に入った時点で `(cd ingest && uv sync)` が自動実行されます。

```bash
cd ingest                    # uv コマンドは ingest/ 配下で実行
uv add requests              # 依存を追加（pyproject.toml と uv.lock を更新）
uv add --dev pytest          # 開発用依存（dependency-groups.dev）に追加
uv remove requests           # 削除
uv sync                      # 手動で同期（通常は自動実行されるので不要）
uv lock --upgrade            # ロックファイルを最新版に更新
uv run python scripts/foo.py # venv 内で実行
uv run pytest                # テスト実行
```

`ingest/pyproject.toml` を直接編集してもよいが、その場合は `uv lock` でロックを再生成すること。`ingest/uv.lock` は **コミット対象**。

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

`ingest/pyproject.toml` の `requires-python` を編集：

```toml
[project]
requires-python = ">=3.15"  # ← ここ
```

uv がこの制約に従って自動で適切な Python を取得します。flake.nix 側に Python は含めておらず、すべて uv 経由なので flake は触らなくて OK。

---

## DB 関連

### 接続

PostgreSQL は cluster 側で `trust` 認証になっているため、ローカル接続にパスワードは不要です。接続情報は以下で固定：

| 項目 | 値 |
|---|---|
| host | `127.0.0.1` （ホスト GUI からは `localhost`） |
| port | `5432` |
| database | `nosuri` |
| user | `postgres` |
| password | （空欄） |

#### A. コンテナ内 CLI（`psql`）

```bash
psql $DATABASE_URL
```

`pgcli` 等を使いたければ `flake.nix` の `packages` に `pkgs.pgcli` を追加するだけで dev shell に入る（「CLI ツールを追加」参照）。

#### B. コンテナ内 GUI（VS Code SQLTools）

devcontainer に `mtxr.sqltools` + `mtxr.sqltools-driver-pg` が同梱済み。サイドバーの SQLTools アイコンから **Add New Connection → PostgreSQL** を選び、上記の接続情報を入力。`Use password` は **Use empty password** を選択。

プロジェクト全体で共有したい場合は `.vscode/settings.json` に `sqltools.connections` を書いてコミットしてもよい。

#### C. ホスト側 GUI クライアント（DBeaver / TablePlus / Postico / pgAdmin など）

`.devcontainer/devcontainer.json` の `forwardPorts: [5432]` でコンテナの 5432 をホストへ転送している。ホスト OS から `localhost:5432` に上記の接続情報で繋げる。

- VS Code から開いている場合は **PORTS** タブに `5432 (PostgreSQL)` が出るのを確認
- `devcontainer` CLI 派の場合は `devcontainer up` 時に同様に転送される（CLI 版は dockershim 経由なのでホスト OS から `localhost:5432` でアクセス可能）
- ポートが既にホストで使われていると衝突する。ホスト側の PostgreSQL を止めるか、devcontainer.json の `forwardPorts` を `"5432:15432"` 形式に書き換えてホスト側だけポートを変える

> セキュリティメモ：cluster は `listen_addresses = '127.0.0.1'` かつ `trust` 認証。devcontainer の port forward は localhost 経由のみで外部公開はされないが、本番／共有環境にこの設定を持ち込まないこと。

### データの永続化とバックアップ

PostgreSQL のデータ実体は `$PWD/.local/state/postgres`（= `PGDATA`）。これはコンテナ内の任意ディレクトリではなく **ホストのワークスペースのバインドマウント上** にあるため、以下の操作ではデータは消えない：

- `pg-down` / `pg-up`
- コンテナ再起動、`Rebuild Container`、`Rebuild Container Without Cache`
- VS Code ウィンドウ／devcontainer のリロード

逆に **消えるパターン**：

- `rm -rf .local/state/postgres`（上記「DB を完全リセット」）
- プロジェクトディレクトリごと削除、別マシンに移動、別ロケーションで clone し直し
- ホストマシン自体の喪失

`.local/` は gitignore 済みなので git では追跡されない。**マシン跨ぎ／チーム共有でデータを残したいなら明示的にダンプを取る**こと。

#### バックアップ戦略（データ種別ごと）

- **Raw テーブル**（オープンデータの 1:1 ミラー）— バックアップ不要。`ingest/scripts/` の ingestion を冪等に保ち、失ったら再取得する方針。
- **Main テーブル**（手作業の編集を含む）— `pg_dump` でファイルに落として保存。
- **マシン跨ぎ用シード** — 小さければ `db/seed.sql` としてコミット、大きければ S3 等の外部ストレージに dump を置く。

#### `pg_dump` / `pg_restore`

```bash
# バックアップ（カスタム形式：高速、選択リストア可、要 pg_restore）
mkdir -p backups
pg_dump -Fc $DATABASE_URL -f backups/nosuri_$(date +%Y%m%d_%H%M%S).dump

# プレーン SQL（人間可読、psql で適用）
pg_dump $DATABASE_URL > backups/nosuri_$(date +%Y%m%d).sql

# 復元（カスタム形式から既存 DB へ）
pg_restore -d $DATABASE_URL --clean --if-exists backups/nosuri_xxx.dump

# 復元（プレーン SQL）
psql $DATABASE_URL -f backups/nosuri_xxx.sql
```

`backups/` を作る場合は `.gitignore` に追加すること（ダンプは大きくなりがち、かつ機密が混じる可能性がある）。

### スキーマ変更

`db/init.sql` が唯一のエントリポイントで、拡張の有効化と各テーブルの DDL (`db/raw_jps_shiseki.sql`, `db/raw_jps_item_api.sql`) の `\ir` 取り込みを行う。全文が `CREATE ... IF NOT EXISTS` なので冪等で、`pg-up` は **毎回** これを適用する。手動適用も同じ：

```bash
psql $DATABASE_URL -f db/init.sql
```

**テーブルを新規追加するとき**：`db/` に DDL ファイルを追加し、`db/init.sql` に `\ir` の行を足す。それだけで `pg-up` に乗る。

**既存テーブルの形を変えるとき**（カラム型・主キー・索引）：`IF NOT EXISTS` は既存テーブルを変更しないので、DDL ファイルを直すだけでは反映されない。`db/migrations/000N_<説明>.sql` を追加し、手で当てる：

```bash
psql $DATABASE_URL -f db/migrations/0001_reshape_raw_jps.sql
```

DDL ファイル（新規 DB 用の正解）とマイグレーション（既存 DB を追いつかせる差分）の両方を必ず更新すること。既存データを捨ててよいなら DB リセットでも良い：

```bash
pg-down
rm -rf .local/state/postgres
pg-up
```

---

## コミット対象の整理

| ファイル | コミット |
|---|---|
| `flake.nix` | ✅ する |
| `flake.lock` | ✅ する（再現性のため） |
| `.envrc` | ✅ する |
| `ingest/pyproject.toml`, `ingest/uv.lock` | ✅ する |
| `db/*.sql` | ✅ する |
| `.devcontainer/**` | ✅ する |
| `.direnv/`, `.local/`, `ingest/.venv/` | ❌ しない（gitignore 済） |
| `.claude/settings.local.json` | ❌ しない（gitignore 済） |
| `bin/devcontainer-exec` | ✅ する（共有ツール） |
| `bin/` のその他 | ❌ しない（個人用ヘルパー、gitignore 済） |
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
