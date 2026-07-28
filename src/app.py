"""
💘 CUPID AGENT — Local Demo App (Role 4 Integrator)
Ghép Tools + Prompts + Test Cases + Mock JSON DB thành app chạy local.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from tools import AVAILABLE_TOOLS, DATABASE_PATH
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    REACT_SYSTEM_PROMPT,
    MAX_ITERATIONS,
    build_user_context,
)
from providers import get_llm_provider

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / "config"


def load_test_cases() -> list[dict]:
    """Đọc bộ test cases từ config/test_cases.json (Role 1)."""
    config_path = CONFIG_DIR / "test_cases.json"
    if not config_path.exists():
        config_path = Path("test_cases.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_mock_database() -> dict:
    """Đọc mock user database từ config/mock_database.json."""
    with open(DATABASE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def find_profile(user_id: str) -> dict | None:
    """Tìm hồ sơ theo user_id (không phân biệt hoa thường)."""
    if not user_id:
        return None
    wanted = user_id.strip().upper()
    profiles = load_mock_database().get("profiles", [])
    return next((p for p in profiles if p.get("user_id", "").upper() == wanted), None)


def login(user_id: str) -> dict | None:
    """Đăng nhập bằng user_id có sẵn trong mock database."""
    profile = find_profile(user_id)
    if profile is None:
        print(f"❌ Đăng nhập thất bại: không tìm thấy {user_id}")
        return None
    print(
        f"✅ Đã đăng nhập: {profile['user_id']} — {profile['display_name']} "
        f"({profile.get('gender')}, {profile['age']} tuổi, {profile['city']})"
    )
    return profile


def print_banner(provider) -> None:
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    db = load_mock_database()
    profiles = db.get("profiles", [])
    print("=" * 64)
    print("💘 CUPID AGENT — Lab 3: Chatbot vs ReAct Agent (LOCAL DEMO)")
    print("=" * 64)
    print(f"🔌 LLM Provider : {provider.__class__.__name__} ({model_name})")
    print(f"🗄️  Mock DB      : {DATABASE_PATH}")
    print(f"👥 Users in DB  : {len(profiles)} "
          f"({', '.join(p['user_id'] for p in profiles)})")
    print(f"🛠️  Tools        : {', '.join(sorted(AVAILABLE_TOOLS.keys()))}")
    print(f"🛡️  Guardrail    : MAX_ITERATIONS = {MAX_ITERATIONS}")
    print(f"📋 Test cases   : {len(load_test_cases())} "
          f"(core = {[t['id'] for t in load_test_cases() if t.get('core_lab_case')]})")
    print("=" * 64)


def show_database() -> None:
    """In danh sách user mock để demo / kiểm tra grounding."""
    db = load_mock_database()
    print("\n🗄️  MOCK DATABASE — profiles")
    print("-" * 64)
    for p in db.get("profiles", []):
        hobbies = ", ".join(p.get("hobbies", [])[:3])
        seeking = ", ".join(p.get("seeking") or []) or "-"
        print(
            f"  {p['user_id']} | {p['display_name']:7} | {p.get('gender', '?'):4} | "
            f"{p['age']:2} tuổi | {p['city']:16} | tìm: {seeking:9} | {hobbies}"
        )
    feedback = db.get("match_feedback", [])
    print(f"\n💾 match_feedback records: {len(feedback)}")
    for item in feedback:
        print(f"  - {item}")


def _split_action_args(raw: str) -> list[str]:
    """Tách tham số trong Action, tôn trọng chuỗi có dấu phẩy trong ngoặc kép."""
    args: list[str] = []
    current: list[str] = []
    in_quote: str | None = None

    for char in raw.strip():
        if char in ("'", '"') and (not in_quote or in_quote == char):
            in_quote = None if in_quote else char
            current.append(char)
        elif char == "," and not in_quote:
            args.append("".join(current).strip().strip("'\""))
            current = []
        else:
            current.append(char)

    if current:
        args.append("".join(current).strip().strip("'\""))
    return [arg for arg in args if arg]


def _normalize_tool_arg(arg: str) -> str:
    """Chuẩn hóa tham số tool (hỗ trợ cả city=Hà Nội lẫn Hà Nội)."""
    arg = arg.strip().strip("'\"")
    if "=" in arg:
        key, value = arg.split("=", 1)
        # Chỉ strip prefix nếu nhìn giống named arg
        if key.strip().replace("_", "").isalpha():
            return value.strip().strip("'\"")
    return arg


def _call_llm(provider, prompt: str, system_prompt: str, retries: int = 2) -> str:
    """Gọi LLM; mock không cần retry, Gemini thì retry nhẹ khi quota."""
    last = ""
    provider_name = provider.__class__.__name__
    attempts = 1 if provider_name == "MockProvider" else retries
    for _ in range(attempts):
        last = provider.generate(prompt, system_prompt=system_prompt)
        if not last.startswith("[Gemini Exception]") and not last.startswith("[Gemini Error]"):
            return last
        time.sleep(12)
    return last


def parse_action(text: str) -> tuple[str, list[str]] | None:
    """Parse Action: tool_name[tham_số] từ phản hồi LLM."""
    cleaned = re.sub(r"```(?:json|text)?\s*", "", text)
    match = re.search(r"Action:\s*(\w+)\[(.*)\]", cleaned, re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    tool_name = match.group(1)
    args = [_normalize_tool_arg(a) for a in _split_action_args(match.group(2))]
    return tool_name, [a for a in args if a]


def extract_field(text: str, field: str) -> str | None:
    """Trích Thought / Final Answer từ phản hồi LLM."""
    pattern = rf"{field}:\s*(.+?)(?:\n(?:Thought|Action|Final Answer|Observation):|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


def execute_tool(tool_name: str, args: list[str]) -> str:
    """Gọi tool từ AVAILABLE_TOOLS; trả chuỗi lỗi thay vì crash."""
    valid_tools = ", ".join(sorted(AVAILABLE_TOOLS.keys()))
    if tool_name not in AVAILABLE_TOOLS:
        return (
            f"LỖI: Tool '{tool_name}' không tồn tại. "
            f"Các tool hợp lệ: [{valid_tools}]"
        )

    fn = AVAILABLE_TOOLS[tool_name]
    try:
        if tool_name == "get_user_profile":
            if not args:
                return "LỖI: get_user_profile cần tham số user_id."
            return fn(args[0])

        if tool_name == "search_candidates":
            args = [_normalize_tool_arg(a) for a in args]
            if len(args) < 4:
                return (
                    "LỖI: search_candidates cần city, hobbies, age_min, age_max "
                    "[, gender]. Ví dụ: search_candidates[Hà Nội, đọc sách, 20, 28, nữ]"
                )
            # Hai tham số số nguyên là age_min/age_max; phần trước là hobbies,
            # phần sau (nếu có) là gender. Cách này chịu được số lượng hobby thay đổi.
            int_positions = [i for i, a in enumerate(args) if a.lstrip("-").isdigit()]
            if len(int_positions) < 2:
                return "LỖI: search_candidates cần age_min và age_max là số nguyên."
            i_min, i_max = int_positions[0], int_positions[1]
            city = args[0]
            hobbies = ", ".join(args[1:i_min]) or ""
            gender = next(
                (a for a in args[i_max + 1:] if not a.lstrip("-").isdigit()), ""
            )
            return fn(city, hobbies, int(args[i_min]), int(args[i_max]), gender)

        if tool_name == "calculate_compatibility":
            if len(args) < 2:
                return "LỖI: calculate_compatibility cần user_a, user_b."
            return fn(args[0], args[1])

        if tool_name == "save_match_feedback":
            if len(args) < 2:
                return "LỖI: save_match_feedback cần match_id, feedback."
            # Hỗ trợ cả M-U001-U002, like  lẫn  U001, U002, like
            if len(args) >= 3 and args[0].upper().startswith("U"):
                match_id = f"M-{'-'.join(sorted([args[0].upper(), args[1].upper()]))}"
                return fn(match_id, args[2])
            return fn(args[0], args[1])

        return fn(*args)
    except (TypeError, ValueError) as exc:
        return f"LỖI: Tham số không hợp lệ cho {tool_name}: {exc}"
    except Exception as exc:
        return f"LỖI: Không thể thực thi {tool_name}: {exc}"


def run_baseline_chatbot(user_query: str, provider, user: dict | None = None) -> dict:
    """Chatbot baseline: một LLM call, không gọi tool."""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    system_prompt = CHATBOT_BASELINE_PROMPT + build_user_context(user)
    response = _call_llm(provider, user_query, system_prompt)
    print(f"🤖 Chatbot trả lời:\n{response}")
    return {
        "mode": "chatbot",
        "response": response,
        "tool_calls": 0,
        "steps": 1,
        "events": [{"kind": "final", "step": 1, "text": response}],
    }


def run_react_agent(user_query: str, provider, user: dict | None = None) -> dict:
    """Vòng lặp ReAct: Thought -> Action -> Observation -> Final Answer."""
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")
    system_prompt = REACT_SYSTEM_PROMPT + build_user_context(user)
    history: list[str] = []
    events: list[dict] = []
    tool_calls = 0
    final_answer = None
    step = 0

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- 🔄 Vòng lặp ReAct (Step {step}/{MAX_ITERATIONS}) ---")

        prompt_parts = [f"Question: {user_query}"]
        if history:
            prompt_parts.append("\n".join(history))
        prompt_parts.append(
            "Tiếp tục suy luận theo định dạng Thought/Action hoặc Thought/Final Answer."
        )
        prompt = "\n\n".join(prompt_parts)

        response = _call_llm(provider, prompt, system_prompt)
        if response.startswith("[Gemini Exception]") or response.startswith("[Gemini Error]"):
            print(f"📤 LLM Response:\n{response}")
            print("👁️ Observation: LỖI API tạm thời — thử lại ở bước sau.")
            history.append("Observation: LỖI API tạm thời. Hãy thử lại Action hợp lệ.")
            events.append({"kind": "error", "step": step, "text": response})
            continue
        print(f"📤 LLM Response:\n{response}")

        thought = extract_field(response, "Thought")
        if thought:
            print(f"🧠 Thought: {thought}")
            events.append({"kind": "thought", "step": step, "text": thought})

        final_answer = extract_field(response, "Final Answer")
        if final_answer:
            print(f"🏁 Final Answer: {final_answer}")
            events.append({"kind": "final", "step": step, "text": final_answer})
            break

        parsed = parse_action(response)
        if not parsed:
            error_obs = (
                "LỖI: Không parse được Action. "
                "Dùng cú pháp Action: tool_name[tham_số] hoặc Final Answer."
            )
            print(f"👁️ Observation: {error_obs}")
            if thought:
                history.append(f"Thought: {thought}")
            history.append(f"Observation: {error_obs}")
            events.append({"kind": "observation", "step": step, "text": error_obs, "ok": False})
            continue

        tool_name, args = parsed
        print(f"🛠️ Action: {tool_name}[{', '.join(args)}]")
        observation = execute_tool(tool_name, args)
        tool_calls += 1
        print(f"👁️ Observation: {observation}")

        events.append(
            {"kind": "action", "step": step, "tool": tool_name, "args": args}
        )
        events.append(
            {
                "kind": "observation",
                "step": step,
                "text": observation,
                "ok": '"ok": true' in observation,
            }
        )

        if thought:
            history.append(f"Thought: {thought}")
        history.append(f"Action: {tool_name}[{', '.join(args)}]")
        history.append(f"Observation: {observation}")

    if final_answer is None:
        final_answer = (
            "Xin lỗi, tôi không thể hoàn thành yêu cầu trong giới hạn "
            f"{MAX_ITERATIONS} bước. Vui lòng thử lại với thông tin cụ thể hơn."
        )
        print(f"\n🛡️ GUARDRAIL TRIGGERED: Đã đạt giới hạn {MAX_ITERATIONS} bước.")
        print(f"🏁 Safe Fallback: {final_answer}")
        events.append({"kind": "guardrail", "step": step, "text": final_answer})

    return {
        "mode": "react_agent",
        "response": final_answer,
        "tool_calls": tool_calls,
        "steps": step,
        "trace": history,
        "events": events,
        "guardrail": any(e["kind"] == "guardrail" for e in events),
    }


def run_test_case(
    test_case: dict, provider, compare_both: bool = False, user: dict | None = None
) -> dict:
    """Chạy một test case theo expected_path hoặc so sánh cả hai mode."""
    case_id = test_case.get("id", "?")
    name = test_case.get("name", test_case.get("category", ""))
    question = test_case["question"]
    expected_path = test_case.get("expected_path", "chatbot")

    print("\n" + "=" * 64)
    print(f"📋 Test #{case_id}: {name}")
    print(f"📂 Category     : {test_case.get('category', 'N/A')}")
    print(f"🎯 Expected path: {expected_path}")
    print(f"🛠️  Expected tools: {test_case.get('expected_tools', [])}")
    print(f"❓ Question     : {question}")
    print("=" * 64)

    results: dict = {"id": case_id, "name": name, "expected_path": expected_path}

    if compare_both or expected_path == "chatbot":
        results["chatbot"] = run_baseline_chatbot(question, provider, user)

    if compare_both or expected_path in ("react_agent", "hybrid"):
        # Hybrid thiếu info → chatbot clarify; nếu needs_db thì agent
        if expected_path == "hybrid" and not compare_both:
            if test_case.get("user_context", {}).get("needs_db") and test_case.get(
                "expected_tools"
            ):
                results["agent"] = run_react_agent(question, provider, user)
            else:
                results["chatbot"] = run_baseline_chatbot(question, provider, user)
                results["agent"] = run_react_agent(question, provider, user)
        else:
            results["agent"] = run_react_agent(question, provider, user)

    return results


def summarize_results(all_results: list[dict]) -> None:
    print("\n" + "=" * 64)
    print("📊 TÓM TẮT KẾT QUẢ DEMO")
    print("=" * 64)
    for result in all_results:
        line = f"  ✅ Test #{result['id']}: {result.get('name', '')} ({result['expected_path']})"
        if "chatbot" in result:
            line += f" | Chatbot tools=0"
        if "agent" in result:
            line += (
                f" | Agent tools={result['agent']['tool_calls']}"
                f", steps={result['agent'].get('steps', 0)}"
            )
        print(line)
    print("=" * 64)


def run_core_lab_suite(
    provider, compare_multi_step: bool = True, user: dict | None = None
) -> list[dict]:
    """Chạy 5 core lab cases (core_lab_case=true)."""
    tests = load_test_cases()
    core_tests = [t for t in tests if t.get("core_lab_case")]
    if not core_tests:
        core_tests = tests[:5]

    print(f"\n🧪 Chạy {len(core_tests)} Core Lab Test Cases...\n")
    all_results = []
    is_mock = provider.__class__.__name__ == "MockProvider"

    for index, test_case in enumerate(core_tests):
        compare = compare_multi_step and test_case.get("id") in (3, 4, 5)
        result = run_test_case(test_case, provider, compare_both=compare, user=user)
        all_results.append(result)
        if not is_mock and index + 1 < len(core_tests):
            time.sleep(12)

    summarize_results(all_results)
    return all_results


def run_all_tests(provider, user: dict | None = None) -> list[dict]:
    """Chạy toàn bộ test cases trong config/test_cases.json."""
    tests = load_test_cases()
    print(f"\n🧪 Chạy toàn bộ {len(tests)} Test Cases...\n")
    all_results = []
    is_mock = provider.__class__.__name__ == "MockProvider"

    for index, test_case in enumerate(tests):
        compare = test_case.get("id") in (3, 4, 5)
        result = run_test_case(test_case, provider, compare_both=compare, user=user)
        all_results.append(result)
        if not is_mock and index + 1 < len(tests):
            time.sleep(12)

    summarize_results(all_results)
    return all_results


def choose_user() -> dict | None:
    """Cho người dùng chọn user để đăng nhập từ danh sách mock."""
    profiles = load_mock_database().get("profiles", [])
    print("\n🔐 ĐĂNG NHẬP — chọn user")
    print("-" * 64)
    for i, p in enumerate(profiles, 1):
        print(
            f"  {i:2}) {p['user_id']} · {p['display_name']:7} · "
            f"{p.get('gender', '?'):4} · {p['age']:2} tuổi · {p['city']}"
        )
    try:
        raw = input("\nNhập số thứ tự hoặc user_id (Enter để bỏ qua) > ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not raw:
        print("⚠️  Chưa đăng nhập — Agent sẽ phải hỏi lại thông tin của bạn.")
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(profiles):
        return login(profiles[int(raw) - 1]["user_id"])
    return login(raw)


def interactive_chat(provider, user: dict | None = None) -> None:
    """Chat tự do: chọn chatbot hoặc react agent."""
    print("\n💬 INTERACTIVE MODE")
    print("  Gõ câu hỏi. Prefix:")
    print("    /c  ...   → Chatbot baseline")
    print("    /a  ...   → ReAct Agent (mặc định)")
    print("    /db       → Xem mock database")
    print("    /login    → Đăng nhập / đổi user")
    print("    /whoami   → Xem user đang đăng nhập")
    print("    /q        → Thoát")
    while True:
        who = user["user_id"] if user else "khách"
        try:
            raw = input(f"\n[{who}] Bạn > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Bye!")
            break
        if not raw:
            continue
        if raw in ("/q", "quit", "exit"):
            print("👋 Bye!")
            break
        if raw == "/db":
            show_database()
            continue
        if raw == "/login":
            user = choose_user() or user
            continue
        if raw == "/whoami":
            if user:
                print(
                    f"👤 {user['user_id']} — {user['display_name']} "
                    f"({user.get('gender')}, {user['age']} tuổi, {user['city']}), "
                    f"tìm: {', '.join(user.get('seeking') or []) or 'chưa nêu'}"
                )
            else:
                print("👤 Chưa đăng nhập (khách). Gõ /login để đăng nhập.")
            continue
        if raw.startswith("/c "):
            run_baseline_chatbot(raw[3:].strip(), provider, user)
        elif raw.startswith("/a "):
            run_react_agent(raw[3:].strip(), provider, user)
        else:
            run_react_agent(raw, provider, user)


def print_menu(user: dict | None) -> None:
    who = (
        f"{user['user_id']} · {user['display_name']} ({user.get('gender')})"
        if user
        else "chưa đăng nhập (khách)"
    )
    print(
        f"""
