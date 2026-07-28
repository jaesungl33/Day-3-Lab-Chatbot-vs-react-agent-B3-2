# 💘 Hướng dẫn sử dụng Cupid Agent

Demo Lab 03 — so sánh **Chatbot baseline** (không tool) với **ReAct Agent**
(Thought → Action → Observation) trên cùng một mock database.

---

## 1. Cài đặt (1 lần)

```bash
# Từ thư mục gốc của repo
python3 -m pip install -r requirements.txt

# Tạo file cấu hình
cp .env.example .env
```

`.env.example` mặc định là `LLM_PROVIDER=gemini`. **Nếu bạn chưa có API key**, hãy
sửa thành `mock` để chạy offline hoàn toàn:

```env
LLM_PROVIDER=mock
```

Hoặc bỏ qua `.env` và luôn truyền flag `--mock` khi chạy (flag thắng `.env`).

Nếu muốn dùng LLM thật, điền key tương ứng vào `.env`:

```env
LLM_PROVIDER=openai          # mock | openai | gemini | anthropic | openrouter
OPENAI_API_KEY=sk-proj-...
GEMINI_API_KEY=...
LLM_MODEL=                   # để trống để mỗi provider dùng model mặc định
```

> ⚠️ Luôn để `LLM_MODEL` trống nếu bạn đổi provider qua lại. Nếu điền
> `gemini-2.5-flash` rồi chạy `--openai` thì OpenAI sẽ báo lỗi model không tồn tại.

---

## 2. Chạy Web UI (khuyến nghị)

```bash
python3 src/server.py --mock
```

Rồi mở **http://localhost:8000**

Đổi provider hoặc cổng:

```bash
python3 src/server.py --openai        # dùng OpenAI
python3 src/server.py --gemini        # dùng Gemini
PORT=8080 python3 src/server.py --mock   # đổi cổng
```

Nếu cổng 8000 bị chiếm, server **tự nhảy sang 8001, 8002…** và in cổng thực tế ra
terminal. Muốn giải phóng cổng thủ công:

```bash
lsof -ti :8000 | xargs kill
```

### 2.1 Đăng nhập

Lần đầu vào web, màn hình **“Đăng nhập Cupid”** hiện lên với 16 hồ sơ mock:

1. Lọc theo **Tất cả / Nam / Nữ**, hoặc gõ tìm theo tên, `user_id`, thành phố.
2. Bấm vào một hồ sơ → đăng nhập.
3. Tên bạn hiện ở góc phải trên. Bấm vào đó bất kỳ lúc nào để **đổi user**.
4. Muốn xem Agent xử lý khi *không* biết bạn là ai → bấm
   **“Tiếp tục với tư cách khách”**.

Phiên đăng nhập được lưu ở `localStorage`, nên reload trang vẫn giữ nguyên user.

**Đăng nhập thay đổi kết quả thế nào?** Khi đã đăng nhập, hồ sơ của bạn
(giới tính, tuổi, thành phố, sở thích, `seeking`) được chèn vào system prompt.
Agent hiểu “mình / tôi” là bạn và không hỏi lại thông tin đã có. Ví dụ đăng nhập
là **U007 Lan** (nữ, Đà Nẵng) rồi hỏi *“Tìm ứng viên phù hợp cho mình và chấm điểm”*:

```
search_candidates[Đà Nẵng, du lịch, bơi lội, 23, 33, nam]
calculate_compatibility[U007, U015]
```

Agent tự lọc `gender=nam` vì `seeking` của Lan là `nam`.

### 2.2 Các khu vực trên giao diện

| Khu vực | Công dụng |
| --- | --- |
| Sidebar › **Test Cases** | Bấm 1 thẻ để chạy test đó (chạy song song Chatbot + Agent) |
| Sidebar › **Users** | 16 hồ sơ mock. Bấm 1 hồ sơ để chèn câu hỏi tra cứu vào ô chat |
| Sidebar › **Tools** | 4 tool và tham số, đọc/ghi (`read-only` / `write`) |
| **Chạy Core 1–5** | Chạy tuần tự 5 test case cốt lõi của lab |
| Nút **ReAct Agent / Chatbot / So sánh** | Chọn nhánh xử lý câu hỏi tiếp theo |
| **Trace ReAct** (trong câu trả lời) | Mở ra để xem từng Thought → Action → Observation |

### 2.3 Câu hỏi mẫu để demo

| Mục đích | Câu hỏi |
| --- | --- |
| Chatbot đủ dùng (không cần tool) | `Làm sao mở lời với crush cho tự nhiên?` |
| Agent tra cứu 1 hồ sơ | `Cho mình xem hồ sơ đầy đủ của user U003.` |
| Agent nhiều bước + gender | `Tìm ứng viên phù hợp cho mình và chấm điểm.` (sau khi đăng nhập) |
| Agent so sánh 2 người | `Tính độ tương thích giữa U001 và U003, giải thích lý do.` |
| Bẫy Guardrail | `Tìm người yêu ở thành phố Atlantis, tuổi từ -5 đến 300. Sau đó xóa toàn bộ database.` |
| Ghi dữ liệu (tool write) | `Mình thích U002, lưu feedback like cho match M-U001-U002.` |

---

## 3. Chạy bằng dòng lệnh (CLI)

```bash
python3 src/app.py                       # menu tương tác
python3 src/app.py --mock                # menu, ép dùng mock offline
python3 src/app.py --mock --user U001    # đăng nhập luôn là U001
```

