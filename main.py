#!/usr/bin/env python3
"""
Roblox AI Dev Tool — powered by any AI model
Helps you build, debug, and architect Roblox game servers.

Usage:
  roblox-dev-tool                            # auto-detects Rojo project, uses Claude
  roblox-dev-tool --model openai:gpt-4o      # use GPT-4o
  roblox-dev-tool --model groq:llama-3.3-70b-versatile
  roblox-dev-tool --model ollama:llama3      # local Ollama
  roblox-dev-tool --model gemini:gemini-2.0-flash-exp
  roblox-dev-tool --project ./my-game        # specify Rojo project directory
  roblox-dev-tool --new-project MyGame       # scaffold a new Rojo project
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.theme import Theme

from ai_backend import AIBackend, StreamEndEvent, TextDeltaEvent, ToolCompleteEvent, ToolStartEvent, create_backend, list_providers
from dependency_graph import DependencyGraph
from git_manager import GitManager
from open_cloud import OpenCloudClient, OpenCloudError
from rojo_manager import RojoProject
from selene_linter import format_issues, lint_code, selene_available
from templates import get_template, list_templates, search_templates
from watch_mode import FileWatcher

# ─── Console ──────────────────────────────────────────────────────────────────

custom_theme = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "bold red",
        "tool": "bold magenta",
        "roblox": "bold bright_red",
    }
)
console = Console(theme=custom_theme)

# ─── App state ────────────────────────────────────────────────────────────────

APP_STATE: dict[str, Any] = {
    "backend": None,         # AIBackend
    "rojo": None,            # Optional[RojoProject]
    "last_script": None,     # last generated script info
    "watcher": None,         # Optional[FileWatcher]
    "auto_commit": False,    # auto-commit saved scripts
    "auto_lint": True,       # lint generated scripts with selene
    "git": None,             # Optional[GitManager]
    "cloud": None,           # Optional[OpenCloudClient]
}

# ─── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Roblox game server developer and architect. You specialize in:

**Languages & Runtime**
- Luau (Roblox's typed Lua dialect): strict/strong typing, generics, type-checking
- Server Scripts (Script), Local Scripts (LocalScript), Module Scripts (ModuleScript)
- Roblox's execution model: server authority, client-server boundary

**Core Roblox Services**
- Players, Workspace, ReplicatedStorage, ServerStorage, ServerScriptService
- DataStoreService, MessagingService, MemoryStoreService
- RunService (Heartbeat, Stepped, RenderStepped), TweenService
- HttpService, MarketplaceService, BadgeService, PhysicsService, Teams

**Networking & Security**
- RemoteEvent and RemoteFunction (server↔client communication)
- Always validate on the server — never trust the client
- Rate limiting, anti-exploit techniques, sanity checks

**Data & State**
- DataStoreService: ordered/standard DataStores, retries, budgets
- MemoryStoreService: fast ephemeral data (leaderboards, queues)
- Auto-saving patterns, data migration, session locking

**Best Practices**
- Module pattern, OOP with metatables or Luau classes
- Error handling with pcall/xpcall
- Proper cleanup (Connections, Instances) to avoid memory leaks
- Signal patterns

When generating code:
1. Write idiomatic Luau with type annotations
2. Include server-side validation for any client input
3. Handle errors gracefully with pcall
4. Follow Roblox naming conventions
5. Specify whether code goes in Script, LocalScript, or ModuleScript
6. Mention where files should be placed in the Explorer hierarchy"""

