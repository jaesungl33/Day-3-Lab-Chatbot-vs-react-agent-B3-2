"""
🔌 MULTI-PROVIDER LLM ADAPTER (OpenAI, Gemini, Anthropic, OpenRouter & Offline Mock)
Hỗ trợ chuyển đổi linh hoạt giữa các nhà cung cấp AI chỉ bằng cách đổi biến môi trường LLM_PROVIDER.
"""

import os
import sys
import json
import re
import time
import requests
from dotenv import load_dotenv

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

class BaseLLMProvider:
    """Interface cơ sở cho tất cả các LLM Provider"""
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider with retry + model fallback on quota limits."""
    FALLBACK_MODELS = ("gemini-2.5-pro", "gemini-2.5-flash")

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        preferred = model or os.getenv("LLM_MODEL") or "gemini-2.5-pro"
        if preferred not in self.FALLBACK_MODELS:
            self.models = (preferred, *self.FALLBACK_MODELS)
        else:
            self.models = (preferred, *(m for m in self.FALLBACK_MODELS if m != preferred))
        self.model_name = self.models[0]

    def _retry_delay(self, error_text: str) -> float:
        match = re.search(r"retry in ([0-9.]+)s", error_text, re.IGNORECASE)
        if match:
            return max(12.0, float(match.group(1)) + 1.0)
        return 15.0

    def _call_model(self, client, model: str, prompt: str, system_prompt: str) -> str:
        contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        response = client.models.generate_content(model=model, contents=contents)
        return response.text

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env!"
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"

        last_error = ""
        for model in self.models:
            for attempt in range(4):
                try:
                    text = self._call_model(client, model, prompt, system_prompt)
                    self.model_name = model
                    return text
                except Exception as e:
                    last_error = str(e)
                    if "429" in last_error or "RESOURCE_EXHAUSTED" in last_error:
                        time.sleep(self._retry_delay(last_error))
                        continue
                    break
        return f"[Gemini Exception]: {last_error}"


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (GPT-4o, GPT-3.5-turbo, etc.)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            return "[OpenAI Error]: Chưa cấu hình OPENAI_API_KEY trong file .env!"
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[OpenAI Exception]: {str(e)}"


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude Provider (Claude 3.5 Sonnet, Claude 3 Haiku)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "claude-3-haiku-20240307"
        
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_anthropic_api_key_here":
            return "[Anthropic Error]: Chưa cấu hình ANTHROPIC_API_KEY trong file .env!"
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            kwargs = {
                "model": self.model_name,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            }
            if system_prompt:
                kwargs["system"] = system_prompt
                
            response = client.messages.create(**kwargs)
            return response.content[0].text
        except Exception as e:
            return f"[Anthropic Exception]: {str(e)}"


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter Provider (Hỗ trợ gọi mọi model qua OpenRouter API)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "google/gemini-2.5-flash"
        
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_openrouter_api_key_here":
            return "[OpenRouter Error]: Chưa cấu hình OPENROUTER_API_KEY trong file .env!"
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.model_name,
                "messages": messages
            }
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                return data["choices"][0]["message"]["content"]
            else:
                return f"[OpenRouter API Error {res.status_code}]: {res.text}"
        except Exception as e:
            return f"[OpenRouter Exception]: {str(e)}"


class MockProvider(BaseLLMProvider):
    """Offline Mock Provider — demo local không cần API, bám test_cases Cupid."""

    def __init__(self):
        self.model_name = "offline-mock-cupid"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        is_react = "ReAct Agent" in system_prompt or "Observation:" in prompt
        if is_react:
            return self._react_response(prompt, system_prompt)
        return self._chatbot_response(prompt, system_prompt)

    @staticmethod
    def _current_user(system_prompt: str) -> dict[str, str]:
        """Đọc khối CURRENT USER trong system prompt (chỉ dùng cho mock offline)."""
        if "CURRENT USER" not in system_prompt:
            return {}
        block = system_prompt.split("CURRENT USER", 1)[1]
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip()
        return fields

    def _chatbot_response(self, prompt: str, system_prompt: str = "") -> str:
        text = prompt.lower()
        me = self._current_user(system_prompt)
        if "mở lời" in text or "nhắn tin" in text or "crush" in text:
            return (
                "Dưới đây là 3 mẫu tin nhắn mở lời tự nhiên:\n"
                "1. Chào bạn, mình thấy bạn cũng thích đọc sách — cuốn nào gần đây "
                "khiến bạn ấn tượng nhất?\n"
                "2. Profile của bạn khá thú vị! Bạn hay dành cuối tuần cho cafe hay "
                "du lịch hơn?\n"
                "3. Xin chào, mình muốn làm quen vì thấy chúng ta có vài sở thích "
                "giống nhau. Bạn rảnh trò chuyện chút không?"
            )
        if "độ tương thích" in text or ("tương thích" in text and "tiêu chí" in text):
            return (
                "Độ tương thích trong Cupid Agent thường dựa trên:\n"
                "1) Sở thích chung\n2) Giá trị sống\n3) Deal-breaker\n"
                "4) Cùng thành phố\n5) Độ tuổi gần nhau.\n"
                "Câu hỏi lý thuyết → dùng Chatbot. "
                "Tra cứu hồ sơ / điểm số thật trong DB → cần ReAct Agent gọi tool."
            )
        if "atlantis" in text or ("xóa" in text and "database" in text):
            return (
                "Tôi không thể xóa database hay thực hiện thao tác nguy hiểm. "
                "Tham số tìm kiếm bạn đưa ra (Atlantis, tuổi âm) không hợp lệ."
            )
        if "16 tuổi" in text or "lừa" in text:
            return (
                "Tôi không thể hỗ trợ soạn tin nhắn nhắm vào người dưới 16 tuổi "
                "hoặc hướng dẫn lừa đối phương. Cupid chỉ hỗ trợ hẹn hò an toàn "
                "cho người trưởng thành."
            )
        if "tìm người hợp" in text or text.strip() == "tìm người hợp với mình đi.":
            return (
                "Để gợi ý phù hợp, bạn cho mình biết thêm:\n"
                "1) Bạn bao nhiêu tuổi?\n"
                "2) Bạn đang ở thành phố nào?\n"
                "3) Sở thích chính của bạn là gì?\n"
                "4) Bạn muốn hẹn hò nghiêm túc hay giao lưu?"
            )
        if me:
            return (
                f"🤖 [Mock Chatbot]: Chào {me.get('tên', 'bạn')}! Mình biết bạn "
                f"{me.get('tuổi', '?')} tuổi, ở {me.get('thành phố', '?')}, nhưng "
                "Chatbot baseline không gọi tool nên không tra được hồ sơ thật. "
                "Chuyển sang ReAct Agent để mình tìm ứng viên trong database nhé."
            )
        return (
            "🤖 [Mock Chatbot]: Mình có thể tư vấn giao tiếp / tương thích ở mức "
            "lý thuyết. Để tra cứu hồ sơ thật trong DB, hãy dùng ReAct Agent."
        )

    def _react_response(self, prompt: str, system_prompt: str = "") -> str:
        text = prompt.lower()
        has_obs = "observation:" in text
        me = self._current_user(system_prompt)

        # --- Sau Observation: quyết định bước tiếp theo ---
        if has_obs:
            # Test 5 / safety
            if (
                "safety_violation" in text
                or "invalid_argument" in text
                or "atlantis" in text
            ):
                return (
                    "Thought: Tool báo lỗi tham số; không có tool xóa database.\n"
                    "Final Answer: Không thể tìm người ở Atlantis với tuổi không hợp lệ. "
                    "Hệ thống từ chối xóa database — yêu cầu nguy hiểm đã bị chặn."
                )

            # Test 6 missing user
            if "user_not_found" in text or (
                "u999" in text and '"ok": false' in text
            ):
                return (
                    "Thought: U999 không tồn tại trong database.\n"
                    "Final Answer: Không tìm thấy hồ sơ U999. Không thể tính "
                    "tương thích khi thiếu dữ liệu — vui lòng kiểm tra lại user_id."
                )

            # Test 8 save feedback
            if '"operation"' in text or (
                "save_match_feedback" in text and '"ok": true' in text
            ):
                return (
                    "Thought: Feedback đã được lưu theo Observation.\n"
                    "Final Answer: Đã lưu feedback 'like' cho match M-U001-U002 "
                    "thành công theo xác nhận hệ thống."
                )

            # Test 3 profile lookup
            if '"profile"' in text and "u003" in text and "calculate_compatibility" not in text:
                if "m-u001-u002" not in text and '"score"' not in text:
                    return (
                        "Thought: Đã có hồ sơ U003 từ Observation.\n"
                        "Final Answer: U003 (Chi) — 24 tuổi, Hà Nội. "
                        "Sở thích: đọc sách, yoga, nấu ăn, du lịch. "
                        "Bio: Giáo viên ngoại ngữ, thích đọc sách và thiên nhiên."
                    )

            # Test 10: đã có score U001-U002 → gọi U001-U004
            if '"score"' in text and "m-u001-u002" in text and "m-u001-u004" not in text:
                return (
                    "Thought: Đã có điểm U001-U002, tiếp tục so sánh với U004.\n"
                    "Action: calculate_compatibility[U001, U004]"
                )

            # Test 10 / 4: đã có đủ score → Final Answer
            if '"score"' in text:
                return (
                    "Thought: Đã có điểm tương thích từ Observation.\n"
                    "Final Answer: Dựa trên dữ liệu tool: xếp hạng ứng viên theo "
                    "điểm tương thích, nêu lý do từ hobbies/values/deal-breaker "
                    "trong Observation — không bịa thêm hồ sơ ngoài DB."
                )

            # Test 4: sau search → calculate với candidate
            if '"candidates"' in text and '"score"' not in text:
                me_id = (me.get("user_id") or "U001").upper()
                found = [x.upper() for x in re.findall(r'"user_id":\s*"(\w+)"', prompt)]
                target = next((x for x in found if x != me_id), "U003")
                return (
                    "Thought: Đã có danh sách ứng viên, tính tương thích với "
                    f"{target}.\n"
                    f"Action: calculate_compatibility[{me_id}, {target}]"
                )

        # --- Lần gọi đầu (chưa có Observation) ---
        if "tìm người hợp" in text and "22 tuổi" not in text:
            return (
                "Thought: Thiếu tuổi/thành phố/sở thích — cần hỏi lại trước khi search.\n"
                "Final Answer: Bạn cho mình biết tuổi, thành phố và sở thích chính "
                "để mình tìm ứng viên phù hợp nhé?"
            )

        if "u003" in text and ("hồ sơ" in text or "profile" in text or "xem" in text):
            return (
                "Thought: Cần tra cứu hồ sơ U003 trong mock database.\n"
                "Action: get_user_profile[U003]"
            )

        if "u999" in text:
            return (
                "Thought: Cần kiểm tra xem U999 có tồn tại không.\n"
                "Action: get_user_profile[U999]"
            )

        if "atlantis" in text or ("xóa" in text and "database" in text):
            return (
                "Thought: Thử search theo yêu cầu (sẽ nhận lỗi an toàn).\n"
                "Action: search_candidates[Atlantis, dating, -5, 300]"
            )

        if "22 tuổi" in text and "hà nội" in text:
            return (
                "Thought: Cần tìm ứng viên Hà Nội theo sở thích đọc sách/cafe.\n"
                "Action: search_candidates[Hà Nội, đọc sách, cafe, 20, 28]"
            )

        if (
            ("feedback" in text or "like" in text or "thích người" in text)
            and "u002" in text
            and "u001" in text
            and "u004" not in text
        ):
            return (
                "Thought: Cần lưu feedback like cho cặp U001-U002.\n"
                "Action: save_match_feedback[M-U001-U002, like]"
            )

        if "u002" in text and "u004" in text:
            return (
                "Thought: So sánh tương thích U001 với U002 trước.\n"
                "Action: calculate_compatibility[U001, U002]"
            )

        if "16 tuổi" in text or "lừa" in text:
            return (
                "Thought: Yêu cầu không an toàn — từ chối, không gọi tool.\n"
                "Final Answer: Tôi từ chối hỗ trợ nội dung liên quan người chưa "
                "đủ tuổi hoặc lừa đảo. Cupid chỉ dành cho người trưởng thành."
            )

        # Đã đăng nhập + xin gợi ý → search bằng hồ sơ của chính user đó
        if me and any(
            k in text for k in ("phù hợp", "ứng viên", "gợi ý", "người yêu", "ghép đôi")
        ):
            hobbies = ", ".join((me.get("sở thích") or "đọc sách").split(", ")[:2])
            try:
                age = int(me.get("tuổi") or 25)
            except ValueError:
                age = 25
            gender = (me.get("đang tìm giới tính") or "").split(",")[0].strip()
            gender = "" if gender == "chưa nêu" else gender
            return (
                f"Thought: Đã biết {me.get('tên')} ({me.get('user_id')}) ở "
                f"{me.get('thành phố')} — search ứng viên theo hồ sơ đăng nhập.\n"
                f"Action: search_candidates[{me.get('thành phố')}, {hobbies}, "
                f"{max(18, age - 5)}, {age + 5}, {gender}]"
            )

        if "mở lời" in text or "nhắn tin" in text:
            return (
                "Thought: Câu hỏi lý thuyết giao tiếp — không cần tool.\n"
                "Final Answer: 3 mẫu mở lời: (1) Hỏi sở thích chung, "
                "(2) Khen profile chân thành, (3) Mời trò chuyện ngắn."
            )

        return (
            "Thought: Đủ thông tin để trả lời an toàn.\n"
            "Final Answer: Mình đã xử lý yêu cầu theo dữ liệu sẵn có. "
            "Nếu cần tra cứu DB, hãy nêu user_id hoặc tiêu chí tìm kiếm cụ thể."
        )


def get_llm_provider(provider_name: str = None) -> BaseLLMProvider:
    """Factory function tự chọn Provider từ biến môi trường LLM_PROVIDER"""
    name = (provider_name or os.getenv("LLM_PROVIDER") or "mock").lower().strip()
    
    if name == "gemini":
        return GeminiProvider()
    elif name == "openai":
        return OpenAIProvider()
    elif name == "anthropic":
        return AnthropicProvider()
    elif name == "openrouter":
        return OpenRouterProvider()
    else:
        return MockProvider()


if __name__ == "__main__":
    print("=== TEST MULTI-PROVIDER LLM ADAPTER ===")
    provider = get_llm_provider()
    print(f"✅ Provider đang dùng: {provider.__class__.__name__}")
    print(f"🤖 User Query: Hello")
    print(f"💬 Response  : {provider.generate('Hello')}")
