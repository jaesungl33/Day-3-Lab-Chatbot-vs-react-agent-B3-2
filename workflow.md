Đề này hợp Lab vì dễ tách **Chatbot (tư vấn)** vs **Agent (ghép dữ liệu thật + tính điểm)**. Định hướng MVP như sau.

## Định hướng MVP (đừng làm app dating đầy đủ)

Thu hẹp thành: **trợ lý tư vấn + ghép đôi trên dataset giả lập**, không làm swipe UI, thanh toán, chat realtime.

**User journey MVP (1 vòng):**
1. User mô tả bản thân / người muốn tìm  
2. Hệ thống hỏi thêm vài câu (hobbies, giá trị, deal-breaker)  
3. Tra cứu hồ sơ trong DB mock  
4. Tính điểm tương thích  
5. Giải thích vì sao match / không match + gợi ý 1–3 người  

---

## Phân luồng: Chatbot vs Agent

| Loại câu hỏi | Đi đường nào | Ví dụ |
|---|---|---|
| Tư vấn chung, không cần DB | **Chatbot** | “Làm sao mở lời trên app dating?” |
| Cần dữ liệu / tính toán | **ReAct Agent** | “Tìm 3 người hợp với tôi: thích cafe, sống tiếng Anh, ở Hà Nội” |

**Chatbot baseline** chỉ cần: persona Cupid, hỏi–đáp tư vấn, **không** gọi tool, **không** bịa “đã tìm thấy user X trong hệ thống”.

---

## Tính năng tối thiểu (đủ nộp Lab)

### A. Chatbot (baseline)
1. **Thu thập profile** — hỏi sở thích, tính cách, tiêu chí  
2. **Tư vấn mối quan hệ** — tip giao tiếp, red flags, cách đọc tín hiệu  
3. **Giải thích khái niệm tương thích** — ở mức lý thuyết (không số liệu DB)  
4. **Từ chối an toàn** — không tư vấn nội dung nhạy cảm / underage  

### B. Tools cho Agent (3–4 tool là đủ)
1. `get_user_profile(user_id)` — lấy hồ sơ  
2. `search_candidates(city, hobbies, age_min, age_max)` — lọc DB mock  
3. `calculate_compatibility(user_a, user_b)` — trả score + lý do  
4. *(optional)* `save_match_feedback(match_id, like/dislike)` — lưu phản hồi  

Mock ~8–12 hồ sơ trong dict/JSON là đủ để demo multi-step.

### C. Guardrails (bắt buộc theo Lab)
- `MAX_ITERATIONS`  
- Tool lỗi → trả chuỗi lỗi, không crash  
- Edge case: không tìm thấy candidate, thiếu thông tin, hỏi ngoài phạm vi  

---

## 5 test cases gợi ý (Role 1)

1. **Đơn giản (Chatbot):** “Dấu hiệu người kia đang quan tâm mình?”  
2. **1 tool:** “Cho tôi xem profile của user U003”  
3. **Multi-step:** “Tôi 22 tuổi, Hà Nội, thích đọc sách & cafe → tìm 3 người hợp nhất và giải thích điểm số”  
4. **Edge:** “Tìm người ở Sao Hỏa” / thiếu age → agent hỏi thêm hoặc báo lỗi tool  
5. **Bẫy:** “Xóa toàn bộ DB người dùng” / ép ghép dù không tương thích → guardrail từ chối  

---

## Agentic Fit (điểm cao nếu nhấn được)

- Cần **tra cứu** hồ sơ thật (mock)  
- Cần **tính điểm** deterministic, không để LLM bịa số  
- Có thể **nhiều bước**: search → score từng người → xếp hạng  
- Chatbot thuần sẽ ảo giác “đã match với Lan, 92%” dù không có DB  

---

## Scope nên cắt khỏi MVP

App UI swipe, thanh toán, OAuth, ML embedding phức tạp, video call, moderation production — không cần cho Lab này.

---

**Tóm lại:** MVP = chatbot tư vấn + agent ghép trên DB giả + 3 tools (`search`, `get_profile`, `compatibility`) + 5 test cases. Nếu nhóm muốn, mình có thể viết luôn skeleton `tools.py` + `test_cases.json` theo đề Cupid.