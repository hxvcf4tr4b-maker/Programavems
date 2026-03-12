"""
web_server.py — WebSocket + HTTP server for the Roblox AI Dev Tool web UI.

Run with:  python web_server.py  (or roblox-dev-tool --web)

Endpoints:
  GET  /              → serves the web UI (static files from web/out/)
  POST /api/chat      → streaming AI chat (Server-Sent Events)
  POST /api/generate  → generate a Luau script
  POST /api/review    → review a Luau script
  POST /rpc           → JSON-RPC 2.0 (Studio plugin compat)
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from ai_backend import TextDeltaEvent, create_backend
from templates import get_template

SYSTEM_PROMPT = (
    "You are an expert Roblox Luau developer. "
    "Be concise, helpful, and always include code examples when relevant."
)

_backend = None


def get_backend():
    global _backend
    if _backend is None:
        spec = os.environ.get("ROBLOX_AI_MODEL", "claude-opus-4-6")
        _backend = create_backend(spec)
    return _backend


def _stream_to_str(messages) -> str:
    text = ""
    for event in get_backend().stream(messages=messages, system=SYSTEM_PROMPT, tools=[]):
        if isinstance(event, TextDeltaEvent):
            text += event.text
    return text


WEB_DIR = Path(__file__).parent / "web" / "out"


class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {self.command} {self.path}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        # Serve static web UI
        path = self.path.split("?")[0]
        if path == "/":
            path = "/index.html"

        file_path = WEB_DIR / path.lstrip("/")

        # Try .html extension fallback
        if not file_path.exists() and not path.endswith(".html"):
            file_path = WEB_DIR / (path.lstrip("/") + ".html")

        if file_path.exists() and file_path.is_file():
            mime, _ = mimetypes.guess_type(str(file_path))
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime or "text/plain")
            self.send_header("Content-Length", str(len(data)))
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        else:
            # SPA fallback → index.html
            index = WEB_DIR / "index.html"
            if index.exists():
                data = index.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(data)))
                self._cors()
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404, "Web UI not built. Run: cd web && npm run build")

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        return json.loads(body) if body else {}

    def _json_response(self, data: dict, status: int = 200):
        encoded = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self._cors()
        self.end_headers()
        self.wfile.write(encoded)

    def _sse_stream(self, messages: list):
        """Stream response as Server-Sent Events."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self._cors()
        self.end_headers()

        try:
            for event in get_backend().stream(messages=messages, system=SYSTEM_PROMPT, tools=[]):
                if isinstance(event, TextDeltaEvent):
                    data = json.dumps({"delta": event.text})
                    chunk = f"data: {data}\n\n".encode()
                    self.wfile.write(chunk)
                    self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        path = self.path.split("?")[0]

        # ── SSE streaming chat ────────────────────────────────────────────────
        if path == "/api/chat":
            body = self._read_body()
            messages = body.get("messages", [])
            if not messages:
                msg = body.get("message", "")
                messages = [{"role": "user", "content": msg}]
            self._sse_stream(messages)
            return

        # ── Generate script ───────────────────────────────────────────────────
        if path == "/api/generate":
            body = self._read_body()
            feature = body.get("feature", "")
            stype = body.get("scriptType", "ModuleScript")
            prompt = f"Generate a complete Roblox {stype} for: {feature}\nOutput ONLY the Luau code."
            code = _stream_to_str([{"role": "user", "content": prompt}]).strip()
            if code.startswith("```"):
                lines = code.split("\n")
                code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            self._json_response({"code": code, "scriptType": stype})
            return

        # ── Review script ─────────────────────────────────────────────────────
        if path == "/api/review":
            body = self._read_body()
            code = body.get("code", "")
            fname = body.get("fileName", "script.luau")
            prompt = (
                f"Review this Roblox Luau script ({fname}) for bugs, security issues, "
                f"and performance. Be concise.\n```luau\n{code}\n```"
            )
            review = _stream_to_str([{"role": "user", "content": prompt}])
            self._json_response({"review": review})
            return

        # ── Templates list ────────────────────────────────────────────────────
        if path == "/api/templates":
            from templates import TEMPLATES
            names = list(TEMPLATES.keys()) if hasattr(__import__("templates"), "TEMPLATES") else []
            self._json_response({"templates": names})
            return

        # ── Studio plugin RPC (backward compat) ───────────────────────────────
        if path == "/rpc":
            body = self._read_body()
            method = body.get("method", "")
            params = body.get("params", {})
            req_id = body.get("id")

            rpc_handlers = {
                "chat": lambda p: {"response": _stream_to_str([{"role": "user", "content": p.get("message", "")}])},
                "review": lambda p: {"review": _stream_to_str([{"role": "user", "content": f"Review: ```luau\n{p.get('code','')}\n```"}])},
                "generate": lambda p: self._rpc_generate(p),
                "template": lambda p: get_template(p.get("name", "")) or {"code": "-- not found"},
            }
            fn = rpc_handlers.get(method)
            if fn:
                try:
                    result = fn(params)
                    self._json_response({"jsonrpc": "2.0", "id": req_id, "result": result})
                except Exception as exc:
                    self._json_response({"jsonrpc": "2.0", "id": req_id, "error": str(exc)})
            else:
                self._json_response({"jsonrpc": "2.0", "id": req_id, "error": f"Unknown method: {method}"})
            return

        self.send_error(404)

    def _rpc_generate(self, params: dict) -> dict:
        feature = params.get("feature", "")
        stype = params.get("scriptType", "ModuleScript")
        prompt = f"Generate a complete Roblox {stype} for: {feature}\nOutput ONLY the Luau code."
        code = _stream_to_str([{"role": "user", "content": prompt}]).strip()
        if code.startswith("```"):
            lines = code.split("\n")
            code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return {"code": code, "scriptType": stype}


def run_server(port: int = 8765) -> None:
    model = os.environ.get("ROBLOX_AI_MODEL", "claude-opus-4-6")
    print(f"[RobloxAI] Web server running at http://localhost:{port}")
    print(f"[RobloxAI] Model: {model}")
    print(f"[RobloxAI] Open your browser at http://localhost:{port}")
    print("[RobloxAI] Press Ctrl-C to stop.\n")
    server = HTTPServer(("0.0.0.0", port), WebHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[RobloxAI] Server stopped.")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    run_server(port)