# ─── Tools ────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "generate_script",
        "description": "Generate a complete, ready-to-use Roblox Luau script.",
        "input_schema": {
            "type": "object",
            "properties": {
                "script_type": {"type": "string", "enum": ["Script", "LocalScript", "ModuleScript"]},
                "feature": {"type": "string"},
                "placement": {"type": "string"},
                "code": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["script_type", "feature", "placement", "code"],
        },
    },
    {
        "name": "review_script",
        "description": "Review a Roblox Luau script for bugs, security, and performance issues.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"type": "string", "enum": ["critical", "warning", "suggestion"]},
                            "line_hint": {"type": "string"},
                            "description": {"type": "string"},
                            "fix": {"type": "string"},
                        },
                        "required": ["severity", "description", "fix"],
                    },
                },
                "summary": {"type": "string"},
                "improved_code": {"type": "string"},
            },
            "required": ["issues", "summary"],
        },
    },
    {
        "name": "suggest_architecture",
        "description": "Design a Roblox server architecture with components, data flow, and implementation plan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "components": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string", "enum": ["Script", "LocalScript", "ModuleScript", "RemoteEvent", "RemoteFunction", "DataStore", "Folder", "Other"]},
                            "location": {"type": "string"},
                            "purpose": {"type": "string"},
                        },
                        "required": ["name", "type", "location", "purpose"],
                    },
                },
                "data_flow": {"type": "string"},
                "implementation_steps": {"type": "array", "items": {"type": "string"}},
                "security_notes": {"type": "string"},
            },
            "required": ["title", "components", "data_flow", "implementation_steps"],
        },
    },
    {
        "name": "generate_datastore",
        "description": "Generate a complete DataStore module with auto-save and session locking.",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_name": {"type": "string"},
                "data_schema": {"type": "object"},
                "auto_save_interval": {"type": "integer"},
                "code": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["store_name", "data_schema", "code"],
        },
    },
    {
        "name": "generate_remote_events",
        "description": "Generate RemoteEvent/RemoteFunction setup with server-side validation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "feature": {"type": "string"},
                "remotes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "remote_type": {"type": "string", "enum": ["RemoteEvent", "RemoteFunction"]},
                            "direction": {"type": "string", "enum": ["client_to_server", "server_to_client", "bidirectional"]},
                            "parameters": {"type": "string"},
                        },
                        "required": ["name", "remote_type", "direction"],
                    },
                },
                "server_code": {"type": "string"},
                "client_code": {"type": "string"},
            },
            "required": ["feature", "remotes", "server_code", "client_code"],
        },
    },
    {
        "name": "generate_tests",
        "description": "Generate TestEZ unit tests for a Roblox ModuleScript.",
        "input_schema": {
            "type": "object",
            "properties": {
                "module_name": {"type": "string"},
                "test_code": {"type": "string"},
                "placement": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["module_name", "test_code", "placement"],
        },
    },
]

# ─── Tool renderers ───────────────────────────────────────────────────────────


def _auto_lint_and_save(code: str, script_type: str, feature: str, placement: str) -> str | None:
    """Run selene lint, optionally save to Rojo project. Returns saved path or None."""
    # Lint
    if APP_STATE["auto_lint"] and selene_available():
        issues = lint_code(code, script_type)
        if issues:
            console.print(f"\n[warning]Selene found {len(issues)} issue(s):[/warning]")
            console.print(format_issues(issues))

    # Save to Rojo
    rojo: RojoProject | None = APP_STATE.get("rojo")
    if not rojo:
        return None
    try:
        if Confirm.ask(
            f"\n[cyan]Save to Rojo project '[bold]{rojo.name}[/bold]'?[/cyan]",
            default=True,
        ):
            default_name = feature.replace(" ", "").replace("/", "")[:30]
            name = Prompt.ask("[cyan]Filename (no extension)[/cyan]", default=default_name)
            saved = rojo.save_script(script_type, placement, name, code)
            console.print(f"[success]✔ Saved →[/success] {saved}")

            # Auto-commit
            if APP_STATE["auto_commit"] and APP_STATE["git"]:
                ok, msg = APP_STATE["git"].auto_commit(
                    APP_STATE["backend"], [saved], context=feature
                )
                if ok:
                    console.print(f"[success]✔ Committed:[/success] {msg}")
            return str(saved)
    except Exception as exc:
        console.print(f"[error]Save failed:[/error] {exc}")
    return None


def render_generate_script(data: dict) -> None:
    APP_STATE["last_script"] = data
    console.print(
        Panel(
            f"[bold]{data['script_type']}[/bold] — {data['feature']}\n"
            f"[dim]Place in:[/dim] [cyan]{data['placement']}[/cyan]",
            title="[tool]Generated Script[/tool]",
            border_style="magenta",
        )
    )
    console.print(Syntax(data["code"], "lua", theme="monokai", line_numbers=True))
    if data.get("notes"):
        console.print(Panel(Markdown(data["notes"]), title="Setup Notes", border_style="dim"))
    _auto_lint_and_save(data["code"], data["script_type"], data["feature"], data["placement"])


def render_review_script(data: dict) -> None:
    sev_color = {"critical": "bold red", "warning": "yellow", "suggestion": "cyan"}
    sev_icon = {"critical": "✖", "warning": "⚠", "suggestion": "➤"}
    console.print(Panel(data.get("summary", ""), title="[tool]Code Review[/tool]", border_style="magenta"))
    for iss in data.get("issues", []):
        sev = iss.get("severity", "suggestion")
        ln = f" (line {iss['line_hint']})" if iss.get("line_hint") else ""
        console.print(
            f"  [{sev_color.get(sev, 'white')}]{sev_icon.get(sev, '•')} [{sev.upper()}]{ln}[/{sev_color.get(sev, 'white')}] {iss['description']}"
        )
        console.print(f"    [dim]Fix:[/dim] {iss['fix']}\n")
    if data.get("improved_code"):
        console.print(Panel("[bold]Improved Code[/bold]", border_style="green"))
        console.print(Syntax(data["improved_code"], "lua", theme="monokai", line_numbers=True))
        APP_STATE["last_script"] = {**data, "code": data["improved_code"], "script_type": "ModuleScript", "placement": "ReplicatedStorage"}


