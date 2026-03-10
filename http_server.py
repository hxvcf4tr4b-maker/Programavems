"""
http_server.py — Local HTTP bridge for the Roblox Studio plugin.

Run with:  roblox-dev-tool --serve [--port 8765]
Or:        python http_server.py

Exposes one endpoint:  POST /rpc   (JSON-RPC 2.0)

The Studio plugin calls this endpoint since it can only make HTTP requests,
not spawn subprocesses.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from ai_backend import create_backend
from dependency_graph import DependencyGraph
from rojo_manager import RojoProject
from templates import get_template

_backend = None
SYSTEM_PROMPT = "You are an expert Roblox Luau developer. Be concise and include code examples."


def get_backend():
    global _backend
    if _backend is None:
        spec = os.environ.get("ROBLOX_AI_MODEL", "claude-opus-4-6")
        _backend = create_backend(spec)
    return _backend


def _stream_to_str(messages) -> str:
    from ai_backend import TextDeltaEvent
    text = ""
    for event in get_backend().stream(messages=messages, system=SYSTEM_PROMPT, tools=[]):
        if isinstance(event, TextDeltaEvent):
            text += event.text
    return text


HANDLERS: dict[str, Any] = {}


def handler(method: str):
    def decorator(fn):
        HANDLERS[method] = fn
        return fn
    return decorator


@handler("chat")
def _chat(params: dict) -> dict:
    msg = params.get("message", "")
    response = _stream_to_str([{"role": "user", "content": msg}])
    return {"response": response}


@handler("review")
def _review(params: dict) -> dict:
    code = params.get("code", "")
    fname = params.get("fileName", "script")
    prompt = f"Review this Roblox Luau script ({fname}) for bugs, security issues, and performance. Be concise.\n```luau\n{code}\n```"
    response = _stream_to_str([{"role": "user", "content": prompt}])
    return {"review": response}


@handler("generate")
def _generate(params: dict) -> dict:
    feature = params.get("feature", "")
    stype = params.get("scriptType", "ModuleScript")
    prompt = f"Generate a complete Roblox {stype} for: {feature}\nOutput ONLY the Luau code."
    response = _stream_to_str([{"role": "user", "content": prompt}])
    code = response.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return {"code": code, "scriptType": stype}


@handler("template")
def _template(params: dict) -> dict:
    t = get_template(params.get("name", ""))
    if not t:
        return {"code": f"-- Template '{params.get('name')}' not found", "scriptType": "ModuleScript"}
    return {"code": t["code"], "scriptType": t["type"]}


@handler("deps")
def _deps(params: dict) -> dict:
    import re
    rojo = RojoProject.find(os.getcwd())
    if not rojo:
        return {"graph": "No Rojo project found"}
    g = DependencyGraph(rojo)
    g.build()
    graph = re.sub(r"\[/?[^\]]+\]", "", g.to_ascii())
    return {"graph": graph}


# ── HTTP handler ──────────────────────────────────────────────────────────────


class RpcHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def do_POST(self):
        if self.path != "/rpc":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # CORS
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        fn = HANDLERS.get(method)
        if fn:
            try:
                result = fn(params)
                resp_body = json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result})
            except Exception as exc:
                resp_body = json.dumps({"jsonrpc": "2.0", "id": req_id, "error": str(exc)})
        else:
            resp_body = json.dumps({"jsonrpc": "2.0", "id": req_id, "error": f"Unknown method: {method}"})

        encoded = resp_body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        self.end_headers()


def run_server(port: int = 8765) -> None:
    server = HTTPServer(("localhost", port), RpcHandler)
    print(f"[RobloxAI] HTTP bridge running at http://localhost:{port}/rpc")
    print(f"[RobloxAI] Model: {os.environ.get('ROBLOX_AI_MODEL', 'claude-opus-4-6')}")
    print("[RobloxAI] Studio plugin can now connect. Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[RobloxAI] Server stopped.")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    run_server(port)
