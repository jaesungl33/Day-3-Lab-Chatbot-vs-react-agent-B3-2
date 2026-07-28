"""
🌐 CUPID AGENT WEB SERVER (localhost:8000)
Web UI cho demo Chatbot vs ReAct Agent — chỉ dùng stdlib, không cần Flask.
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app import (
    find_profile,
    load_mock_database,
    load_test_cases,
    run_baseline_chatbot,
    run_react_agent,
)
from prompts import MAX_ITERATIONS
from providers import get_llm_provider
from tools import AVAILABLE_TOOLS, TOOL_SCHEMAS

BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BASE_DIR / "web"
HOST = "127.0.0.1"
PORT = int(os.getenv("PORT", "8000"))

_provider_cache: dict[str, object] = {}


def get_provider(name: str):
    """Cache provider theo tên để không khởi tạo lại mỗi request."""
    key = (name or "mock").lower().strip()
    if key not in _provider_cache:
        _provider_cache[key] = get_llm_provider(key)
    return _provider_cache[key]


class CupidServer(ThreadingHTTPServer):
    # Cho phép bind lại ngay sau khi restart, tránh TIME_WAIT giữ cổng.
    allow_reuse_address = True
    daemon_threads = True


class CupidHandler(BaseHTTPRequestHandler):
    server_version = "CupidAgent/1.0"

    def log_message(self, fmt, *args):
        print(f"  [web] {fmt % args}")

    # ---------- helpers ----------
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "Not found"}, 404)
            return
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    # ---------- routes ----------
    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path

        if route == "/api/meta":
            db = load_mock_database()
            provider = get_provider(os.getenv("LLM_PROVIDER", "mock"))
            self._send_json(
                {
                    "provider": provider.__class__.__name__,
                    "model": getattr(provider, "model_name", "offline-mock"),
                    "default_provider": (os.getenv("LLM_PROVIDER") or "mock").lower(),
                    "max_iterations": MAX_ITERATIONS,
                    "tools": sorted(AVAILABLE_TOOLS.keys()),
                    "tool_schemas": TOOL_SCHEMAS,
                    "user_count": len(db.get("profiles", [])),
                    "feedback_count": len(db.get("match_feedback", [])),
                }
            )
            return

        if route == "/api/database":
            self._send_json(load_mock_database())
            return

        if route == "/api/test-cases":
            self._send_json({"test_cases": load_test_cases()})
            return

        # static files
        if route == "/":
            self._send_file(WEB_DIR / "index.html")
            return

        candidate = (WEB_DIR / route.lstrip("/")).resolve()
        if str(candidate).startswith(str(WEB_DIR.resolve())):
            self._send_file(candidate)
        else:
            self._send_json({"error": "Forbidden"}, 403)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        payload = self._read_json()

        try:
            if route == "/api/login":
                self._handle_login(payload)
                return
            if route == "/api/chat":
                self._handle_chat(payload)
                return
            if route == "/api/run-test":
                self._handle_run_test(payload)
                return
            self._send_json({"error": "Not found"}, 404)
        except Exception as exc:
            traceback.print_exc()
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def _handle_login(self, payload: dict) -> None:
        user_id = (payload.get("user_id") or "").strip()
        profile = find_profile(user_id)
        if profile is None:
            self._send_json(
                {"ok": False, "error": f"Không tìm thấy user {user_id or '(trống)'}"}, 404
            )
            return
        print(f"  [auth] đăng nhập: {profile['user_id']} — {profile['display_name']}")
        self._send_json({"ok": True, "user": profile})

    def _handle_chat(self, payload: dict) -> None:
        message = (payload.get("message") or "").strip()
        mode = (payload.get("mode") or "agent").lower()
        provider_name = payload.get("provider") or os.getenv("LLM_PROVIDER") or "mock"
        user = find_profile(payload.get("user_id") or "")

        if not message:
            self._send_json({"error": "message trống"}, 400)
            return

        provider = get_provider(provider_name)
        if mode == "chatbot":
            result = run_baseline_chatbot(message, provider, user)
        elif mode == "both":
            chatbot = run_baseline_chatbot(message, provider, user)
            agent = run_react_agent(message, provider, user)
            self._send_json(
                {
                    "question": message,
                    "mode": "both",
                    "chatbot": chatbot,
                    "agent": agent,
                    "provider": provider.__class__.__name__,
                    "user_id": user["user_id"] if user else None,
                }
            )
            return
        else:
            result = run_react_agent(message, provider, user)

        result["question"] = message
        result["provider"] = provider.__class__.__name__
        result["user_id"] = user["user_id"] if user else None
        self._send_json(result)

    def _handle_run_test(self, payload: dict) -> None:
        test_id = payload.get("id")
        provider_name = payload.get("provider") or os.getenv("LLM_PROVIDER") or "mock"
        tests = load_test_cases()
        test_case = next((t for t in tests if t.get("id") == test_id), None)

        if test_case is None:
            self._send_json({"error": f"Không tìm thấy test #{test_id}"}, 404)
            return

        provider = get_provider(provider_name)
        user = find_profile(payload.get("user_id") or "")
        expected_path = test_case.get("expected_path", "chatbot")
        response: dict = {
            "id": test_id,
            "name": test_case.get("name"),
            "question": test_case["question"],
            "category": test_case.get("category"),
            "expected_path": expected_path,
            "expected_tools": test_case.get("expected_tools", []),
            "success_criteria": test_case.get("success_criteria", []),
            "provider": provider.__class__.__name__,
        }

        response["chatbot"] = run_baseline_chatbot(test_case["question"], provider, user)
        if expected_path in ("react_agent", "hybrid") or payload.get("compare"):
            response["agent"] = run_react_agent(test_case["question"], provider, user)

        response["passed"] = self._evaluate(test_case, response)
        self._send_json(response)

    @staticmethod
    def _evaluate(test_case: dict, result: dict) -> bool:
        """Heuristic pass/fail dựa trên expected_tools và guardrail."""
        expected_tools = test_case.get("expected_tools", [])
        agent = result.get("agent")
        chatbot = result.get("chatbot", {})

        if test_case.get("expected_path") == "chatbot":
            text = chatbot.get("response", "")
            return bool(text) and not text.startswith("[")

        if not agent:
            return False
        if agent.get("guardrail") and expected_tools:
            # Guardrail chấp nhận được với case bẫy
            return "Guardrails" in str(test_case.get("rubric_focus", []))
        called = [e.get("tool") for e in agent.get("events", []) if e["kind"] == "action"]
        if expected_tools:
            return any(t in called for t in expected_tools) or not expected_tools
        return bool(agent.get("response"))


def bind_server(port: int, max_tries: int = 10) -> tuple[CupidServer, int]:
    """Bind vào port; nếu bị chiếm thì thử port kế tiếp thay vì crash."""
    last_error: OSError | None = None
    for offset in range(max_tries):
        candidate = port + offset
        try:
            return CupidServer((HOST, candidate), CupidHandler), candidate
        except OSError as exc:
            if exc.errno not in (48, 98):  # EADDRINUSE (mac / linux)
                raise
            last_error = exc
            print(f"⚠️  Cổng {candidate} đang bị chiếm, thử {candidate + 1}...")
    raise SystemExit(
        f"❌ Không tìm được cổng trống trong khoảng {port}–{port + max_tries - 1}.\n"
        f"   Gợi ý: lsof -ti :{port} | xargs kill   (hoặc PORT=8080 python3 src/server.py)\n"
        f"   Lỗi gốc: {last_error}"
    )


def main() -> None:
    provider_arg = None
    for arg in sys.argv[1:]:
        if arg.startswith("--provider="):
            provider_arg = arg.split("=", 1)[1]
        elif arg in ("--mock", "--gemini", "--openai", "--anthropic", "--openrouter"):
            provider_arg = arg.lstrip("-")
    if provider_arg:
        os.environ["LLM_PROVIDER"] = provider_arg

    provider = get_provider(os.getenv("LLM_PROVIDER", "mock"))
    db = load_mock_database()
    httpd, port = bind_server(PORT)

    print("=" * 60)
    print("💘 CUPID AGENT — WEB DEMO")
    print("=" * 60)
    print(f"🔌 Provider : {provider.__class__.__name__} "
          f"({getattr(provider, 'model_name', 'offline-mock')})")
    print(f"👥 Users    : {len(db.get('profiles', []))}")
    print(f"🛠️  Tools    : {', '.join(sorted(AVAILABLE_TOOLS.keys()))}")
    print(f"🛡️  Guardrail: MAX_ITERATIONS={MAX_ITERATIONS}")
    print(f"\n🚀 Mở trình duyệt: http://localhost:{port}\n")
    print("   (Ctrl+C để dừng)")
    print("=" * 60, flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Đã dừng server.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