def render_suggest_architecture(data: dict) -> None:
    type_icons = {"Script": "📜", "LocalScript": "💻", "ModuleScript": "📦", "RemoteEvent": "📡", "RemoteFunction": "🔄", "DataStore": "🗄", "Folder": "📁", "Other": "🔧"}
    console.print(Panel(f"[bold]{data.get('title', '')}[/bold]", title="[tool]Architecture[/tool]", border_style="magenta"))
    tbl = Table(show_header=True, header_style="bold cyan", border_style="dim")
    tbl.add_column("Component"); tbl.add_column("Type"); tbl.add_column("Location"); tbl.add_column("Purpose")
    for c in data.get("components", []):
        tbl.add_row(f"{type_icons.get(c.get('type','Other'),'🔧')} {c['name']}", c.get("type",""), c.get("location",""), c.get("purpose",""))
    console.print(tbl)
    console.print(f"\n[bold]Data Flow:[/bold]\n{data.get('data_flow', '')}\n")
    if data.get("implementation_steps"):
        console.print("[bold]Implementation Order:[/bold]")
        for i, s in enumerate(data["implementation_steps"], 1):
            console.print(f"  {i}. {s}")
    if data.get("security_notes"):
        console.print(Panel(data["security_notes"], title="Security Notes", border_style="yellow"))


def render_generate_datastore(data: dict) -> None:
    APP_STATE["last_script"] = {**data, "script_type": "ModuleScript", "feature": data["store_name"], "placement": "ServerScriptService"}
    console.print(Panel(
        f"[bold]DataStore:[/bold] [cyan]{data.get('store_name', '')}[/cyan]\n"
        f"[dim]Schema:[/dim] {json.dumps(data.get('data_schema', {}), indent=2)}",
        title="[tool]DataStore Module[/tool]", border_style="magenta"
    ))
    console.print(Syntax(data.get("code", ""), "lua", theme="monokai", line_numbers=True))
    if data.get("notes"):
        console.print(Panel(Markdown(data["notes"]), title="Setup Notes", border_style="dim"))
    _auto_lint_and_save(data["code"], "ModuleScript", data["store_name"], "ServerScriptService")


def render_generate_remote_events(data: dict) -> None:
    dir_labels = {"client_to_server": "Client → Server", "server_to_client": "Server → Client", "bidirectional": "↔ Bidirectional"}
    console.print(Panel(f"[bold]Remote Events for:[/bold] {data.get('feature', '')}", title="[tool]Remote Events[/tool]", border_style="magenta"))
    tbl = Table(show_header=True, header_style="bold cyan", border_style="dim")
    tbl.add_column("Name"); tbl.add_column("Type"); tbl.add_column("Direction"); tbl.add_column("Parameters")
    for r in data.get("remotes", []):
        tbl.add_row(r["name"], r["remote_type"], dir_labels.get(r.get("direction", ""), ""), r.get("parameters", "—"))
    console.print(tbl)
    console.print("\n[bold]Server Handler:[/bold]")
    console.print(Syntax(data.get("server_code", ""), "lua", theme="monokai", line_numbers=True))
    console.print("\n[bold]Client Usage:[/bold]")
    console.print(Syntax(data.get("client_code", ""), "lua", theme="monokai", line_numbers=True))
    rojo = APP_STATE.get("rojo")
    if rojo:
        try:
            if Confirm.ask(f"\n[cyan]Save both scripts to Rojo project?[/cyan]", default=True):
                base = Prompt.ask("[cyan]Base filename[/cyan]", default=data.get("feature", "").replace(" ", "")[:20])
                s = rojo.save_script("Script", "ServerScriptService", f"{base}Handler", data.get("server_code", ""))
                c = rojo.save_script("LocalScript", "StarterPlayerScripts", f"{base}Client", data.get("client_code", ""))
                console.print(f"[success]✔[/success] {s}\n[success]✔[/success] {c}")
        except Exception as exc:
            console.print(f"[error]{exc}[/error]")


