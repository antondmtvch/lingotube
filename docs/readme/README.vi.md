# lingotube

![version](https://img.shields.io/badge/version-0.1.0-blue)
![extension release](https://img.shields.io/github/v/release/antondmtvch/lingotube?filter=extension-v*&label=extension)
![python](https://img.shields.io/badge/python-%E2%89%A53.14-3776AB?logo=python&logoColor=white)
![coverage cli](https://img.shields.io/badge/coverage_cli-96%25-brightgreen)
![coverage extension](https://img.shields.io/badge/coverage_extension-99%25-brightgreen)
[![skills.sh](https://skills.sh/b/antondmtvch/lingotube)](https://skills.sh/antondmtvch/lingotube)

[English](/README.md) · [Русский](/docs/readme/README.ru.md) · [简体中文](/docs/readme/README.zh-Hans.md) · [繁體中文](/docs/readme/README.zh-Hant.md) · [हिन्दी](/docs/readme/README.hi.md) · [Español](/docs/readme/README.es.md) · [Français](/docs/readme/README.fr.md) · [العربية](/docs/readme/README.ar.md) · [বাংলা](/docs/readme/README.bn.md) · [Português](/docs/readme/README.pt.md) · [ไทย](/docs/readme/README.th.md) · [日本語](/docs/readme/README.ja.md) · **Tiếng Việt** · [Deutsch](/docs/readme/README.de.md)

lingotube lấy phụ đề, bản chép lời và bản tóm tắt của video YouTube. Dự án gồm ba phần: công cụ dòng lệnh, skill cho tác tử AI và tiện ích mở rộng trình duyệt (đang phát triển) hiển thị phụ đề đã dịch phía trên trình phát.
Văn bản được lấy từ khung chat tích hợp sẵn của YouTube («Hỏi», Gemini) trên trang video.
Mọi yêu cầu đều được gửi dưới danh nghĩa tài khoản YouTube của bạn.

> [!WARNING]
> Công cụ sử dụng một yêu cầu chat của YouTube **nội bộ, không có tài liệu**. YouTube có thể thay đổi
> nó bất cứ lúc nào mà không báo trước, và khi đó công cụ sẽ ngừng hoạt động cho đến khi được cập nhật.
> Điều khoản dịch vụ của YouTube không cho phép truy cập tự động: bạn tự chịu rủi ro khi sử dụng công cụ.
> Các yêu cầu được gửi lần lượt, có quãng nghỉ giữa các lần, nhưng không có gì đảm bảo
> tài khoản của bạn sẽ không bị hạn chế.

> [!NOTE]
> Câu hỏi và câu trả lời vẫn nằm trong lịch sử chat của tài khoản bạn. Chat không khả dụng ở Nga
> và phần lớn các nước EU, cũng như dưới một số video.

**Mục lục**

- [Dự án gồm những gì](#dự-án-gồm-những-gì)
- [Công cụ dòng lệnh (CLI)](#công-cụ-dòng-lệnh-cli)
  - [Tính năng](#tính-năng)
  - [Cài đặt](#cài-đặt)
  - [Bắt đầu nhanh](#bắt-đầu-nhanh)
  - [Lệnh](#lệnh)
  - [Cookie và đăng nhập](#cookie-và-đăng-nhập)
  - [Các chế độ dịch](#các-chế-độ-dịch)
  - [Mã thoát](#mã-thoát)
- [Skill cho tác tử AI](#skill-cho-tác-tử-ai)
- [Tiện ích mở rộng trình duyệt](#tiện-ích-mở-rộng-trình-duyệt)
- [Hạn chế](#hạn-chế)
- [Phát triển](#phát-triển)

## Dự án gồm những gì

| Thành phần | Chức năng |
|---|---|
| [Công cụ dòng lệnh (CLI)](#công-cụ-dòng-lệnh-cli) | Lệnh `lingotube`: lấy phụ đề, bản chép lời và bản tóm tắt của video dưới dạng tệp hoặc JSON. |
| [Skill cho tác tử AI](#skill-cho-tác-tử-ai) | Cho phép tác tử AI (Claude Code, Codex, Cursor và các tác tử khác) tóm tắt video, tạo bản chép lời hoặc phụ đề và tìm một thời điểm theo mô tả. Nó chạy công cụ dòng lệnh. |
| [Tiện ích mở rộng trình duyệt](#tiện-ích-mở-rộng-trình-duyệt) | Phụ đề đã dịch phía trên trình phát YouTube, bằng mọi ngôn ngữ. Đang phát triển. |

## Công cụ dòng lệnh (CLI)

Mọi nội dung trong phần này đều nói về lệnh `lingotube`. Skill và tiện ích mở rộng có các phần riêng ở bên dưới.

### Tính năng

- **Phụ đề** bằng mọi ngôn ngữ, ở các định dạng `srt`, `vtt` và `json`.
- **Bản chép lời** bằng ngôn ngữ gốc, kèm mốc thời gian.
- **Bản tóm tắt** video.
- **Ba chế độ dịch**: chat tích hợp sẵn của YouTube, mô hình riêng của bạn với API tương thích OpenAI,
  hoặc một tác tử AI tự dịch bản chép lời.
- **Bộ nhớ đệm và tiếp tục**: video dài được xử lý theo từng phần, và sau khi lỗi, công việc tiếp tục từ chỗ đã dừng.
- **Đầu ra máy đọc được** với `--json` cho script và tác tử AI.

### Cài đặt

Bạn cần [uv](https://docs.astral.sh/uv/). uv tự tải đúng phiên bản Python.

```sh
uv tool install --python 3.14 git+https://github.com/antondmtvch/lingotube
```

Hoặc từ bản sao cục bộ của kho mã:

```sh
uv tool install --python 3.14 .
```

Cập nhật và gỡ cài đặt:

```sh
uv tool upgrade lingotube
uv tool uninstall lingotube
```

### Bắt đầu nhanh

1. Đăng nhập YouTube. Trên Chrome hoặc Edge, cách dễ nhất là:

   ```sh
   lingotube login
   ```

   Một cửa sổ trình duyệt mở ra với hồ sơ lingotube riêng. Hãy đăng nhập vào tài khoản và **đóng cửa sổ
   trình duyệt**: lệnh sẽ chờ cho đến khi bạn đóng nó. Trên Firefox, chỉ cần đăng nhập YouTube như bình thường.

2. Kiểm tra mọi thứ đã sẵn sàng:

   ```sh
   lingotube doctor
   ```

   `doctor` kiểm tra các nguồn cookie, việc đăng nhập tài khoản và khả năng dùng chat trên một video thử.
   Nó chỉ mở chat và không ghi gì vào đó.

3. Lấy phụ đề:

   ```sh
   lingotube subs https://www.youtube.com/watch?v=XXXXXXXXXXX --lang vi
   ```

### Lệnh

| Lệnh | Chức năng |
|---|---|
| `lingotube subs <liên kết> --lang vi` | Tạo tệp phụ đề bằng ngôn ngữ đã chọn. |
| `lingotube summary <liên kết> --lang vi` | In bản tóm tắt bằng ngôn ngữ đã chọn. |
| `lingotube transcript <liên kết>` | Tạo bản chép lời bằng ngôn ngữ gốc kèm mốc thời gian (mặc định là JSON). |
| `lingotube build <liên kết> --lang vi --from <tệp>` | Nhận bản dịch có sẵn, đối chiếu với bản gốc và dựng phụ đề. |
| `lingotube login [--browser chrome\|edge]` | Mở cửa sổ đăng nhập YouTube và lưu cookie. |
| `lingotube logout` | Xóa hồ sơ đăng nhập và các cookie đã lưu. |
| `lingotube doctor` | Kiểm tra mức sẵn sàng: cookie, đăng nhập tài khoản và chat trên video thử. |

`<liên kết>` là bất kỳ liên kết video YouTube nào hoặc ID video.

Các tùy chọn chính:

- `--lang <mã>` — ngôn ngữ kết quả (`ru`, `en`, `es`, v.v.). Nếu không có, ngôn ngữ lấy từ phần cài đặt.
- `--format srt|vtt|json` — định dạng phụ đề, mặc định là `srt`.
- `-o <đường dẫn>` — nơi ghi kết quả. Với `-o -`, kết quả được xuất ra đầu ra chuẩn.
- `--offset <giây>` — dịch toàn bộ phụ đề; có thể dùng số thập phân và số âm.
- `--cookies-file <đường dẫn>` / `--browser <tên>` — nguồn cookie.
- `--no-cache` — không dùng bộ nhớ đệm.
- `--json` — một tài liệu JSON duy nhất `{"ok", "result", "warnings", "error"}`.

ID bắt đầu bằng dấu gạch nối được truyền sau `--`:

```sh
lingotube subs --lang vi -- -n5MqamatXE
```

### Cookie và đăng nhập

Công cụ lấy nguồn phù hợp đầu tiên theo thứ tự sau:

1. Tệp `cookies.txt`: tùy chọn `--cookies-file`, biến `LINGOTUBE_COOKIES_FILE` hoặc đường dẫn trong cài đặt.
2. Trình duyệt được chọn rõ ràng: tùy chọn `--browser` hoặc `browser` trong cài đặt.
3. Hồ sơ đăng nhập lingotube, nếu được tạo bằng `lingotube login`.
4. Nếu không, lần lượt thử Firefox, Chrome, Edge và Brave.

Trên Windows, Chrome và Edge bảo vệ cookie của chúng, và thường không thể đọc trực tiếp.
Với chúng, hãy dùng `lingotube login`. Xuất tệp vẫn là phương án dự phòng.

> [!CAUTION]
> Tệp `cookies.txt` cấp quyền truy cập vào tài khoản của bạn. Hãy giữ nó như mật khẩu và đừng đặt
> trong kho mã hay thư mục dùng chung. Cookie, token và tiêu đề ủy quyền
> không bao giờ xuất hiện trong đầu ra, thông báo lỗi hay `--json`: thay vào đó sẽ in `***`.

Nếu cookie ngừng hoạt động (mã thoát `4`), hãy chạy lại `lingotube login` hoặc xuất một tệp mới.

### Các chế độ dịch

| Chế độ | Khi nào bật | Ai dịch |
|---|---|---|
| **Chat** (mặc định) | chưa cấu hình gì | chat của YouTube trả văn bản ngay bằng ngôn ngữ cần thiết |
| **Mô hình riêng** | mục `[translator]` được đặt trong cài đặt | mô hình của bạn với API tương thích OpenAI |
| **Tác tử** | `transcript` → dịch → `build` | tác tử AI hoặc chính bạn làm thủ công; lingotube chỉ kiểm tra bản dịch và dựng phụ đề |

Cài đặt nằm trong `settings.toml`:

- Windows: `%LOCALAPPDATA%\lingotube\settings.toml`
- macOS: `~/Library/Application Support/lingotube/settings.toml`
- Linux: `~/.config/lingotube/settings.toml`

Ví dụ chế độ «mô hình riêng»:

```toml
lang = "vi"

[translator]
base_url = "https://api.openai.com/v1"   # hoặc mô hình cục bộ, ví dụ http://127.0.0.1:11434/v1
model = "gpt-4o-mini"
api_key_env = "LINGOTUBE_API_KEY"        # tên biến môi trường chứa khóa
batch_size = 40
```

Khóa không bao giờ được ghi vào tệp cài đặt: công cụ chỉ đọc nó từ biến môi trường.

Chế độ «tác tử»:

```sh
lingotube transcript <liên kết> -o orig.json          # bản gốc ở dạng JSON
# dịch trường text của từng dòng, giữ nguyên id và thời gian, lưu thành vi.json
lingotube build <liên kết> --lang vi --from vi.json   # kiểm tra và dựng phụ đề
```

> [!TIP]
> Để giữ bản dịch sát từng chữ, hãy dùng chế độ «mô hình riêng» hoặc «tác tử»: chúng lấy bản gốc trước,
> rồi kiểm tra bản dịch theo số dòng. Chat có thể diễn đạt lại hoặc gộp các câu.

### Mã thoát

| Mã | Ý nghĩa |
|---|---|
| `0` | Thành công. |
| `1` | Lỗi khác. |
| `2` | Tùy chọn lệnh không hợp lệ. |
| `3` | Chat không khả dụng cho video hoặc tài khoản này. |
| `4` | Vấn đề đăng nhập: không tìm thấy cookie hoặc cookie đã hết hạn, hoặc chưa đặt khóa mô hình. |
| `5` | Kết quả chưa đầy đủ: tệp đã được ghi, nhưng bản chép lời chưa tới cuối video. |
| `6` | Lỗi mạng sau khi hết số lần thử lại. |
| `7` | Dữ liệu không qua được bước kiểm tra. |
| `8` | YouTube đã thay đổi định dạng mà lingotube đọc. Hãy cập nhật lingotube: xem mục «Cài đặt». |
| `130` | Bị người dùng ngắt (Ctrl+C). |

## Skill cho tác tử AI

Skill chạy [công cụ dòng lệnh](#công-cụ-dòng-lệnh-cli) thay cho tác tử, vì vậy hãy cài công cụ trước, rồi cài skill.


Kho mã có một skill theo định dạng mở Agent Skills. Với skill này, tác tử AI (Claude Code, Codex,
Cursor, Gemini CLI và các tác tử khác) tóm tắt video, tạo bản chép lời và phụ đề,
tìm một thời điểm theo mô tả, đồng thời hỗ trợ cài đặt và đăng nhập.

```sh
npx skills add antondmtvch/lingotube
```

Không có Node.js, hãy chép thư mục `skills/lingotube/` vào thư mục skills của tác tử
(`~/.claude/skills/` cho Claude Code hoặc `~/.agents/skills/` cho hầu hết các tác tử khác).

Sau đó đưa cho tác tử một liên kết và nói bạn cần gì:

```text
Tóm tắt video này: https://youtu.be/VIDEO_ID
Video này nói về dựng phim ở đoạn nào? https://youtu.be/VIDEO_ID
Tạo phụ đề tiếng Việt cho video này: https://youtu.be/VIDEO_ID
```

## Tiện ích mở rộng trình duyệt

Tiện ích mở rộng Manifest V3 cho Chrome, Edge và Firefox, hiển thị phụ đề đã dịch phía trên trình phát YouTube. Nó đang được phát triển.

- Một nút trong trình phát bật phụ đề; có thể kéo bảng chứa văn bản.
- Bạn chọn một trong 30 ngôn ngữ hoặc tự nhập ngôn ngữ của mình.
- Thời gian và văn bản gốc lấy từ chính phụ đề của YouTube; chat chỉ dịch chúng.
- Nó chạy trong trình duyệt mà bạn đã đăng nhập YouTube, nên không cần cấu hình cookie.

Nó chưa có trên cửa hàng nào. Hãy tải các tệp dành cho trình duyệt của bạn từ [trang bản phát hành](https://github.com/antondmtvch/lingotube/releases):

- Chrome: tải `lingotube-<version>-chromium.zip` và giải nén vào một thư mục mà bạn sẽ giữ lại. Mở `chrome://extensions`, bật «Developer mode», bấm «Load unpacked» và chọn thư mục đó. Khi khởi động, Chrome nhắc về các tiện ích ở chế độ nhà phát triển. Để cập nhật, hãy thay các tệp trong thư mục và bấm nút tải lại trên thẻ của tiện ích.
- Edge: dùng cùng tệp nén đó. Mở `edge://extensions`, bật «Developer mode», bấm «Load unpacked» và chọn thư mục.
- Firefox 140 trở lên: tải `lingotube-<version>-firefox.xpi`, kéo tệp vào cửa sổ Firefox (hoặc mở `about:addons`, bấm biểu tượng bánh răng và chọn «Install Add-on From File...») rồi xác nhận cài đặt.

Brave, Opera và Vivaldi chưa được kiểm thử.

## Hạn chế

Các hạn chế này áp dụng cho cả ba thành phần, vì tất cả đều dựa vào chat của YouTube.


- Chat chỉ hoạt động với người dùng đã đăng nhập trên 13 tuổi, không có ở mọi quốc gia
  và không có dưới mọi video.
- Không hỗ trợ tài khoản thương hiệu: dùng tài khoản chính của trình duyệt.
- Một giờ video mất vài phút: các yêu cầu được gửi lần lượt.
- Thời gian của các dòng do chat quyết định. Ở video dài, một số dòng có thể lệch vài
  giây; độ lệch cố định được chỉnh bằng tùy chọn `--offset`.
- Văn bản của video dài không đảm bảo sát từng chữ: đôi khi chat trả lời bằng văn bản
  gần nghĩa, và công cụ không phát hiện được. Với mục đích quan trọng, hãy đối chiếu kết quả với bản ghi.
- Không hỗ trợ proxy.

## Phát triển

Phụ thuộc và môi trường được quản lý bằng uv:

```sh
uv sync
uv run pytest
uv run ruff check
```

Độ phủ kiểm thử (các giá trị trong huy hiệu ở trên được đo bằng các lệnh này và cập nhật thủ công):

```sh
uv run --with pytest-cov pytest --cov=lingotube
cd extension && node --test --experimental-test-coverage --test-coverage-exclude='tests/**' tests/
```

Cấu trúc dự án:

- `src/lingotube/` — lõi: CLI, ủy quyền, chat, dịch, bộ nhớ đệm và ghi kết quả.
- `skills/lingotube/` — skill cho tác tử AI.
- `extension/` — tiện ích mở rộng trình duyệt.
- `tests/` — kiểm thử Python.
- `docs/readme/` — các bản dịch của README này.
