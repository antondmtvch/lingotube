# lingotube

![version](https://img.shields.io/badge/version-0.1.0-blue)
![extension release](https://img.shields.io/github/v/release/antondmtvch/lingotube?filter=extension-v*&label=extension)
![python](https://img.shields.io/badge/python-%E2%89%A53.14-3776AB?logo=python&logoColor=white)
![coverage cli](https://img.shields.io/badge/coverage_cli-96%25-brightgreen)
![coverage extension](https://img.shields.io/badge/coverage_extension-99%25-brightgreen)
[![skills.sh](https://skills.sh/b/antondmtvch/lingotube)](https://skills.sh/antondmtvch/lingotube)

[English](/README.md) · [Русский](/docs/readme/README.ru.md) · [简体中文](/docs/readme/README.zh-Hans.md) · **繁體中文** · [हिन्दी](/docs/readme/README.hi.md) · [Español](/docs/readme/README.es.md) · [Français](/docs/readme/README.fr.md) · [العربية](/docs/readme/README.ar.md) · [বাংলা](/docs/readme/README.bn.md) · [Português](/docs/readme/README.pt.md) · [ไทย](/docs/readme/README.th.md) · [日本語](/docs/readme/README.ja.md) · [Tiếng Việt](/docs/readme/README.vi.md) · [Deutsch](/docs/readme/README.de.md)

lingotube 用於取得 YouTube 影片的字幕、逐字稿和摘要。專案由三部分組成：命令列工具、面向 AI 代理的 skill，以及在播放器上顯示翻譯字幕的瀏覽器擴充功能（開發中）。
文字來自影片頁面上 YouTube 內建的聊天功能（「提問」，Gemini）。
所有請求都以你的 YouTube 帳號名義發出。

> [!WARNING]
> 此工具使用的是 YouTube 聊天的**內部、未公開文件**的請求。YouTube 可能隨時更改而不另行通知，
> 屆時工具將無法使用，直到更新為止。YouTube 的服務條款不允許自動化存取：使用本工具的風險由你自行承擔。
> 請求會逐一送出，且每次之間有間隔，但無法保證你的帳號不會受到限制。
> 支援服務盡力而為，利用業餘時間進行，不設截止期限。

> [!NOTE]
> 提問與回答會保留在你帳號的聊天紀錄中。聊天功能在俄羅斯和歐盟大部分地區無法使用，
> 部分影片下也沒有。

**目錄**

- [專案包含什麼](#專案包含什麼)
- [命令列工具（CLI）](#命令列工具cli)
  - [功能](#功能)
  - [安裝](#安裝)
  - [快速開始](#快速開始)
  - [指令](#指令)
  - [Cookie 與登入](#cookie-與登入)
  - [翻譯模式](#翻譯模式)
  - [結束碼](#結束碼)
- [面向 AI 代理的 skill](#面向-ai-代理的-skill)
- [瀏覽器擴充功能](#瀏覽器擴充功能)
- [限制](#限制)
- [開發](#開發)

## 專案包含什麼

| 元件 | 作用 |
|---|---|
| [命令列工具（CLI）](#命令列工具cli) | `lingotube` 指令：以檔案或 JSON 形式取得影片的字幕、逐字稿和摘要。 |
| [面向 AI 代理的 skill](#面向-ai-代理的-skill) | 讓 AI 代理（Claude Code、Codex、Cursor 等）為影片做摘要、產生逐字稿或字幕，並依描述尋找某個時刻。它會呼叫命令列工具。 |
| [瀏覽器擴充功能](#瀏覽器擴充功能) | 在 YouTube 播放器上顯示任意語言的翻譯字幕。開發中。 |

## 命令列工具（CLI）

本節的所有內容都與 `lingotube` 指令有關。skill 和擴充功能在下面各有單獨的章節。

### 功能

- **字幕**：支援任何語言，格式為 `srt`、`vtt` 和 `json`。
- **逐字稿**：使用原始語言並附時間碼。
- **影片摘要**。
- **三種翻譯模式**：YouTube 內建聊天、你自己的相容 OpenAI API 的模型，
  或由 AI 代理自行翻譯逐字稿。
- **快取與續傳**：長影片分段處理，失敗後從中斷處繼續。
- **機器可讀輸出**：`--json` 適用於腳本和 AI 代理。

### 安裝

需要 [uv](https://docs.astral.sh/uv/)。uv 會自動下載所需的 Python 版本。

```sh
uv tool install --python 3.14 git+https://github.com/antondmtvch/lingotube
```

或從儲存庫的本機副本安裝：

```sh
uv tool install --python 3.14 .
```

更新與解除安裝：

```sh
uv tool upgrade lingotube
uv tool uninstall lingotube
```

### 快速開始

1. 登入 YouTube。在 Chrome 或 Edge 中，最簡單的方式是：

   ```sh
   lingotube login
   ```

   會開啟一個使用獨立 lingotube 設定檔的瀏覽器視窗。登入你的帳號後，**請關閉瀏覽器視窗**：
   指令會等待你關閉視窗。在 Firefox 中，像平常一樣登入 YouTube 即可。

2. 檢查是否就緒：

   ```sh
   lingotube doctor
   ```

   `doctor` 會檢查 cookie 來源、帳號登入狀態，以及測試影片上聊天功能是否可用。
   它只會開啟聊天，不會向其中寫入任何內容。

3. 取得字幕：

   ```sh
   lingotube subs https://www.youtube.com/watch?v=XXXXXXXXXXX --lang zh-Hant
   ```

### 指令

| 指令 | 作用 |
|---|---|
| `lingotube subs <連結> --lang zh-Hant` | 建立所選語言的字幕檔。 |
| `lingotube summary <連結> --lang zh-Hant` | 輸出所選語言的摘要。 |
| `lingotube transcript <連結>` | 產生原始語言、附時間碼的逐字稿（預設為 JSON）。 |
| `lingotube build <連結> --lang zh-Hant --from <檔案>` | 接收現成的譯文，與原文核對後產生字幕。 |
| `lingotube login [--browser chrome\|edge]` | 開啟 YouTube 登入視窗並儲存 cookie。 |
| `lingotube logout` | 刪除登入設定檔和已儲存的 cookie。 |
| `lingotube doctor` | 檢查就緒狀態：cookie、帳號登入以及測試影片上的聊天。 |

`<連結>` 可以是任何形式的 YouTube 影片連結，也可以是影片 ID。

主要選項：

- `--lang <代碼>` — 結果語言（`ru`、`en`、`es` 等）。未指定時，語言取自設定。
- `--format srt|vtt|json` — 字幕格式，預設為 `srt`。
- `-o <路徑>` — 結果寫入位置。使用 `-o -` 時輸出到標準輸出。
- `--offset <秒>` — 整體平移所有字幕；可以使用小數和負數。
- `--cookies-file <路徑>` / `--browser <名稱>` — cookie 來源。
- `--no-cache` — 不使用快取。
- `--json` — 輸出單一 JSON 文件 `{"ok", "result", "warnings", "error"}`。

以連字號開頭的 ID 請放在 `--` 之後：

```sh
lingotube subs --lang zh-Hant -- -n5MqamatXE
```

### Cookie 與登入

工具依以下順序選用第一個可用的來源：

1. `cookies.txt` 檔案：`--cookies-file` 選項、`LINGOTUBE_COOKIES_FILE` 變數或設定中的路徑。
2. 明確指定的瀏覽器：`--browser` 選項或設定中的 `browser`。
3. lingotube 登入設定檔（由 `lingotube login` 建立）。
4. 否則依序嘗試 Firefox、Chrome、Edge 和 Brave。

在 Windows 上，Chrome 和 Edge 會保護其 cookie，通常無法直接讀取。
對它們請使用 `lingotube login`。匯出檔案仍可作為備用方式。

> [!CAUTION]
> `cookies.txt` 檔案可存取你的帳號。請像保管密碼一樣保管它，不要放入程式碼儲存庫或共用資料夾。
> cookie、權杖和授權標頭絕不會出現在輸出、錯誤訊息或 `--json` 中：它們會顯示為 `***`。

如果 cookie 失效（結束碼 `4`），請重新執行 `lingotube login`，或匯出新的檔案。

### 翻譯模式

| 模式 | 何時啟用 | 由誰翻譯 |
|---|---|---|
| **聊天**（預設） | 未做任何設定 | YouTube 聊天直接給出所需語言的文字 |
| **自有模型** | 設定中配置了 `[translator]` 區段 | 你的相容 OpenAI API 的模型 |
| **代理** | `transcript` → 翻譯 → `build` | AI 代理或你本人手動完成；lingotube 只負責核對譯文並產生字幕 |

設定位於 `settings.toml`：

- Windows：`%LOCALAPPDATA%\lingotube\settings.toml`
- macOS：`~/Library/Application Support/lingotube/settings.toml`
- Linux：`~/.config/lingotube/settings.toml`

「自有模型」模式範例：

```toml
lang = "zh-Hant"

[translator]
base_url = "https://api.openai.com/v1"   # 或本機模型，例如 http://127.0.0.1:11434/v1
model = "gpt-4o-mini"
api_key_env = "LINGOTUBE_API_KEY"        # 存放金鑰的環境變數名稱
batch_size = 40
```

金鑰不會寫入設定檔：工具只從環境變數中讀取。

「代理」模式：

```sh
lingotube transcript <連結> -o orig.json          # 原文，JSON 格式
# 翻譯每條字幕的 text 欄位，不要更動 id 和時間，並儲存為 zh.json
lingotube build <連結> --lang zh-Hant --from zh.json   # 檢查並產生字幕
```

> [!TIP]
> 若要確保直譯，請使用「自有模型」或「代理」模式：它們會先取得原文，
> 再依行號核對譯文。聊天可能會改寫或合併語句。

### 結束碼

| 代碼 | 含義 |
|---|---|
| `0` | 成功。 |
| `1` | 其他錯誤。 |
| `2` | 指令選項無效。 |
| `3` | 此影片或帳號無法使用聊天。 |
| `4` | 登入問題：找不到 cookie 或已失效，或未設定模型金鑰。 |
| `5` | 結果不完整：檔案已寫入，但逐字稿未涵蓋到影片結尾。 |
| `6` | 重試次數用盡後發生網路故障。 |
| `7` | 資料未通過驗證。 |
| `8` | YouTube 改變了 lingotube 讀取的格式。請更新 lingotube：參見「安裝」部分。 |
| `130` | 被使用者中斷（Ctrl+C）。 |

## 面向 AI 代理的 skill

skill 會代替代理執行[命令列工具](#命令列工具cli)，因此請先安裝工具，再安裝 skill。


儲存庫中提供了採用開放 Agent Skills 格式的 skill。藉助它，AI 代理（Claude Code、Codex、
Cursor、Gemini CLI 等）可以為影片做摘要、產生逐字稿和字幕、
依描述尋找某個時刻，並協助安裝與登入。

```sh
npx skills add antondmtvch/lingotube
```

沒有 Node.js 時，請把 `skills/lingotube/` 資料夾複製到你的代理的 skills 資料夾
（Claude Code 為 `~/.claude/skills/`，大多數其他代理為 `~/.agents/skills/`）。

然後把連結交給代理，並說明你的需求：

```text
總結這部影片：https://youtu.be/VIDEO_ID
這部影片哪裡提到了剪輯？https://youtu.be/VIDEO_ID
為這部影片產生繁體中文字幕：https://youtu.be/VIDEO_ID
```

## 瀏覽器擴充功能

一個適用於 Chrome、Edge 和 Firefox 的 Manifest V3 擴充功能，在 YouTube 播放器上顯示翻譯字幕。它仍在開發中。

- 播放器中的按鈕用於開啟字幕；帶文字的面板可以拖曳。
- 可從 30 種語言中選擇，也可以自行輸入。
- 時間和原文來自 YouTube 自己的字幕，聊天只負責翻譯。
- 它在你已登入 YouTube 的瀏覽器中運作，因此不需要設定 cookie。

它目前不在任何商店中。請在[發布頁面](https://github.com/antondmtvch/lingotube/releases)下載適用於你的瀏覽器的檔案：

- Chrome：下載 `lingotube-<version>-chromium.zip`，解壓縮到一個你會長期保留的資料夾。開啟 `chrome://extensions`，啟用「開發人員模式」，點擊「載入未封裝項目」，然後選擇該資料夾。Chrome 在啟動時會提醒你有處於開發人員模式的擴充功能。要更新，請取代資料夾中的檔案，並點擊擴充功能卡片上的重新載入按鈕。
- Edge：使用同一個壓縮檔。開啟 `edge://extensions`，啟用「開發人員模式」，點擊「載入解壓縮」，然後選擇該資料夾。
- Firefox 140 或更新版本：下載 `lingotube-<version>-firefox.xpi`，把檔案拖進 Firefox 視窗（或開啟 `about:addons`，點擊齒輪圖示，選擇「從檔案安裝附加元件…」），然後確認安裝。

尚未在 Brave、Opera 和 Vivaldi 中測試過。

## 限制

這些限制適用於全部三個元件，因為它們都依賴 YouTube 的聊天功能。


- 聊天功能僅適用於已登入且年滿 13 歲的使用者，並非所有國家都可用，
  也並非每部影片下都有。
- 不支援品牌帳號：使用的是瀏覽器中的主要帳號。
- 一小時的影片需要幾分鐘：請求是逐一送出的。
- 字幕時間由聊天給出。長影片中個別字幕可能偏移幾秒；
  若偏移固定，可用 `--offset` 選項修正。
- 長影片的文字不保證逐字準確：聊天有時會給出意思相近的文字，而工具無法察覺。
  用於重要場合時，請對照錄影核對結果。
- 不支援代理伺服器（proxy）。

## 開發

相依套件和環境由 uv 管理：

```sh
uv sync
uv run pytest
uv run ruff check
```

測試覆蓋率（上方徽章中的數值由這些指令測得，需手動更新）：

```sh
uv run --with pytest-cov pytest --cov=lingotube
cd extension && node --test --experimental-test-coverage --test-coverage-exclude='tests/**' tests/
```

專案結構：

- `src/lingotube/` — 核心：CLI、授權、聊天、翻譯、快取和結果寫入。
- `skills/lingotube/` — 面向 AI 代理的 skill。
- `extension/` — 瀏覽器擴充功能。
- `tests/` — Python 測試。
- `docs/readme/` — 本 README 的翻譯。