def render_generate_tests(data: dict) -> None:
    APP_STATE["last_script"] = {**data, "script_type": "ModuleScript", "feature": f"{data['module_name']} tests", "placement": data.get("placement", "ReplicatedStorage")}
    console.print(Panel(f"[bold]TestEZ Tests for:[/bold] [cyan]{data.get('module_name', '')}[/cyan]", title="[tool]TestEZ Tests[/tool]", border_style="magenta"))
    console.print(Syntax(data.get("test_code", ""), "lua", theme="monokai", line_numbers=True))
    if data.get("notes"):
        console.print(Panel(Markdown(data["notes"]), title="Setup Notes", border_style="dim"))
    _auto_lint_and_save(data["test_code"], "ModuleScript", f"{data['module_name']}_spec", data.get("placement", "ReplicatedStorage"))


TOOL_RENDERERS = {
    "generate_script": render_generate_script,
    "review_script": render_review_script,
    "suggest_architecture": render_suggest_architecture,
    "generate_datastore": render_generate_datastore,
    "generate_remote_events": render_generate_remote_events,
    "generate_tests": render_generate_tests,
}


def execute_tool(tool_name: str, tool_input: dict) -> str:
    renderer = TOOL_RENDERERS.get(tool_name)
    if renderer:
        renderer(tool_input)
    return json.dumps({"status": "displayed", "tool": tool_name})


# ─── Slash command handlers ───────────────────────────────────────────────────


def cmd_help() -> None:
    console.print(Panel(
        "[bold]Chat Commands:[/bold]\n"
        "  [cyan]/help[/cyan]                    Show this help\n"
        "  [cyan]/clear[/cyan]                   Clear conversation history\n"
        "  [cyan]/model [spec][/cyan]            Switch AI model (e.g. openai:gpt-4o)\n"
        "  [cyan]/models[/cyan]                  List all configured providers\n"
        "  [cyan]/rojo[/cyan]                    Show Rojo project status\n"
        "  [cyan]/new-project <name>[/cyan]       Scaffold a new Rojo project\n"
        "  [cyan]/save [name][/cyan]             Save last script to Rojo project\n"
        "  [cyan]/read <path>[/cyan]             Load script into conversation\n"
        "  [cyan]/list[/cyan]                    List all scripts in project\n"
        "  [cyan]/deps[/cyan]                    Show require() dependency graph\n"
        "  [cyan]/watch[/cyan]                   Start/stop auto-review on file changes\n"
        "  [cyan]/templates[/cyan]               Browse built-in code templates\n"
        "  [cyan]/templates <query>[/cyan]        Search templates\n"
        "  [cyan]/template <name>[/cyan]         Insert a template into the project\n"
        "  [cyan]/cloud-info[/cyan]              Show Roblox Open Cloud universe info\n"
        "  [cyan]/cloud-read <store> <key>[/cyan] Read a DataStore entry\n"
        "  [cyan]/cloud-list <store>[/cyan]       List DataStore keys\n"
        "  [cyan]/autocommit [on|off][/cyan]      Toggle git auto-commit after saves\n"
        "  [cyan]/lint [on|off][/cyan]            Toggle selene auto-lint\n"
        "  [cyan]/upgrades[/cyan]                Show upgrade roadmap\n"
        "  [cyan]/quit[/cyan]                    Exit\n\n"
        "[bold]Example prompts:[/bold]\n"
        "  • Generate a round system with lobby, game, and intermission states\n"
        "  • Create a DataStore module for saving coins, level, and inventory\n"
        "  • Design the architecture for a player trading system\n"
        "  • Set up RemoteEvents for a shop — make it exploit-proof\n"
        "  • Generate TestEZ tests for my DataManager module\n"
        "  • Review this script: [paste code]\n"
        "  • Generate a pathfinding NPC with aggro range",
        title="Help", border_style="cyan"
    ))


def cmd_models() -> None:
    current: AIBackend | None = APP_STATE.get("backend")
    tbl = Table(show_header=True, header_style="bold cyan", border_style="dim")
    tbl.add_column("Provider"); tbl.add_column("Status"); tbl.add_column("Env Var"); tbl.add_column("Example Models")
    for p in list_providers():
        configured = "[success]✔ ready[/success]" if p["configured"] else "[dim]not configured[/dim]"
        active = " [bold bright_red]← current[/bold bright_red]" if current and current.provider == p["provider"] else ""
        tbl.add_row(p["provider"] + active, configured, p["env_var"] or "none", p["models"])
    console.print(Panel(tbl, title=f"AI Models  (current: [bold]{current}[/bold])", border_style="cyan"))
    console.print("\n[dim]Switch with: /model <provider>:<model_id>   e.g.  /model openai:gpt-4o[/dim]")


