#!/usr/bin/env python3
"""
server_mode.py — JSON-RPC stdio server for the VS Code extension.

Reads newline-delimited JSON-RPC 2.0 requests from stdin,
processes them, and writes responses to stdout.

Methods:
  chat      { message: str }              → { response: str }
  review    { code: str, fileName: str }  → { review: str }
  generate  { feature: str, scriptType: str } → { code: str }
  template  { name: str }                 → { code: str }
  deps      {}                            → { graph: str }
"""

from __future__ import annotations

import json
import os
import sys

from ai_backend import create_backend
from dependency_graph import DependencyGraph
from rojo_manager import RojoProject
from templates import get_template

SYSTEM_PROMPT = """You are an expert Roblox Luau developer. Answer concisely and always
include code examples. When generating scripts, output only the Luau code block."""

_backend = None


def get_backend():
    global _backend
    if _backend is None:
        spec = os.environ.get("ROBLOX_AI_MODEL", "claude-opus-4-6")
        _backend = create_backend(spec)
    return _backend


def _stream_to_str(messages, system=SYSTEM_PROMPT, tools=None):
    from ai_backend import TextDeltaEvent
    text = ""
    for event in get_backend().stream(messages=messages, system=system, tools=tools or []):
        if isinstance(event, TextDeltaEvent):
            text += event.text
    return text


def handle_chat(params: dict) -> dict:
    msg = params.get("message", "")
    response = _stream_to_str([{"role": "user", "content": msg}])
    return {"response": response}


def handle_review(params: dict) -> dict:
    code = params.get("code", "")
    fname = params.get("fileName", "script")
    prompt = f"Review this Roblox Luau script ({fname}) for bugs, security, and performance. Be concise.\n```luau\n{code}\n```"
    response = _stream_to_str([{"role": "user", "content": prompt}])
    return {"review": response}


def handle_generate(params: dict) -> dict:
    feature = params.get("feature", "")
    stype = params.get("scriptType", "ModuleScript")
    prompt = f"Generate a complete Roblox {stype} for: {feature}\nOutput only the Luau code, no explanation."
    response = _stream_to_str([{"role": "user", "content": prompt}])
    # Strip code fences if present
    code = response.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return {"code": code}


def handle_template(params: dict) -> dict:
    t = get_template(params.get("name", ""))
    if not t:
        return {"code": f"-- Template '{params.get('name')}' not found"}
    return {"code": t["code"]}


def handle_deps(params: dict) -> dict:
    rojo = RojoProject.find(os.getcwd())
    if not rojo:
        return {"graph": "No Rojo project found"}
    g = DependencyGraph(rojo)
    g.build()
    # Strip rich markup for plain text output
    import re
    graph = re.sub(r"\[/?[^\]]+\]", "", g.to_ascii())
    return {"graph": graph}


HANDLERS = {
    "chat": handle_chat,
    "review": handle_review,
    "generate": handle_generate,
    "template": handle_template,
    "deps": handle_deps,
}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        handler = HANDLERS.get(method)
        if handler:
            try:
                result = handler(params)
                resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
            except Exception as exc:
                resp = {"jsonrpc": "2.0", "id": req_id, "error": str(exc)}
        else:
            resp = {"jsonrpc": "2.0", "id": req_id, "error": f"Unknown method: {method}"}

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
