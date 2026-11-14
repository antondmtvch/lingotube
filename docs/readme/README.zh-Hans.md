# lingotube

![version](https://img.shields.io/badge/version-0.1.0-blue)
![extension release](https://img.shields.io/github/v/release/antondmtvch/lingotube?filter=extension-v*&label=extension)
![python](https://img.shields.io/badge/python-%E2%89%A53.14-3776AB?logo=python&logoColor=white)
![coverage cli](https://img.shields.io/badge/coverage_cli-96%25-brightgreen)
![coverage extension](https://img.shields.io/badge/coverage_extension-99%25-brightgreen)
[![skills.sh](https://skills.sh/b/antondmtvch/lingotube)](https://skills.sh/antondmtvch/lingotube)

[English](/README.md) · [Русский](/docs/readme/README.ru.md) · **简体中文** · [繁體中文](/docs/readme/README.zh-Hant.md) · [हिन्दी](/docs/readme/README.hi.md) · [Español](/docs/readme/README.es.md) · [Français](/docs/readme/README.fr.md) · [العربية](/docs/readme/README.ar.md) · [বাংলা](/docs/readme/README.bn.md) · [Português](/docs/readme/README.pt.md) · [ไทย](/docs/readme/README.th.md) · [日本語](/docs/readme/README.ja.md) · [Tiếng Việt](/docs/readme/README.vi.md) · [Deutsch](/docs/readme/README.de.md)

lingotube 用于获取 YouTube 视频的字幕、文字稿和摘要。项目由三部分组成：命令行工具、面向 AI 代理的 skill，以及在播放器上显示翻译字幕的浏览器扩展（开发中）。
文本来自视频页面上 YouTube 内置的聊天功能（“提问”，Gemini）。
所有请求都以你的 YouTube 账号的名义发出。

> [!WARNING]
> 该工具使用的是 YouTube 聊天的**内部、未公开文档**的请求。YouTube 可能随时更改它而不另行通知，
> 届时工具将无法使用，直到更新为止。YouTube 的服务条款不允许自动化访问：使用本工具的风险由你自行承担。
> 请求会逐个发送，且每次之间有间隔，但无法保证你的账号不会被限制。

> [!NOTE]
> 提问和回答会保留在你账号的聊天记录中。聊天功能在俄罗斯和欧盟大部分地区不可用，
> 部分视频下也没有。

**目录**

- [项目包含什么](#项目包含什么)
- [命令行工具（CLI）](#命令行工具cli)
  - [功能](#功能)
  - [安装](#安装)
  - [快速开始](#快速开始)
  - [命令](#命令)
  - [Cookie 与登录](#cookie-与登录)
  - [翻译模式](#翻译模式)
  - [退出码](#退出码)
- [面向 AI 代理的 skill](#面向-ai-代理的-skill)
- [浏览器扩展](#浏览器扩展)
- [限制](#限制)
- [开发](#开发)

## 项目包含什么

| 组件 | 作用 |
|---|---|
| [命令行工具（CLI）](#命令行工具cli) | `lingotube` 命令：以文件或 JSON 形式获取视频的字幕、文字稿和摘要。 |
| [面向 AI 代理的 skill](#面向-ai-代理的-skill) | 让 AI 代理（Claude Code、Codex、Cursor 等）为视频做摘要、生成文字稿或字幕，并按描述查找某个时刻。它会调用命令行工具。 |
| [浏览器扩展](#浏览器扩展) | 在 YouTube 播放器上显示任意语言的翻译字幕。开发中。 |

## 命令行工具（CLI）

本节的所有内容都与 `lingotube` 命令有关。skill 和扩展在下面各有单独的章节。

### 功能

- **字幕**：支持任意语言，格式为 `srt`、`vtt` 和 `json`。
- **文字稿**：使用原始语言并带时间码。
- **视频摘要**。
- **三种翻译模式**：YouTube 内置聊天、你自己的兼容 OpenAI API 的模型，
  或由 AI 代理自行翻译文字稿。
- **缓存与续传**：长视频分段处理，失败后从中断处继续。
- **机器可读输出**：`--json` 适用于脚本和 AI 代理。

### 安装

需要 [uv](https://docs.astral.sh/uv/)。uv 会自动下载所需的 Python 版本。

```sh
uv tool install --python 3.14 git+https://github.com/antondmtvch/lingotube
```

或者从仓库的本地副本安装：

```sh
uv tool install --python 3.14 .
```

更新与卸载：

```sh
uv tool upgrade lingotube
uv tool uninstall lingotube
```

### 快速开始

1. 登录 YouTube。在 Chrome 或 Edge 中，最简单的方式是：

   ```sh
   lingotube login
   ```

   会打开一个使用独立 lingotube 配置文件的浏览器窗口。登录你的账号后，**请关闭浏览器窗口**：
   命令会等待你关闭窗口。在 Firefox 中，像平常一样登录 YouTube 即可。

2. 检查是否就绪：

   ```sh
   lingotube doctor
   ```

   `doctor` 会检查 cookie 来源、账号登录状态，以及测试视频上聊天功能是否可用。
   它只会打开聊天，不会向其中写入任何内容。

3. 获取字幕：

   ```sh
   lingotube subs https://www.youtube.com/watch?v=XXXXXXXXXXX --lang zh-Hans
   ```

### 命令

| 命令 | 作用 |
|---|---|
| `lingotube subs <链接> --lang zh-Hans` | 创建所选语言的字幕文件。 |
| `lingotube summary <链接> --lang zh-Hans` | 输出所选语言的摘要。 |
| `lingotube transcript <链接>` | 生成原始语言、带时间码的文字稿（默认为 JSON）。 |
| `lingotube build <链接> --lang zh-Hans --from <文件>` | 接收现成的译文，与原文核对后生成字幕。 |
| `lingotube login [--browser chrome\|edge]` | 打开 YouTube 登录窗口并保存 cookie。 |
| `lingotube logout` | 删除登录配置文件和已保存的 cookie。 |
| `lingotube doctor` | 检查就绪状态：cookie、账号登录以及测试视频上的聊天。 |

`<链接>` 可以是任意形式的 YouTube 视频链接，也可以是视频 ID。

主要选项：

- `--lang <代码>` — 结果语言（`ru`、`en`、`es` 等）。不指定时，语言取自设置。
- `--format srt|vtt|json` — 字幕格式，默认为 `srt`。
- `-o <路径>` — 结果写入位置。使用 `-o -` 时输出到标准输出。
- `--offset <秒>` — 整体平移所有字幕；可以使用小数和负数。
- `--cookies-file <路径>` / `--browser <名称>` — cookie 来源。
- `--no-cache` — 不使用缓存。
- `--json` — 输出单个 JSON 文档 `{"ok", "result", "warnings", "error"}`。

以连字符开头的 ID 请放在 `--` 之后：

```sh
lingotube subs --lang zh-Hans -- -n5MqamatXE
```

### Cookie 与登录

工具按以下顺序选用第一个可用的来源：

1. `cookies.txt` 文件：`--cookies-file` 选项、`LINGOTUBE_COOKIES_FILE` 变量或设置中的路径。
2. 明确指定的浏览器：`--browser` 选项或设置中的 `browser`。
3. lingotube 登录配置文件（由 `lingotube login` 创建）。
4. 否则依次尝试 Firefox、Chrome、Edge 和 Brave。

在 Windows 上，Chrome 和 Edge 会保护其 cookie，通常无法直接读取。
对它们请使用 `lingotube login`。导出文件仍可作为备用方式。

> [!CAUTION]
> `cookies.txt` 文件可访问你的账号。请像保管密码一样保管它，不要放入代码仓库或共享文件夹。
> cookie、令牌和授权头绝不会出现在输出、错误信息或 `--json` 中：它们会被显示为 `***`。

如果 cookie 失效（退出码 `4`），请重新运行 `lingotube login`，或导出新的文件。

### 翻译模式

| 模式 | 何时启用 | 由谁翻译 |
|---|---|---|
| **聊天**（默认） | 未做任何配置 | YouTube 聊天直接给出所需语言的文本 |
| **自有模型** | 设置中配置了 `[translator]` 部分 | 你的兼容 OpenAI API 的模型 |
| **代理** | `transcript` → 翻译 → `build` | AI 代理或你本人手动完成；lingotube 只负责核对译文并生成字幕 |

设置位于 `settings.toml`：

- Windows：`%LOCALAPPDATA%\lingotube\settings.toml`
- macOS：`~/Library/Application Support/lingotube/settings.toml`
- Linux：`~/.config/lingotube/settings.toml`

“自有模型”模式示例：

```toml
lang = "zh-Hans"

[translator]
base_url = "https://api.openai.com/v1"   # 或本地模型，例如 http://127.0.0.1:11434/v1
model = "gpt-4o-mini"
api_key_env = "LINGOTUBE_API_KEY"        # 存放密钥的环境变量名
batch_size = 40
```

密钥不会写入设置文件：工具只从环境变量中读取。

“代理”模式：

```sh
lingotube transcript <链接> -o orig.json          # 原文，JSON 格式
# 翻译每条字幕的 text 字段，不要改动 id 和时间，并保存为 zh.json
lingotube build <链接> --lang zh-Hans --from zh.json   # 检查并生成字幕
```

> [!TIP]
> 若要保证直译，请使用“自有模型”或“代理”模式：它们会先获取原文，
> 再按行号核对译文。聊天可能会改写或合并语句。

### 退出码

| 代码 | 含义 |
|---|---|
| `0` | 成功。 |
| `1` | 其他错误。 |
| `2` | 命令选项无效。 |
| `3` | 该视频或账号无法使用聊天。 |
| `4` | 登录问题：找不到 cookie 或已失效，或未设置模型密钥。 |
| `5` | 结果不完整：文件已写入，但文字稿未覆盖到视频结尾。 |
| `6` | 重试次数用尽后出现网络故障。 |
| `7` | 数据未通过校验。 |
| `8` | YouTube 改变了 lingotube 读取的格式。请更新 lingotube：参见「安装」部分。 |
| `130` | 被用户中断（Ctrl+C）。 |

## 面向 AI 代理的 skill

skill 会代替代理运行[命令行工具](#命令行工具cli)，因此请先安装工具，再安装 skill。


仓库中提供了采用开放 Agent Skills 格式的 skill。借助它，AI 代理（Claude Code、Codex、
Cursor、Gemini CLI 等）可以为视频做摘要、生成文字稿和字幕、
按描述查找某个时刻，并协助安装与登录。

```sh
npx skills add antondmtvch/lingotube
```

没有 Node.js 时，请把 `skills/lingotube/` 文件夹复制到你的代理的 skills 文件夹
（Claude Code 为 `~/.claude/skills/`，大多数其他代理为 `~/.agents/skills/`）。

然后把链接发给代理，并说明你的需求：

```text
总结这个视频：https://youtu.be/VIDEO_ID
这个视频里哪里讲到了剪辑？https://youtu.be/VIDEO_ID
为这个视频生成中文字幕：https://youtu.be/VIDEO_ID
```

## 浏览器扩展

一个适用于 Chrome、Edge 和 Firefox 的 Manifest V3 扩展，在 YouTube 播放器上显示翻译字幕。它仍在开发中。

- 播放器中的按钮用于开启字幕；带文字的面板可以拖动。
- 可从 30 种语言中选择，也可以自己输入。
- 时间和原文来自 YouTube 自己的字幕，聊天只负责翻译。
- 它在你已登录 YouTube 的浏览器中运行，因此无需配置 cookie。

它目前不在任何应用商店中。请在[发布页面](https://github.com/antondmtvch/lingotube/releases)下载适用于你的浏览器的文件：

- Chrome：下载 `lingotube-<version>-chromium.zip`，解压到一个你会长期保留的文件夹。打开 `chrome://extensions`，开启“开发者模式”，点击“加载已解压的扩展程序”，然后选择该文件夹。Chrome 在启动时会提醒你有处于开发者模式的扩展。要更新，请替换文件夹中的文件，并点击扩展卡片上的重新加载按钮。
- Edge：使用同一个压缩包。打开 `edge://extensions`，开启“开发人员模式”，点击“加载解压缩的扩展”，然后选择该文件夹。
- Firefox 140 或更高版本：下载 `lingotube-<version>-firefox.xpi`，把文件拖进 Firefox 窗口（或打开 `about:addons`，点击齿轮图标，选择“从文件安装附加组件…”），然后确认安装。

尚未在 Brave、Opera 和 Vivaldi 中测试过。

## 限制

这些限制适用于全部三个组件，因为它们都依赖 YouTube 的聊天功能。


- 聊天功能仅适用于已登录且年满 13 岁的用户，并非所有国家都可用，
  也并非每个视频下都有。
- 不支持品牌账号：使用的是浏览器中的主账号。
- 一小时的视频需要几分钟：请求是逐个发送的。
- 字幕时间由聊天给出。长视频中个别字幕可能偏移几秒；
  若偏移固定，可用 `--offset` 选项修正。
- 长视频的文本不保证逐字准确：聊天有时会给出意思相近的文本，而工具无法察觉。
  用于重要场合时，请对照录像核对结果。
- 不支持代理。

## 开发

依赖和环境由 uv 管理：

```sh
uv sync
uv run pytest
uv run ruff check
```

测试覆盖率（上方徽章中的数值由这些命令测得，需手动更新）：

```sh
uv run --with pytest-cov pytest --cov=lingotube
cd extension && node --test --experimental-test-coverage --test-coverage-exclude='tests/**' tests/
```

项目结构：

- `src/lingotube/` — 核心：CLI、授权、聊天、翻译、缓存和结果写入。
- `skills/lingotube/` — 面向 AI 代理的 skill。
- `extension/` — 浏览器扩展。
- `tests/` — Python 测试。
- `docs/readme/` — 本 README 的翻译。