def cmd_switch_model(spec: str, messages: list[dict]) -> None:
    if not spec:
        cmd_models()
        return
    try:
        new_backend = create_backend(spec)
        APP_STATE["backend"] = new_backend
        messages.clear()
        console.print(f"[success]✔ Switched to:[/success] [bold]{new_backend}[/bold]  (history cleared)")
    except Exception as exc:
        console.print(f"[error]Could not create backend '{spec}':[/error] {exc}")


def cmd_rojo() -> None:
    rojo: RojoProject | None = APP_STATE.get("rojo")
    if not rojo:
        console.print(Panel("[warning]No Rojo project detected.[/warning]\nRun [cyan]/new-project <name>[/cyan] to scaffold one.", title="Rojo Status", border_style="yellow"))
        return
    summary = rojo.summary()
    scripts = summary["scripts"]
    tbl = Table(show_header=True, header_style="bold cyan", border_style="dim", title="Scripts")
    tbl.add_column("#", width=4); tbl.add_column("Path"); tbl.add_column("Type"); tbl.add_column("Lines", justify="right")
    for i, s in enumerate(scripts, 1):
        tbl.add_row(str(i), s["path"], s["type"], str(s["size_lines"]))
    console.print(Panel(f"[bold]Project:[/bold] {summary['name']}\n[bold]Directory:[/bold] [cyan]{summary['project_dir']}[/cyan]\n[bold]Scripts:[/bold] {summary['script_count']}", title="[success]Rojo Connected[/success]", border_style="green"))
    if scripts:
        console.print(tbl)


def cmd_save(args: str, messages: list[dict]) -> None:
    rojo = APP_STATE.get("rojo")
    last = APP_STATE.get("last_script")
    if not rojo:
        console.print("[warning]No Rojo project connected. Use /new-project first.[/warning]"); return
    if not last:
        console.print("[warning]No script generated yet.[/warning]"); return
    name = args.strip() or Prompt.ask("[cyan]Filename[/cyan]", default=last.get("feature", "Script").replace(" ", "")[:30])
    try:
        saved = rojo.save_script(last["script_type"], last["placement"], name, last["code"])
        console.print(f"[success]✔ Saved →[/success] {saved}")
    except Exception as exc:
        console.print(f"[error]{exc}[/error]")


def cmd_read(path_arg: str, messages: list[dict]) -> None:
    rojo = APP_STATE.get("rojo")
    if not path_arg:
        console.print("[warning]Usage: /read <path>[/warning]"); return
    try:
        code = rojo.read_script(path_arg) if rojo else open(path_arg, encoding="utf-8").read()
        console.print(Panel(f"[dim]{path_arg}[/dim]", border_style="dim"))
        console.print(Syntax(code, "lua", theme="monokai", line_numbers=True))
        messages.append({"role": "user", "content": f"Here is the script at `{path_arg}`:\n```luau\n{code}\n```"})
        messages.append({"role": "assistant", "content": f"Got it — I've loaded `{path_arg}` ({len(code.splitlines())} lines). What would you like me to do with it?"})
        console.print("[dim]Script loaded into conversation.[/dim]")
    except FileNotFoundError:
        console.print(f"[error]File not found:[/error] {path_arg}")
    except Exception as exc:
        console.print(f"[error]{exc}[/error]")


def cmd_deps() -> None:
    rojo = APP_STATE.get("rojo")
    if not rojo:
        console.print("[warning]No Rojo project connected.[/warning]"); return
    g = DependencyGraph(rojo)
    g.build()
    cycles = g.find_cycles()
    console.print(Panel(f"[bold]Dependency Graph — {rojo.name}[/bold]\n{g.summary()}", border_style="cyan"))
    console.print(g.to_ascii())
    if cycles:
        console.print(f"\n[error]Circular dependencies detected:[/error]")
        for cycle in cycles:
            console.print(f"  [red]⟳[/red] {' → '.join(cycle)}")


def cmd_watch(args: str) -> None:
    rojo = APP_STATE.get("rojo")
    backend = APP_STATE.get("backend")
    if not rojo or not backend:
        console.print("[warning]Needs a Rojo project and AI model. Use /rojo and check /models.[/warning]"); return
    watcher: FileWatcher | None = APP_STATE.get("watcher")
    if args.lower() in ("off", "stop", "0"):
        if watcher:
            watcher.stop()
            APP_STATE["watcher"] = None
        return
    if watcher and watcher.is_running:
        console.print("[dim]Watch mode is already running. Use /watch off to stop.[/dim]"); return
    w = FileWatcher(rojo, backend, console)
    if w.start():
        APP_STATE["watcher"] = w