┌─────────────────────────────────────────────────────────────┐
│  MENU DEMO LOCAL                                            │
│  👤 User: {who:<49}│
│                                                             │
│  1) Xem mock database (users)                               │
│  2) Liệt kê test cases                                      │
│  3) Chạy Core Lab (test 1–5)                                │
│  4) Chạy 1 test case theo ID                                │
│  5) Chạy TẤT CẢ test cases                                  │
│  6) Interactive chat (chatbot / agent)                      │
│  7) Đăng nhập / đổi user                                    │
│  0) Thoát                                                   │
└─────────────────────────────────────────────────────────────┘"""
    )


def list_test_cases() -> None:
    tests = load_test_cases()
    print("\n📋 TEST CASES")
    print("-" * 64)
    for t in tests:
        core = "★" if t.get("core_lab_case") else " "
        print(
            f"  {core} #{t['id']:2} [{t.get('expected_path', '?'):12}] "
            f"{t.get('name', t.get('category', ''))}"
        )
    print("\n  ★ = core_lab_case")


def interactive_menu(provider, user: dict | None = None) -> None:
    while True:
        print_menu(user)
        try:
            choice = input("Chọn > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Bye!")
            break

        if choice == "0":
            print("👋 Bye!")
            break
        if choice == "1":
            show_database()
        elif choice == "2":
            list_test_cases()
        elif choice == "3":
            run_core_lab_suite(provider, user=user)
        elif choice == "4":
            list_test_cases()
            try:
                tid = int(input("Nhập test id > ").strip())
            except ValueError:
                print("❌ ID không hợp lệ")
                continue
            match = next((t for t in load_test_cases() if t.get("id") == tid), None)
            if not match:
                print(f"❌ Không tìm thấy test #{tid}")
            else:
                run_test_case(match, provider, compare_both=True, user=user)
        elif choice == "5":
            run_all_tests(provider, user=user)
        elif choice == "6":
            interactive_chat(provider, user)
        elif choice == "7":
            user = choose_user() or user
        else:
            print("❌ Lựa chọn không hợp lệ")


PROVIDER_FLAGS = ("mock", "openai", "gemini", "anthropic", "openrouter")


def resolve_provider():
    """Ưu tiên flag CLI (--mock/--openai/--gemini...); mặc định đọc .env."""
    args = [a.lower().lstrip("-") for a in sys.argv[1:]]
    for name in PROVIDER_FLAGS:
        if name in args:
            return get_llm_provider(name)
    # Local demo: nếu chưa set / lỗi quota → mock vẫn chạy được
    name = (os.getenv("LLM_PROVIDER") or "mock").lower().strip()
    return get_llm_provider(name)


def resolve_user() -> dict | None:
    """Đọc --user=U001 (hoặc --user U001) từ CLI."""
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        low = arg.lower()
        if low.startswith("--user="):
            return login(arg.split("=", 1)[1])
        if low == "--user" and i + 1 < len(args):
            return login(args[i + 1])
    return None


def main() -> None:
    provider = resolve_provider()
    user = resolve_user()
    print_banner(provider)

    # Lọc flag provider + giá trị của --user khỏi argv vị trí
    user_values = set()
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg.lower() == "--user" and i + 1 < len(args):
            user_values.add(args[i + 1])
    positional = [
        a for a in args
        if a.lower().lstrip("-") not in PROVIDER_FLAGS
        and not a.startswith("--")
        and a not in user_values
    ]

    if not positional:
        interactive_menu(provider, user)
        return

    cmd = positional[0].lower()
    if cmd in ("menu", "ui"):
        interactive_menu(provider, user)
    elif cmd == "db":
        show_database()
    elif cmd == "list":
        list_test_cases()
    elif cmd == "login":
        user = choose_user() or user
        interactive_chat(provider, user)
    elif cmd == "core":
        run_core_lab_suite(provider, user=user)
    elif cmd == "all":
        run_all_tests(provider, user=user)
    elif cmd == "chat":
        if user is None:
            user = choose_user()
        interactive_chat(provider, user)
    else:
        try:
            target_id = int(cmd)
        except ValueError:
            print(
                "❌ Dùng: python3 src/app.py "
                "[menu|db|list|login|core|all|chat|<id>] [--mock] [--user U001]"
            )
            return
        match = next((t for t in load_test_cases() if t.get("id") == target_id), None)
        if not match:
            print(f"❌ Không tìm thấy test case id={target_id}")
            return
        run_test_case(match, provider, compare_both=True, user=user)


if __name__ == "__main__":
    main()