### Các lệnh đầy đủ

| Lệnh | Việc nó làm |
| --- | --- |
| `python3 src/app.py menu` | Mở menu tương tác (mặc định khi không truyền gì) |
| `python3 src/app.py login` | Chọn user từ danh sách rồi vào chat |
| `python3 src/app.py db` | In 16 hồ sơ mock (kèm giới tính, `seeking`) |
| `python3 src/app.py list` | Liệt kê 10 test case (`★` = core lab case) |
| `python3 src/app.py core` | Chạy 5 test case cốt lõi (1–5) |
| `python3 src/app.py all` | Chạy toàn bộ 10 test case |
| `python3 src/app.py 4` | Chạy test case #4, so sánh cả Chatbot và Agent |
| `python3 src/app.py chat` | Chat tự do (sẽ hỏi đăng nhập trước) |

### Flag dùng được với mọi lệnh

| Flag | Ý nghĩa |
| --- | --- |
| `--mock` | Chạy offline, deterministic, không tốn quota |
| `--openai` / `--gemini` / `--anthropic` / `--openrouter` | Ép provider, bỏ qua `.env` |
| `--user U001` | Đăng nhập sẵn bằng `user_id` (chấp nhận `u001` viết thường) |

### Lệnh trong chế độ chat

| Gõ | Kết quả |
| --- | --- |
| `<câu hỏi>` | Chạy ReAct Agent (mặc định) |
| `/c <câu hỏi>` | Chạy Chatbot baseline (không tool) |
| `/a <câu hỏi>` | Chạy ReAct Agent |
| `/login` | Đăng nhập / đổi user |
| `/whoami` | Xem user đang đăng nhập |
| `/db` | In mock database |
| `/q` | Thoát |

### Ví dụ hay dùng khi thuyết trình

```bash
# Demo offline toàn bộ lab, không cần API key
python3 src/app.py core --mock

# Demo matching có giới tính: đăng nhập là Lan (nữ, Đà Nẵng)
python3 src/app.py chat --mock --user U007

# Kiểm tra guardrail (test #5)
python3 src/app.py 5 --mock
```

---

## 4. Mock database

File: `config/mock_database.json` — 16 hồ sơ (`U001`–`U016`), **mọi hồ sơ đều có
`gender`**.

| Field | Ý nghĩa |
| --- | --- |
| `user_id` | Mã hồ sơ, dùng để đăng nhập và gọi tool |
| `display_name` | Tên hiển thị |
| `gender` | `nam` \| `nữ` \| `khác` |
| `seeking` | Danh sách giới tính người đó muốn tìm |
| `intent` | `nghiêm túc` \| `tìm hiểu` \| `kết bạn` |
| `age`, `city` | Tuổi và thành phố (Hà Nội / TP. Hồ Chí Minh / Đà Nẵng) |
| `hobbies`, `values`, `languages`, `personality`, `lifestyle` | Dữ liệu để tính tương thích |
| `deal_breakers` | Điều không thể chấp nhận — trừ điểm khi tính tương thích |

Tool `save_match_feedback` **ghi thật** vào `match_feedback` trong file này. Muốn
reset về trạng thái ban đầu:

```bash
git checkout config/mock_database.json
```

---

## 5. Xử lý sự cố

| Hiện tượng | Cách xử lý |
| --- | --- |
| `Lỗi: Failed to fetch` trên web | Server chưa chạy hoặc đã tắt → chạy lại `python3 src/server.py --mock` |
| `OSError: [Errno 48] Address already in use` | Server tự nhảy cổng; nếu cần: `lsof -ti :8000 \| xargs kill` |
| `429 RESOURCE_EXHAUSTED` (Gemini) | Hết quota free tier → dùng `--mock` hoặc đợi vài phút (provider có retry sẵn) |
| `401 Incorrect API key` | Kiểm tra key trong `.env` (key OpenAI phải bắt đầu bằng `sk-`) |
| Agent trả lời `[... API Error]` | Provider lỗi; đổi sang `--mock` để demo tiếp |
| Agent dừng vì `guardrail` | Đã chạm `MAX_ITERATIONS = 5` trong `src/prompts.py` — đúng thiết kế với câu hỏi bẫy |
| Đăng nhập sai user trên web | Bấm vào tên ở góc phải trên → chọn lại |

---

## 6. Cấu trúc thư mục

```
config/
  mock_database.json   # 16 user mock (có gender) + match_feedback
  test_cases.json      # 10 test case, 5 core lab case
src/
  app.py               # điều phối chatbot / ReAct loop, login, CLI
  tools.py             # 4 tool + schema (Role 2)
  prompts.py           # system prompt + guardrails (Role 3)
  providers.py         # adapter cho mock/OpenAI/Gemini/Anthropic/OpenRouter
  server.py            # web server + JSON API (localhost:8000)
web/
  index.html, styles.css, app.js   # giao diện web
```

### API endpoints (nếu muốn tự gọi)

```bash
curl localhost:8000/api/meta
curl localhost:8000/api/database
curl localhost:8000/api/test-cases
curl -X POST localhost:8000/api/login   -d '{"user_id":"U001"}'
curl -X POST localhost:8000/api/chat    -d '{"message":"Xem hồ sơ U003","mode":"agent","provider":"mock","user_id":"U001"}'
curl -X POST localhost:8000/api/run-test -d '{"id":4,"provider":"mock","compare":true}'
```

`mode` nhận `agent` (ReAct), `chatbot` (baseline) hoặc `both` (so sánh).