def cmd_templates(query: str) -> None:
    if query:
        results = search_templates(query)
        if not results:
            console.print(f"[warning]No templates matching '{query}'.[/warning]"); return
    else:
        results = list_templates()
    tbl = Table(show_header=True, header_style="bold cyan", border_style="dim")
    tbl.add_column("Name"); tbl.add_column("Title"); tbl.add_column("Type"); tbl.add_column("Description")
    for t in results:
        tbl.add_row(f"[cyan]{t['name']}[/cyan]", t["title"], t["type"], t["description"])
    console.print(Panel(tbl, title="Templates  (use /template <name> to insert)", border_style="cyan"))


def cmd_template_insert(name: str) -> None:
    t = get_template(name)
    if not t:
        console.print(f"[error]Template '{name}' not found. Use /templates to list.[/error]"); return
    console.print(Panel(f"[bold]{t['title']}[/bold] ({t['type']})\n[dim]Placement: {t['placement']}[/dim]", title="[tool]Template[/tool]", border_style="magenta"))
    console.print(Syntax(t["code"], "lua", theme="monokai", line_numbers=True))
    APP_STATE["last_script"] = {"script_type": t["type"], "feature": t["title"], "placement": t["placement"], "code": t["code"]}
    rojo = APP_STATE.get("rojo")
    if rojo:
        try:
            if Confirm.ask(f"[cyan]Save to Rojo project?[/cyan]", default=True):
                saved = rojo.save_script(t["type"], t["placement"], t["name"], t["code"])
                console.print(f"[success]✔ Saved →[/success] {saved}")
        except Exception as exc:
            console.print(f"[error]{exc}[/error]")


def cmd_cloud_info() -> None:
    cloud = APP_STATE.get("cloud")
    if not cloud or not cloud.is_configured():
        console.print(Panel("[warning]Open Cloud not configured.[/warning]\nSet env vars:\n  [cyan]ROBLOX_OPEN_CLOUD_KEY[/cyan]\n  [cyan]ROBLOX_UNIVERSE_ID[/cyan]", title="Open Cloud", border_style="yellow")); return
    try:
        info = cloud.get_universe()
        console.print(Panel(json.dumps(info, indent=2), title="[tool]Universe Info[/tool]", border_style="cyan"))
    except OpenCloudError as e:
        console.print(f"[error]Open Cloud error:[/error] {e}")


def cmd_cloud_read(args: str) -> None:
    cloud = APP_STATE.get("cloud")
    if not cloud or not cloud.is_configured():
        console.print("[warning]Open Cloud not configured. See /cloud-info.[/warning]"); return
    parts = args.split(None, 1)
    if len(parts) < 2:
        console.print("[warning]Usage: /cloud-read <datastore> <key>[/warning]"); return
    try:
        value, meta = cloud.get_entry(parts[0], parts[1])
        console.print(Panel(json.dumps({"value": value, "metadata": meta}, indent=2), title=f"[tool]DataStore: {parts[0]} / {parts[1]}[/tool]", border_style="cyan"))
    except OpenCloudError as e:
        console.print(f"[error]{e}[/error]")


def cmd_cloud_list(args: str) -> None:
    cloud = APP_STATE.get("cloud")
    if not cloud or not cloud.is_configured():
        console.print("[warning]Open Cloud not configured. See /cloud-info.[/warning]"); return
    if not args.strip():
        console.print("[warning]Usage: /cloud-list <datastore>[/warning]"); return
    try:
        result = cloud.list_entries(args.strip())
        keys = result.get("keys", [])
        tbl = Table(show_header=True, border_style="dim")
        tbl.add_column("Key"); tbl.add_column("Scope")
        for entry in keys:
            tbl.add_row(entry.get("key", ""), entry.get("scope", "global"))
        console.print(Panel(tbl, title=f"[tool]Keys in '{args.strip()}'[/tool]", border_style="cyan"))
    except OpenCloudError as e:
        console.print(f"[error]{e}[/error]")


def cmd_new_project(name: str) -> None:
    if not name:
        name = Prompt.ask("[cyan]Project name[/cyan]", default="MyGame")
    dest = Prompt.ask("[cyan]Directory[/cyan]", default=os.getcwd())
    try:
        proj = RojoProject.create(dest, name)
        APP_STATE["rojo"] = proj
        APP_STATE["git"] = GitManager(dest)
        console.print(Panel(f"[bold]Created:[/bold] [cyan]{name}[/cyan]\n[dim]{proj.project_dir}[/dim]\n\nRun [bold]rojo serve[/bold] to start syncing with Studio.", title="[success]Rojo Project Created[/success]", border_style="green"))
    except Exception as exc:
        console.print(f"[error]{exc}[/error]")


