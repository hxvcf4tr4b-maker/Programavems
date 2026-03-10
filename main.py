#!/usr/bin/env python3
"""
Roblox AI Dev Tool — powered by Claude
Helps you build, debug, and architect Roblox game servers.

Usage:
  roblox-dev-tool                   # auto-detects Rojo project
  roblox-dev-tool --project ./my-game
  roblox-dev-tool --new-project MyGame
"""

import anthropic
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

from rojo_manager import RojoProject

# ─── Console ──────────────────────────────────────────────────────────────────

custom_theme = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "bold red",
        "tool": "bold magenta",
        "roblox": "bold bright_red",
        "dim": "grey50",
    }
)
console = Console(theme=custom_theme)

# ─── App state (mutable, shared across renderers) ─────────────────────────────

APP_STATE: dict[str, Any] = {
    "rojo": None,           # Optional[RojoProject]
    "last_script": None,    # last generate_script tool output
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
- HttpService (for external APIs), MarketplaceService, BadgeService
- PhysicsService (collision groups), Teams, SoundService

**Networking & Security**
- RemoteEvent and RemoteFunction (server↔client communication)
- Always validate on the server side — never trust the client
- Rate limiting, anti-exploit techniques, sanity checks
- BindableEvent / BindableFunction for server-internal communication

**Data & State**
- DataStoreService: ordered/standard DataStores, retries, budgets
- MemoryStoreService: fast ephemeral data (leaderboards, queues)
- Auto-saving patterns, data migration, backup strategies
- Session locking to prevent data loss on multiple servers

**Game Systems**
- Round systems, lobby/game state machines
- Matchmaking with TeleportService and ReservedServers
- Currency, inventory, trading systems
- Combat, hitbox validation, damage systems
- NPC AI (pathfinding, behavior trees)

**Performance**
- Part streaming (StreamingEnabled), LOD
- Efficient Heartbeat usage, avoiding RunService overuse
- Profiler usage, micro-optimization tips
- Instance caching and pooling

**Best Practices**
- Module pattern for shared code
- OOP with metatables or Luau classes
- Error handling with pcall/xpcall
- Proper cleanup (Connections, Instances) to avoid memory leaks
- Signal patterns (using BindableEvents or custom signal libraries)

When generating code:
1. Write idiomatic, well-commented Luau with proper type annotations
2. Always include server-side validation for any client input
3. Handle errors gracefully with pcall
4. Follow Roblox naming conventions (PascalCase for services/classes, camelCase for variables)
5. Specify whether code goes in Script, LocalScript, or ModuleScript
6. Mention where in the Roblox Explorer hierarchy files should be placed

Be concise but thorough. Show full working code examples, not pseudocode."""

# ─── Tool definitions ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "generate_script",
        "description": (
            "Generate a complete, ready-to-use Roblox Luau script for a specific feature or system. "
            "Use this when the user wants to create a new script from scratch."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "script_type": {
                    "type": "string",
                    "enum": ["Script", "LocalScript", "ModuleScript"],
                    "description": "The type of Roblox script to generate",
                },
                "feature": {
                    "type": "string",
                    "description": "What the script should do (e.g. 'player data saving', 'round system')",
                },
                "placement": {
                    "type": "string",
                    "description": "Where in the Roblox Explorer hierarchy (e.g. ServerScriptService, ReplicatedStorage.Modules)",
                },
                "code": {
                    "type": "string",
                    "description": "The complete Luau code for the script",
                },
                "notes": {
                    "type": "string",
                    "description": "Setup instructions, dependencies, or integration notes",
                },
            },
            "required": ["script_type", "feature", "placement", "code"],
        },
    },
    {
        "name": "review_script",
        "description": (
            "Review a Roblox Luau script for bugs, security issues, performance problems, "
            "and style improvements."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {
                                "type": "string",
                                "enum": ["critical", "warning", "suggestion"],
                            },
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
        "description": (
            "Suggest a server architecture or system design for a Roblox game feature, "
            "including a breakdown of components, data flow, and implementation plan."
        ),
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
                            "type": {
                                "type": "string",
                                "enum": [
                                    "Script",
                                    "LocalScript",
                                    "ModuleScript",
                                    "RemoteEvent",
                                    "RemoteFunction",
                                    "DataStore",
                                    "Folder",
                                    "Other",
                                ],
                            },
                            "location": {"type": "string"},
                            "purpose": {"type": "string"},
                        },
                        "required": ["name", "type", "location", "purpose"],
                    },
                },
                "data_flow": {"type": "string"},
                "implementation_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "security_notes": {"type": "string"},
            },
            "required": ["title", "components", "data_flow", "implementation_steps"],
        },
    },
    {
        "name": "generate_datastore",
        "description": (
            "Generate a complete DataStore module for player data persistence, "
            "including auto-save, session locking, and error handling."
        ),
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
        "description": (
            "Generate the RemoteEvent/RemoteFunction setup for a specific feature, "
            "including server-side handlers with validation and client-side fire calls."
        ),
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
                            "remote_type": {
                                "type": "string",
                                "enum": ["RemoteEvent", "RemoteFunction"],
                            },
                            "direction": {
                                "type": "string",
                                "enum": [
                                    "client_to_server",
                                    "server_to_client",
                                    "bidirectional",
                                ],
                            },
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
]

# ─── Tool renderers ───────────────────────────────────────────────────────────


def render_generate_script(data: dict[str, Any]) -> None:
    script_type = data.get("script_type", "Script")
    feature = data.get("feature", "")
    placement = data.get("placement", "")
    code = data.get("code", "")
    notes = data.get("notes", "")

    # Store for /save command
    APP_STATE["last_script"] = data

    console.print(
        Panel(
            f"[bold]{script_type}[/bold] — {feature}\n"
            f"[dim]Place in:[/dim] [cyan]{placement}[/cyan]",
            title="[tool]Generated Script[/tool]",
            border_style="magenta",
        )
    )
    console.print(Syntax(code, "lua", theme="monokai", line_numbers=True))
    if notes:
        console.print(Panel(Markdown(notes), title="Setup Notes", border_style="dim"))

    # Auto-offer save to Rojo project
    rojo: RojoProject | None = APP_STATE.get("rojo")
    if rojo:
        try:
            if Confirm.ask(
                f"\n[cyan]Save to Rojo project '[bold]{rojo.name}[/bold]'?[/cyan]",
                default=True,
            ):
                default_name = feature.replace(" ", "").replace("/", "")[:30]
                script_name = Prompt.ask(
                    "[cyan]Filename (without extension)[/cyan]",
                    default=default_name,
                )
                saved = rojo.save_script(script_type, placement, script_name, code)
                console.print(f"[success]✔ Saved →[/success] {saved}")
        except Exception as exc:
            console.print(f"[error]Save failed:[/error] {exc}")


def render_review_script(data: dict[str, Any]) -> None:
    issues = data.get("issues", [])
    summary = data.get("summary", "")
    improved = data.get("improved_code", "")

    severity_color = {"critical": "bold red", "warning": "yellow", "suggestion": "cyan"}
    severity_icon = {"critical": "✖", "warning": "⚠", "suggestion": "➤"}

    console.print(Panel(summary, title="[tool]Code Review[/tool]", border_style="magenta"))
    for issue in issues:
        sev = issue.get("severity", "suggestion")
        color = severity_color.get(sev, "white")
        icon = severity_icon.get(sev, "•")
        line = f" (line {issue['line_hint']})" if issue.get("line_hint") else ""
        console.print(
            f"  [{color}]{icon} [{sev.upper()}]{line}[/{color}] {issue['description']}"
        )
        console.print(f"    [dim]Fix:[/dim] {issue['fix']}\n")

    if improved:
        console.print(Panel("[bold]Improved Code[/bold]", border_style="green"))
        console.print(Syntax(improved, "lua", theme="monokai", line_numbers=True))
        APP_STATE["last_script"] = {
            "script_type": "ModuleScript",
            "feature": "reviewed script",
            "placement": "ReplicatedStorage",
            "code": improved,
        }


def render_suggest_architecture(data: dict[str, Any]) -> None:
    title = data.get("title", "Architecture")
    components = data.get("components", [])
    data_flow = data.get("data_flow", "")
    steps = data.get("implementation_steps", [])
    security = data.get("security_notes", "")

    type_icons = {
        "Script": "📜",
        "LocalScript": "💻",
        "ModuleScript": "📦",
        "RemoteEvent": "📡",
        "RemoteFunction": "🔄",
        "DataStore": "🗄",
        "Folder": "📁",
        "Other": "🔧",
    }

    console.print(
        Panel(f"[bold]{title}[/bold]", title="[tool]Architecture[/tool]", border_style="magenta")
    )

    tbl = Table(show_header=True, header_style="bold cyan", border_style="dim")
    tbl.add_column("Component")
    tbl.add_column("Type")
    tbl.add_column("Location")
    tbl.add_column("Purpose")
    for comp in components:
        icon = type_icons.get(comp.get("type", "Other"), "🔧")
        tbl.add_row(
            f"{icon} {comp['name']}",
            comp.get("type", ""),
            comp.get("location", ""),
            comp.get("purpose", ""),
        )
    console.print(tbl)
    console.print(f"\n[bold]Data Flow:[/bold]\n{data_flow}\n")

    if steps:
        console.print("[bold]Implementation Order:[/bold]")
        for i, step in enumerate(steps, 1):
            console.print(f"  {i}. {step}")

    if security:
        console.print(Panel(security, title="Security Notes", border_style="yellow"))


def render_generate_datastore(data: dict[str, Any]) -> None:
    store_name = data.get("store_name", "PlayerData")
    schema = data.get("data_schema", {})
    code = data.get("code", "")
    notes = data.get("notes", "")

    APP_STATE["last_script"] = {
        "script_type": "ModuleScript",
        "feature": store_name,
        "placement": "ServerScriptService",
        "code": code,
    }

    console.print(
        Panel(
            f"[bold]DataStore:[/bold] [cyan]{store_name}[/cyan]\n"
            f"[dim]Default schema:[/dim] {json.dumps(schema, indent=2)}",
            title="[tool]DataStore Module[/tool]",
            border_style="magenta",
        )
    )
    console.print(Syntax(code, "lua", theme="monokai", line_numbers=True))
    if notes:
        console.print(Panel(Markdown(notes), title="Setup Notes", border_style="dim"))

    rojo: RojoProject | None = APP_STATE.get("rojo")
    if rojo:
        try:
            if Confirm.ask(
                f"\n[cyan]Save DataStore module to Rojo project '[bold]{rojo.name}[/bold]'?[/cyan]",
                default=True,
            ):
                name = Prompt.ask("[cyan]Filename[/cyan]", default=store_name)
                saved = rojo.save_script("ModuleScript", "ServerScriptService", name, code)
                console.print(f"[success]✔ Saved →[/success] {saved}")
        except Exception as exc:
            console.print(f"[error]Save failed:[/error] {exc}")


def render_generate_remote_events(data: dict[str, Any]) -> None:
    feature = data.get("feature", "")
    remotes = data.get("remotes", [])
    server_code = data.get("server_code", "")
    client_code = data.get("client_code", "")

    dir_labels = {
        "client_to_server": "Client → Server",
        "server_to_client": "Server → Client",
        "bidirectional": "Bidirectional ↔",
    }

    console.print(
        Panel(
            f"[bold]Remote Events for:[/bold] {feature}",
            title="[tool]Remote Events[/tool]",
            border_style="magenta",
        )
    )

    tbl = Table(show_header=True, header_style="bold cyan", border_style="dim")
    tbl.add_column("Name")
    tbl.add_column("Type")
    tbl.add_column("Direction")
    tbl.add_column("Parameters")
    for r in remotes:
        tbl.add_row(
            r["name"],
            r["remote_type"],
            dir_labels.get(r.get("direction", ""), r.get("direction", "")),
            r.get("parameters", "—"),
        )
    console.print(tbl)

    console.print("\n[bold]Server Handler (ServerScriptService → Script):[/bold]")
    console.print(Syntax(server_code, "lua", theme="monokai", line_numbers=True))
    console.print("\n[bold]Client Usage (StarterPlayerScripts → LocalScript):[/bold]")
    console.print(Syntax(client_code, "lua", theme="monokai", line_numbers=True))

    rojo: RojoProject | None = APP_STATE.get("rojo")
    if rojo:
        try:
            if Confirm.ask(
                f"\n[cyan]Save both scripts to Rojo project '[bold]{rojo.name}[/bold]'?[/cyan]",
                default=True,
            ):
                base = Prompt.ask("[cyan]Base filename[/cyan]", default=feature.replace(" ", "")[:20])
                s = rojo.save_script("Script", "ServerScriptService", f"{base}Handler", server_code)
                c = rojo.save_script("LocalScript", "StarterPlayerScripts", f"{base}Client", client_code)
                console.print(f"[success]✔ Saved →[/success] {s}")
                console.print(f"[success]✔ Saved →[/success] {c}")
        except Exception as exc:
            console.print(f"[error]Save failed:[/error] {exc}")


TOOL_RENDERERS = {
    "generate_script": render_generate_script,
    "review_script": render_review_script,
    "suggest_architecture": render_suggest_architecture,
    "generate_datastore": render_generate_datastore,
    "generate_remote_events": render_generate_remote_events,
}


def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    renderer = TOOL_RENDERERS.get(tool_name)
    if renderer:
        renderer(tool_input)
    return json.dumps({"status": "displayed", "tool": tool_name})


# ─── Slash command handlers ───────────────────────────────────────────────────

UPGRADES = [
    {
        "title": "Selene Linting",
        "priority": "High",
        "description": (
            "Auto-lint every generated Luau script with selene "
            "(https://github.com/Kampfkarren/selene). Catches undefined globals, "
            "style issues, and bad patterns before you paste code into Studio."
        ),
    },
    {
        "title": "Watch Mode",
        "priority": "High",
        "description": (
            "Watch the Rojo src/ directory for changes. When a .luau file is "
            "modified, automatically send it to Claude for a quick review and "
            "display any issues inline."
        ),
    },
    {
        "title": "Multi-Script Feature Generation",
        "priority": "High",
        "description": (
            "Ask Claude to generate an entire feature (e.g. a full shop system) "
            "and have it produce all necessary Scripts, ModuleScripts, RemoteEvents, "
            "and folder structure in one pass — saving every file into Rojo."
        ),
    },
    {
        "title": "Roblox Open Cloud Integration",
        "priority": "Medium",
        "description": (
            "Use the Roblox Open Cloud API to read live DataStore entries, "
            "publish place files, and manage universes directly from the CLI — "
            "great for debugging production data issues."
        ),
    },
    {
        "title": "TestEZ Test Generation",
        "priority": "Medium",
        "description": (
            "Automatically generate TestEZ unit tests for any ModuleScript. "
            "Tests go in a parallel __tests__ folder and integrate with Rojo's "
            "test runner setup."
        ),
    },
    {
        "title": "Dependency Graph Visualiser",
        "priority": "Medium",
        "description": (
            "Parse all require() calls in your src/ directory and generate an "
            "ASCII or Graphviz diagram showing how your ModuleScripts depend on "
            "each other. Spots circular dependencies and dead code."
        ),
    },
    {
        "title": "VS Code Extension",
        "priority": "Medium",
        "description": (
            "A sidebar panel in VS Code that provides the same AI chat, "
            "inline code review on hover, and one-click script generation — "
            "without leaving your editor."
        ),
    },
    {
        "title": "Roblox Studio Plugin",
        "priority": "Medium",
        "description": (
            "An in-Studio plugin that adds an AI chat panel, lets you select "
            "any Script in the Explorer and right-click → 'Review with AI', "
            "and inserts generated code directly into the correct service."
        ),
    },
    {
        "title": "Template Library",
        "priority": "Low",
        "description": (
            "A built-in catalogue of battle-tested patterns: singleton service, "
            "observer/signal, state machine, OOP class template, promise wrapper. "
            "Browse with /templates and insert into your project instantly."
        ),
    },
    {
        "title": "Git Auto-Commit",
        "priority": "Low",
        "description": (
            "After each successful file save to the Rojo project, optionally "
            "run git add + git commit with an AI-generated commit message "
            "describing what was changed."
        ),
    },
]


def cmd_help() -> None:
    console.print(
        Panel(
            "[bold]Chat Commands:[/bold]\n"
            "  [cyan]/help[/cyan]              Show this help\n"
            "  [cyan]/clear[/cyan]             Clear conversation history\n"
            "  [cyan]/save [name][/cyan]       Save last generated script to Rojo project\n"
            "  [cyan]/read <path>[/cyan]       Read a project script into the conversation\n"
            "  [cyan]/list[/cyan]              List all scripts in the Rojo project\n"
            "  [cyan]/rojo[/cyan]              Show Rojo project status\n"
            "  [cyan]/new-project <name>[/cyan] Create a new Rojo project here\n"
            "  [cyan]/upgrades[/cyan]          Show suggested upgrades for this tool\n"
            "  [cyan]/quit[/cyan]              Exit\n\n"
            "[bold]Example prompts:[/bold]\n"
            "  • Generate a round system with lobby, game, and intermission states\n"
            "  • Create a DataStore module for saving coins, level, and inventory\n"
            "  • Design the architecture for a player trading system\n"
            "  • Set up RemoteEvents for a shop — make it exploit-proof\n"
            "  • Review this script: [paste code]\n"
            "  • How do I prevent exploiters from firing my RemoteEvent?\n"
            "  • Generate a pathfinding NPC module with aggro range",
            title="Help",
            border_style="cyan",
        )
    )


def cmd_rojo() -> None:
    rojo: RojoProject | None = APP_STATE.get("rojo")
    if not rojo:
        console.print(
            Panel(
                "[warning]No Rojo project detected.[/warning]\n\n"
                "Run [cyan]/new-project <name>[/cyan] to scaffold one here,\n"
                "or open the tool from a directory containing [bold]default.project.json[/bold].",
                title="Rojo Status",
                border_style="yellow",
            )
        )
        return

    summary = rojo.summary()
    scripts = summary["scripts"]

    tbl = Table(show_header=True, header_style="bold cyan", border_style="dim", title="Scripts in project")
    tbl.add_column("#", style="dim", width=4)
    tbl.add_column("Path")
    tbl.add_column("Type")
    tbl.add_column("Lines", justify="right")
    for i, s in enumerate(scripts, 1):
        tbl.add_row(str(i), s["path"], s["type"], str(s["size_lines"]))

    console.print(
        Panel(
            f"[bold]Project:[/bold] {summary['name']}\n"
            f"[bold]Directory:[/bold] [cyan]{summary['project_dir']}[/cyan]\n"
            f"[bold]Scripts:[/bold] {summary['script_count']}",
            title="[success]Rojo Project Connected[/success]",
            border_style="green",
        )
    )
    if scripts:
        console.print(tbl)


def cmd_save(args: str, messages: list[dict]) -> None:
    rojo: RojoProject | None = APP_STATE.get("rojo")
    if not rojo:
        console.print("[warning]No Rojo project connected. Use /new-project <name> first.[/warning]")
        return

    last = APP_STATE.get("last_script")
    if not last:
        console.print("[warning]No script has been generated yet.[/warning]")
        return

    script_name = args.strip() or Prompt.ask(
        "[cyan]Filename (without extension)[/cyan]",
        default=last.get("feature", "Script").replace(" ", "")[:30],
    )
    try:
        saved = rojo.save_script(
            last["script_type"], last["placement"], script_name, last["code"]
        )
        console.print(f"[success]✔ Saved →[/success] {saved}")
    except Exception as exc:
        console.print(f"[error]Save failed:[/error] {exc}")


def cmd_read(path_arg: str, messages: list[dict]) -> None:
    rojo: RojoProject | None = APP_STATE.get("rojo")
    if not path_arg:
        console.print("[warning]Usage: /read <relative-path>[/warning]")
        return

    try:
        if rojo:
            code = rojo.read_script(path_arg)
        else:
            from pathlib import Path
            code = Path(path_arg).read_text(encoding="utf-8")

        console.print(Panel(f"[dim]{path_arg}[/dim]", border_style="dim"))
        console.print(Syntax(code, "lua", theme="monokai", line_numbers=True))

        messages.append({
            "role": "user",
            "content": f"Here is the script at `{path_arg}` for context:\n```luau\n{code}\n```",
        })
        messages.append({
            "role": "assistant",
            "content": f"Got it — I've read `{path_arg}` ({len(code.splitlines())} lines). What would you like me to do with it?",
        })
        console.print(f"[dim]Script loaded into conversation context.[/dim]")
    except FileNotFoundError:
        console.print(f"[error]File not found:[/error] {path_arg}")
    except Exception as exc:
        console.print(f"[error]Error reading file:[/error] {exc}")


def cmd_list() -> None:
    rojo: RojoProject | None = APP_STATE.get("rojo")
    if not rojo:
        console.print("[warning]No Rojo project connected.[/warning]")
        return
    cmd_rojo()


def cmd_new_project(name: str) -> None:
    if not name:
        name = Prompt.ask("[cyan]Project name[/cyan]", default="MyGame")

    dest = Prompt.ask("[cyan]Directory[/cyan]", default=os.getcwd())
    try:
        proj = RojoProject.create(dest, name)
        APP_STATE["rojo"] = proj
        console.print(
            Panel(
                f"[bold]Created Rojo project:[/bold] [cyan]{name}[/cyan]\n"
                f"[dim]{proj.project_dir}[/dim]\n\n"
                "Starter scripts written to [bold]src/[/bold].\n"
                "Run [bold]rojo serve[/bold] in that directory to start syncing.",
                title="[success]Rojo Project Created[/success]",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(f"[error]Failed to create project:[/error] {exc}")


def cmd_upgrades() -> None:
    priority_color = {"High": "bold green", "Medium": "yellow", "Low": "cyan"}
    console.print(
        Panel(
            "[bold]Suggested Upgrades[/bold]\n[dim]Ideas to make this tool more powerful[/dim]",
            border_style="magenta",
        )
    )
    for i, upg in enumerate(UPGRADES, 1):
        pc = priority_color.get(upg["priority"], "white")
        console.print(
            f"\n  [bold]{i}. {upg['title']}[/bold]  [{pc}]({upg['priority']} priority)[/{pc}]"
        )
        console.print(f"     {upg['description']}")


def handle_slash_command(user_input: str, messages: list[dict]) -> bool:
    """
    Handle /commands. Returns True if the input was a slash command
    (so the chat loop should skip the API call).
    """
    parts = user_input.strip().split(None, 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd in ("/help", "/?"):
        cmd_help()
    elif cmd == "/clear":
        messages.clear()
        console.print("[dim]Conversation cleared.[/dim]")
    elif cmd == "/rojo":
        cmd_rojo()
    elif cmd == "/save":
        cmd_save(args, messages)
    elif cmd == "/read":
        cmd_read(args, messages)
    elif cmd == "/list":
        cmd_list()
    elif cmd in ("/new-project", "/newproject"):
        cmd_new_project(args)
    elif cmd == "/upgrades":
        cmd_upgrades()
    elif cmd in ("/quit", "/exit", "/q"):
        console.print("[dim]Goodbye![/dim]")
        sys.exit(0)
    else:
        return False  # not a slash command we recognise — let Claude handle it

    return True


# ─── Banner ───────────────────────────────────────────────────────────────────

def print_banner() -> None:
    rojo: RojoProject | None = APP_STATE.get("rojo")
    rojo_line = (
        f"[success]Rojo:[/success] [cyan]{rojo.name}[/cyan] ({rojo.project_dir})"
        if rojo
        else "[warning]Rojo: no project detected[/warning] (use /new-project to create one)"
    )
    console.print(
        Panel(
            "[bold bright_red]Roblox AI Dev Tool[/bold bright_red]\n"
            "[dim]Powered by Claude · Type [bold]/help[/bold] for commands · [bold]/quit[/bold] to exit[/dim]\n\n"
            + rojo_line,
            border_style="bright_red",
        )
    )


# ─── Main chat loop ───────────────────────────────────────────────────────────


def chat(client: anthropic.Anthropic) -> None:
    messages: list[dict] = []
    print_banner()

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            if handle_slash_command(user_input, messages):
                continue
            # Unrecognised slash command — fall through to Claude

        messages.append({"role": "user", "content": user_input})

        # ── Streaming tool-use loop ──────────────────────────────────────────
        while True:
            console.print("\n[bold green]Claude[/bold green] ", end="")

            full_text = ""
            tool_calls: list[dict] = []
            current_tool: dict | None = None
            current_tool_json = ""
            stop_reason = "end_turn"

            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=8192,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_start":
                        blk = event.content_block
                        if blk.type == "tool_use":
                            if full_text:
                                console.print()
                            current_tool = {"id": blk.id, "name": blk.name}
                            current_tool_json = ""
                            console.print(f"\n[tool]⚙ Using tool: {blk.name}[/tool]")
                        elif blk.type == "thinking":
                            console.print("[dim][thinking...][/dim]", end="", soft_wrap=True)

                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            console.print(delta.text, end="", soft_wrap=True)
                            full_text += delta.text
                        elif delta.type == "input_json_delta":
                            current_tool_json += delta.partial_json

                    elif event.type == "content_block_stop":
                        if current_tool and current_tool_json:
                            try:
                                current_tool["input"] = json.loads(current_tool_json)
                            except json.JSONDecodeError:
                                current_tool["input"] = {}
                            tool_calls.append(current_tool)
                            current_tool = None
                            current_tool_json = ""

                    elif event.type == "message_delta":
                        stop_reason = event.delta.stop_reason or "end_turn"

                final_msg = stream.get_final_message()

            if full_text and not tool_calls:
                console.print()

            messages.append({"role": "assistant", "content": final_msg.content})

            if stop_reason != "tool_use" or not tool_calls:
                break

            tool_results = []
            for tc in tool_calls:
                result = execute_tool(tc["name"], tc.get("input", {}))
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tc["id"], "content": result}
                )

            messages.append({"role": "user", "content": tool_results})


# ─── Entry point ──────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="roblox-dev-tool",
        description="AI-powered Roblox game server development assistant",
    )
    parser.add_argument(
        "--project",
        metavar="DIR",
        help="Path to an existing Rojo project directory",
    )
    parser.add_argument(
        "--new-project",
        metavar="NAME",
        dest="new_project",
        help="Scaffold a new Rojo project in the current directory with this name",
    )
    return parser.parse_args()


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print(
            "[error]Error:[/error] ANTHROPIC_API_KEY environment variable not set.\n"
            "  [cyan]export ANTHROPIC_API_KEY=your-key-here[/cyan]"
        )
        sys.exit(1)

    args = parse_args()

    # ── Rojo project initialisation ──────────────────────────────────────────
    if args.new_project:
        proj = RojoProject.create(os.getcwd(), args.new_project)
        APP_STATE["rojo"] = proj
        console.print(
            f"[success]✔ Created Rojo project:[/success] [cyan]{args.new_project}[/cyan]"
        )
    elif args.project:
        proj = RojoProject(args.project)
        if proj.load():
            APP_STATE["rojo"] = proj
        else:
            console.print(
                f"[error]No default.project.json found in:[/error] {args.project}"
            )
            sys.exit(1)
    else:
        proj = RojoProject.find(os.getcwd())
        if proj:
            APP_STATE["rojo"] = proj

    client = anthropic.Anthropic(api_key=api_key)
    chat(client)


if __name__ == "__main__":
    main()
