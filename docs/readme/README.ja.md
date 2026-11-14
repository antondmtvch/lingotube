# lingotube

![version](https://img.shields.io/badge/version-0.1.0-blue)
![extension release](https://img.shields.io/github/v/release/antondmtvch/lingotube?filter=extension-v*&label=extension)
![python](https://img.shields.io/badge/python-%E2%89%A53.14-3776AB?logo=python&logoColor=white)
![coverage cli](https://img.shields.io/badge/coverage_cli-96%25-brightgreen)
![coverage extension](https://img.shields.io/badge/coverage_extension-99%25-brightgreen)
[![skills.sh](https://skills.sh/b/antondmtvch/lingotube)](https://skills.sh/antondmtvch/lingotube)

[English](/README.md) · [Русский](/docs/readme/README.ru.md) · [简体中文](/docs/readme/README.zh-Hans.md) · [繁體中文](/docs/readme/README.zh-Hant.md) · [हिन्दी](/docs/readme/README.hi.md) · [Español](/docs/readme/README.es.md) · [Français](/docs/readme/README.fr.md) · [العربية](/docs/readme/README.ar.md) · [বাংলা](/docs/readme/README.bn.md) · [Português](/docs/readme/README.pt.md) · [ไทย](/docs/readme/README.th.md) · **日本語** · [Tiếng Việt](/docs/readme/README.vi.md) · [Deutsch](/docs/readme/README.de.md)

lingotube は、YouTube 動画の字幕、文字起こし、要約を取得します。プロジェクトは 3 つの部分で構成されています。コマンドラインツール、AI エージェント向けの skill、そしてプレーヤー上に翻訳字幕を表示するブラウザ拡張機能（開発中）です。
テキストは、動画ページにある YouTube 組み込みのチャット（「質問する」、Gemini）から取得します。
すべてのリクエストは、あなたの YouTube アカウントとして送信されます。

> [!WARNING]
> このツールは、YouTube チャットの**内部の、ドキュメント化されていない**リクエストを使用します。
> YouTube は予告なくいつでもこれを変更する可能性があり、その場合はアップデートされるまでツールが動作しなくなります。
> YouTube の利用規約は自動化されたアクセスを認めていません。ご利用は自己責任でお願いします。
> リクエストは間隔を空けて 1 件ずつ送信されますが、アカウントが制限されないという保証はありません。

> [!NOTE]
> 質問と回答は、アカウントのチャット履歴に残ります。チャットはロシアおよび EU のほとんどの国では利用できず、
> 一部の動画にも表示されません。

**目次**

- [含まれるもの](#含まれるもの)
- [コマンドラインツール（CLI）](#コマンドラインツールcli)
  - [機能](#機能)
  - [インストール](#インストール)
  - [クイックスタート](#クイックスタート)
  - [コマンド](#コマンド)
  - [Cookie とサインイン](#cookie-とサインイン)
  - [翻訳モード](#翻訳モード)
  - [終了コード](#終了コード)
- [AI エージェント向け skill](#ai-エージェント向け-skill)
- [ブラウザ拡張機能](#ブラウザ拡張機能)
- [制限事項](#制限事項)
- [開発](#開発)

## 含まれるもの

| コンポーネント | 内容 |
|---|---|
| [コマンドラインツール（CLI）](#コマンドラインツールcli) | `lingotube` コマンド：動画の字幕、文字起こし、要約をファイルまたは JSON として取得します。 |
| [AI エージェント向け skill](#ai-エージェント向け-skill) | AI エージェント（Claude Code、Codex、Cursor など）に、動画の要約、文字起こしや字幕の作成、説明からの場面検索を行わせます。コマンドラインツールを実行します。 |
| [ブラウザ拡張機能](#ブラウザ拡張機能) | YouTube プレーヤー上に、任意の言語の翻訳字幕を表示します。開発中。 |

## コマンドラインツール（CLI）

このセクションの内容はすべて `lingotube` コマンドに関するものです。skill と拡張機能は、下に別のセクションがあります。

### 機能

- **字幕**：任意の言語、`srt`・`vtt`・`json` 形式。
- **文字起こし**：原語で、タイムコード付き。
- 動画の**要約**。
- **3 つの翻訳モード**：YouTube 組み込みチャット、OpenAI 互換 API を持つ独自モデル、
  またはトランスクリプトを自ら翻訳する AI エージェント。
- **キャッシュと再開**：長い動画は分割して処理され、失敗しても中断した箇所から再開します。
- スクリプトや AI エージェント向けの `--json` による**機械可読な出力**。

### インストール

[uv](https://docs.astral.sh/uv/) が必要です。適切な Python のバージョンは uv が自動でダウンロードします。

```sh
uv tool install --python 3.14 git+https://github.com/antondmtvch/lingotube
```

またはリポジトリのローカルコピーから:

```sh
uv tool install --python 3.14 .
```

更新とアンインストール:

```sh
uv tool upgrade lingotube
uv tool uninstall lingotube
```

### クイックスタート

1. YouTube にサインインします。Chrome または Edge では次のコマンドが最も簡単です。

   ```sh
   lingotube login
   ```

   lingotube 専用のプロファイルでブラウザウィンドウが開きます。アカウントにサインインしたら、**ブラウザウィンドウを閉じてください**。
   コマンドはウィンドウが閉じられるまで待機します。Firefox では、いつも通り YouTube にサインインするだけで十分です。

2. 準備ができているか確認します。

   ```sh
   lingotube doctor
   ```

   `doctor` は、Cookie の取得元、アカウントへのサインイン、テスト動画でのチャットの利用可否を確認します。
   チャットを開くだけで、何も書き込みません。

3. 字幕を取得します。

   ```sh
   lingotube subs https://www.youtube.com/watch?v=XXXXXXXXXXX --lang ja
   ```

### コマンド

| コマンド | 内容 |
|---|---|
| `lingotube subs <リンク> --lang ja` | 選択した言語の字幕ファイルを作成します。 |
| `lingotube summary <リンク> --lang ja` | 選択した言語で要約を出力します。 |
| `lingotube transcript <リンク>` | 原語のタイムコード付き文字起こしを作成します（デフォルトは JSON）。 |
| `lingotube build <リンク> --lang ja --from <ファイル>` | 用意された翻訳を受け取り、原文と照合して字幕を作成します。 |
| `lingotube login [--browser chrome\|edge]` | YouTube のサインインウィンドウを開き、Cookie を保存します。 |
| `lingotube logout` | サインイン用プロファイルと保存済みの Cookie を削除します。 |
| `lingotube doctor` | 準備状況を確認します：Cookie、アカウントへのサインイン、テスト動画でのチャット。 |

`<リンク>` には、任意の形式の YouTube 動画リンクまたは動画 ID を指定できます。

主なオプション:

- `--lang <コード>` — 結果の言語（`ru`、`en`、`es` など）。指定しない場合は設定から取得します。
- `--format srt|vtt|json` — 字幕の形式。デフォルトは `srt`。
- `-o <パス>` — 結果の書き込み先。`-o -` を指定すると標準出力に出力します。
- `--offset <秒>` — すべての字幕をずらします。小数や負の数も指定できます。
- `--cookies-file <パス>` / `--browser <名前>` — Cookie の取得元。
- `--no-cache` — キャッシュを使用しません。
- `--json` — 単一の JSON ドキュメント `{"ok", "result", "warnings", "error"}`。

ハイフンで始まる ID は `--` の後ろに指定してください。

```sh
lingotube subs --lang ja -- -n5MqamatXE
```

### Cookie とサインイン

ツールは次の順序で、最初に使用可能な取得元を採用します。

1. `cookies.txt` ファイル：`--cookies-file` オプション、`LINGOTUBE_COOKIES_FILE` 変数、または設定に保存されたパス。
2. 明示的に指定したブラウザ：`--browser` オプション、または設定の `browser`。
3. lingotube のサインイン用プロファイル（`lingotube login` で作成した場合）。
4. それ以外の場合は、Firefox、Chrome、Edge、Brave を順に試します。

Windows の Chrome と Edge は Cookie を保護しており、通常は直接読み取れません。
これらには `lingotube login` を使用してください。ファイルのエクスポートは代替手段として残されています。

> [!CAUTION]
> `cookies.txt` ファイルはアカウントへのアクセスを許可します。パスワードと同じように大切に保管し、
> リポジトリや共有フォルダには置かないでください。Cookie、トークン、認可ヘッダーが、
> 出力、エラーメッセージ、`--json` に表示されることはありません。代わりに `***` が表示されます。

Cookie が機能しなくなった場合（終了コード `4`）は、もう一度 `lingotube login` を実行するか、新しいファイルをエクスポートしてください。

### 翻訳モード

| モード | 有効になる条件 | 翻訳する主体 |
|---|---|---|
| **チャット**（デフォルト） | 何も設定していない | YouTube のチャットが、目的の言語でそのままテキストを返す |
| **独自モデル** | 設定に `[translator]` セクションがある | OpenAI 互換 API を持つあなたのモデル |
| **エージェント** | `transcript` → 翻訳 → `build` | AI エージェント、またはあなたが手作業で。lingotube は翻訳の検証と字幕の作成だけを行います |

設定は `settings.toml` にあります。

- Windows: `%LOCALAPPDATA%\lingotube\settings.toml`
- macOS: `~/Library/Application Support/lingotube/settings.toml`
- Linux: `~/.config/lingotube/settings.toml`

「独自モデル」モードの例:

```toml
lang = "ja"

[translator]
base_url = "https://api.openai.com/v1"   # またはローカルモデル（例: http://127.0.0.1:11434/v1）
model = "gpt-4o-mini"
api_key_env = "LINGOTUBE_API_KEY"        # キーを格納する環境変数の名前
batch_size = 40
```

キーが設定ファイルに書き込まれることはありません。ツールは環境変数からのみキーを読み取ります。

「エージェント」モード:

```sh
lingotube transcript <リンク> -o orig.json          # 原文を JSON で出力
# 各行の text フィールドを翻訳し、id と時刻は変更せず、ja.json として保存
lingotube build <リンク> --lang ja --from ja.json   # 検証と字幕の作成
```

> [!TIP]
> 逐語訳を保ちたい場合は、「独自モデル」または「エージェント」モードを使用してください。
> これらはまず原文を取得し、翻訳を行番号で検証します。チャットは文を言い換えたり、まとめたりすることがあります。

### 終了コード

| コード | 意味 |
|---|---|
| `0` | 成功。 |
| `1` | その他のエラー。 |
| `2` | コマンドのオプションが無効です。 |
| `3` | この動画またはアカウントではチャットを利用できません。 |
| `4` | サインインの問題：Cookie が見つからない、または期限切れ、あるいはモデルのキーが未設定です。 |
| `5` | 不完全な結果：ファイルは書き込まれましたが、文字起こしが動画の最後まで届いていません。 |
| `6` | 再試行を使い切った後のネットワーク障害。 |
| `7` | データが検証に失敗しました。 |
| `130` | ユーザーによって中断されました（Ctrl+C）。 |

## AI エージェント向け skill

skill はエージェントに代わって[コマンドラインツール](#コマンドラインツールcli)を実行するため、先にツールを、次に skill をインストールしてください。


リポジトリには、オープンな Agent Skills 形式の skill が含まれています。これを使うと、AI エージェント（Claude Code、Codex、
Cursor、Gemini CLI など）が動画を要約し、文字起こしと字幕を作成し、
説明から該当の場面を探し、インストールとサインインを手伝います。

```sh
npx skills add antondmtvch/lingotube
```

Node.js がない場合は、`skills/lingotube/` フォルダをエージェントの skills フォルダにコピーしてください
（Claude Code は `~/.claude/skills/`、それ以外の多くは `~/.agents/skills/`）。

次に、エージェントにリンクを渡して、やりたいことを伝えます。

```text
この動画を要約してください: https://youtu.be/VIDEO_ID
この動画で編集について話している場面はどこですか？ https://youtu.be/VIDEO_ID
日本語の字幕を作ってください: https://youtu.be/VIDEO_ID
```

## ブラウザ拡張機能

Chrome、Edge、Firefox 向けの Manifest V3 拡張機能で、YouTube プレーヤー上に翻訳字幕を表示します。現在開発中です。

- プレーヤーのボタンで字幕をオンにします。テキストのパネルはドラッグできます。
- 30 の言語から選ぶか、自分で入力します。
- タイミングと原文は YouTube 自身の字幕から取得し、チャットは翻訳だけを行います。
- すでに YouTube にサインインしているブラウザで動作するため、Cookie の設定は不要です。

ストアにはまだ公開されていません。お使いのブラウザ用のファイルを[リリースページ](https://github.com/antondmtvch/lingotube/releases)からダウンロードしてください。

- Chrome：`lingotube-<version>-chromium.zip` をダウンロードし、保管しておくフォルダに展開します。`chrome://extensions` を開き、「デベロッパーモード」をオンにして「パッケージ化されていない拡張機能を読み込む」を押し、そのフォルダを選びます。Chrome は起動時に、デベロッパーモードの拡張機能について通知します。更新するには、フォルダ内のファイルを置き換え、拡張機能のカードにある再読み込みボタンを押します。
- Edge：同じアーカイブを使います。`edge://extensions` を開き、「開発者モード」をオンにして「展開して読み込み」を押し、フォルダを選びます。
- Firefox 140 以降：`lingotube-<version>-firefox.xpi` をダウンロードし、ファイルを Firefox のウィンドウにドラッグします（または `about:addons` を開き、歯車アイコンから「ファイルからアドオンをインストール」を選びます）。その後、インストールを確認します。

Brave、Opera、Vivaldi では動作を確認していません。

## 制限事項

これらの制限は、3 つのコンポーネントすべてに当てはまります。いずれも YouTube のチャットに依存しているためです。


- チャットは、サインイン済みの 13 歳以上のユーザーにのみ機能し、すべての国で利用できるわけではなく、
  すべての動画に表示されるわけでもありません。
- ブランドアカウントはサポートされていません。ブラウザのメインアカウントが使用されます。
- 1 時間の動画の処理には数分かかります。リクエストは 1 件ずつ送信されます。
- 行のタイミングはチャットが決定します。長い動画では、一部の行が数秒ずれることがあります。
  一定のずれは `--offset` オプションで補正できます。
- 長い動画のテキストが逐語的であるとは限りません。チャットが意味の近いテキストを返すことがあり、
  ツールはそれを検出できません。重要な用途では、結果を録画と照合してください。
- プロキシはサポートされていません。

## 開発

依存関係と環境は uv で管理します。

```sh
uv sync
uv run pytest
uv run ruff check
```

テストカバレッジ（上のバッジの値はこれらのコマンドで測定したもので、手動で更新します）:

```sh
uv run --with pytest-cov pytest --cov=lingotube
cd extension && node --test --experimental-test-coverage --test-coverage-exclude='tests/**' tests/
```

プロジェクト構成:

- `src/lingotube/` — コア：CLI、認可、チャット、翻訳、キャッシュ、結果の書き込み。
- `skills/lingotube/` — AI エージェント向けの skill。
- `extension/` — ブラウザ拡張機能。
- `tests/` — Python のテスト。
- `docs/readme/` — この README の翻訳。