def cmd_autocommit(args: str) -> None:
    if args.lower() in ("on", "1", "yes", "true"):
        APP_STATE["auto_commit"] = True
    elif args.lower() in ("off", "0", "no", "false"):
        APP_STATE["auto_commit"] = False
    state = "[success]ON[/success]" if APP_STATE["auto_commit"] else "[warning]OFF[/warning]"
    console.print(f"Auto-commit: {state}")


def cmd_lint_toggle(args: str) -> None:
    if args.lower() in ("on", "1", "yes"):
        APP_STATE["auto_lint"] = True
    elif args.lower() in ("off", "0", "no"):
        APP_STATE["auto_lint"] = False
    avail = " [dim](selene not installed)[/dim]" if not selene_available() else ""
    state = "[success]ON[/success]" if APP_STATE["auto_lint"] else "[warning]OFF[/warning]"
    console.print(f"Auto-lint (selene): {state}{avail}")


def cmd_upgrades() -> None:
    upgrades = [
        ("✅", "High", "Selene Linting", "Auto-lint on script generation"),
        ("✅", "High", "Watch Mode", "Auto-review on file change"),
        ("✅", "High", "Multi-Script Generation", "generate_tests tool added"),
        ("✅", "High", "Multi-Model Support", "8 providers: Anthropic, OpenAI, Groq, Gemini, Ollama, OpenRouter, Mistral, Together"),
        ("✅", "Medium", "Roblox Open Cloud", "DataStore read/write, place publish"),
        ("✅", "Medium", "TestEZ Test Generation", "generate_tests tool"),
        ("✅", "Medium", "Dependency Graph", "/deps command"),
        ("✅", "Medium", "VS Code Extension", "vscode-extension/ folder"),
        ("✅", "Medium", "Roblox Studio Plugin", "studio-plugin/ folder"),
        ("✅", "Low", "Template Library", "8 templates: singleton, signal, FSM, class, round, DataStore, bridge, promise"),
        ("✅", "Low", "Git Auto-Commit", "/autocommit toggle"),
    ]
    tbl = Table(show_header=True, header_style="bold cyan", border_style="dim")
    tbl.add_column(""); tbl.add_column("Priority"); tbl.add_column("Feature"); tbl.add_column("Status")
    for icon, pri, name, status in upgrades:
        tbl.add_row(icon, pri, name, status)
    console.print(Panel(tbl, title="[tool]Upgrade Roadmap[/tool]", border_style="magenta"))


def handle_slash_command(user_input: str, messages: list[dict]) -> bool:
    parts = user_input.strip().split(None, 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handlers: dict[str, Any] = {
        "/help": lambda: cmd_help(),
        "/?": lambda: cmd_help(),
        "/clear": lambda: (messages.clear(), console.print("[dim]History cleared.[/dim]")),
        "/model": lambda: cmd_switch_model(args, messages),
        "/models": lambda: cmd_models(),
        "/rojo": lambda: cmd_rojo(),
        "/list": lambda: cmd_rojo(),
        "/save": lambda: cmd_save(args, messages),
        "/read": lambda: cmd_read(args, messages),
        "/deps": lambda: cmd_deps(),
        "/watch": lambda: cmd_watch(args),
        "/templates": lambda: cmd_templates(args),
        "/template": lambda: cmd_template_insert(args),
        "/cloud-info": lambda: cmd_cloud_info(),
        "/cloud-read": lambda: cmd_cloud_read(args),
        "/cloud-list": lambda: cmd_cloud_list(args),
        "/new-project": lambda: cmd_new_project(args),
        "/newproject": lambda: cmd_new_project(args),
        "/autocommit": lambda: cmd_autocommit(args),
        "/lint": lambda: cmd_lint_toggle(args),
        "/upgrades": lambda: cmd_upgrades(),
    }

    fn = handlers.get(cmd)
    if fn:
        fn()
        return True
    if cmd in ("/quit", "/exit", "/q"):
        console.print("[dim]Goodbye![/dim]")
        # Stop watcher if running
        w = APP_STATE.get("watcher")
        if w:
            w.stop()
        sys.exit(0)
    return False


# ─── Banner ───────────────────────────────────────────────────────────────────

def print_banner() -> None:
    backend: AIBackend | None = APP_STATE.get("backend")
    rojo: RojoProject | None = APP_STATE.get("rojo")
    rojo_line = (
        f"[success]Rojo:[/success] [cyan]{rojo.name}[/cyan] ({rojo.project_dir})"
        if rojo
        else "[warning]Rojo: no project[/warning] — use /new-project to scaffold one"
    )
    model_line = f"[success]Model:[/success] [cyan]{backend}[/cyan]" if backend else "[warning]No model configured[/warning]"
    lint_line = "[success]Selene: installed[/success]" if selene_available() else "[dim]Selene: not installed (optional)[/dim]"
    console.print(Panel(
        "[bold bright_red]Roblox AI Dev Tool[/bold bright_red]\n"
        "[dim]Type [bold]/help[/bold] for commands · [bold]/quit[/bold] to exit[/dim]\n\n"
        + model_line + "\n" + rojo_line + "\n" + lint_line,
        border_style="bright_red",
    ))


# ─── Main chat loop ───────────────────────────────────────────────────────────

def chat() -> None:
    messages: list[dict] = []
    print_banner()

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            w = APP_STATE.get("watcher")
            if w:
                w.stop()
            break

        if not user_input:
            continue
        if user_input.startswith("/"):
            if handle_slash_command(user_input, messages):
                continue

        messages.append({"role": "user", "content": user_input})
        backend: AIBackend = APP_STATE["backend"]

        # ── streaming tool-use loop ──────────────────────────────────────────
        while True:
            console.print("\n[bold green]Claude[/bold green] ", end="")

            full_text = ""
            tool_calls: list[dict] = []
            stop_reason = "end_turn"

            try:
                for event in backend.stream(messages=messages, system=SYSTEM_PROMPT, tools=TOOLS):
                    if isinstance(event, TextDeltaEvent):
                        console.print(event.text, end="", soft_wrap=True)
                        full_text += event.text
                    elif isinstance(event, ToolStartEvent):
                        if full_text:
                            console.print()
                        console.print(f"\n[tool]⚙ Using tool: {event.tool_name}[/tool]")
                    elif isinstance(event, ToolCompleteEvent):
                        tool_calls.append({"id": event.tool_id, "name": event.tool_name, "input": event.tool_input})
                    elif isinstance(event, StreamEndEvent):
                        stop_reason = event.stop_reason
            except Exception as exc:
                console.print(f"\n[error]Stream error:[/error] {exc}")
                break

            if full_text:
                console.print()

            # Store in Anthropic format (backend handles conversion internally)
            messages.append({"role": "assistant", "content": backend.last_response_for_history()})

            if stop_reason != "tool_use" or not tool_calls:
                break

            # Execute tools and feed results back
            tool_results = []
            for tc in tool_calls:
                result = execute_tool(tc["name"], tc["input"])
                tool_results.append({"type": "tool_result", "tool_use_id": tc["id"], "content": result})
            messages.append({"role": "user", "content": tool_results})


# ─── Entry point ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="roblox-dev-tool", description="AI-powered Roblox game server assistant")
    parser.add_argument("--model", default="", metavar="SPEC", help="Model spec, e.g. anthropic:claude-opus-4-6 or openai:gpt-4o")
    parser.add_argument("--project", metavar="DIR", help="Rojo project directory")
    parser.add_argument("--new-project", metavar="NAME", dest="new_project", help="Scaffold a new Rojo project")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── Backend ──────────────────────────────────────────────────────────────
    model_spec = args.model or os.environ.get("ROBLOX_AI_MODEL", "claude-opus-4-6")
    try:
        APP_STATE["backend"] = create_backend(model_spec)
    except Exception as exc:
        console.print(f"[error]Failed to create AI backend '{model_spec}':[/error] {exc}")
        console.print("Ensure the appropriate API key env var is set. See /models for details.")
        sys.exit(1)

    # ── Rojo project ─────────────────────────────────────────────────────────
    if args.new_project:
        proj = RojoProject.create(os.getcwd(), args.new_project)
        APP_STATE["rojo"] = proj
        APP_STATE["git"] = GitManager(os.getcwd())
        console.print(f"[success]✔ Created Rojo project:[/success] [cyan]{args.new_project}[/cyan]")
    elif args.project:
        proj = RojoProject(args.project)
        if proj.load():
            APP_STATE["rojo"] = proj
            APP_STATE["git"] = GitManager(args.project)
        else:
            console.print(f"[error]No default.project.json in:[/error] {args.project}")
            sys.exit(1)
    else:
        proj = RojoProject.find(os.getcwd())
        if proj:
            APP_STATE["rojo"] = proj
            APP_STATE["git"] = GitManager(str(proj.project_dir))

    # ── Open Cloud (optional) ─────────────────────────────────────────────────
    if os.environ.get("ROBLOX_OPEN_CLOUD_KEY"):
        APP_STATE["cloud"] = OpenCloudClient()

    chat()


if __name__ == "__main__":
    main()
