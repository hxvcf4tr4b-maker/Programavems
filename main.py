#!/usr/bin/env python3
"""
Roblox AI Dev Tool — powered by Claude
Helps you build, debug, and architect Roblox game servers.
"""

import anthropic
import json
import os
import sys
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.theme import Theme

# ─── Console setup ───────────────────────────────────────────────────────────

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
                    "description": "What the script should do (e.g. 'player data saving', 'round system', 'shop UI handler')",
                },
                "placement": {
                    "type": "string",
                    "description": "Where in the Roblox Explorer hierarchy the script belongs (e.g. ServerScriptService, ReplicatedStorage.Modules)",
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
            "and style improvements. Returns structured feedback."
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
                    "description": "List of issues found in the script",
                },
                "summary": {
                    "type": "string",
                    "description": "Overall assessment of the script",
                },
                "improved_code": {
                    "type": "string",
                    "description": "The improved version of the script (if applicable)",
                },
            },
            "required": ["issues", "summary"],
        },
    },
    {
        "name": "suggest_architecture",
        "description": (
            "Suggest a server architecture or system design for a Roblox game feature. "
            "Returns a structured breakdown of components, data flow, and implementation plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Name of the system/architecture",
                },
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
                    "description": "List of scripts/instances that make up the system",
                },
                "data_flow": {
                    "type": "string",
                    "description": "Description of how data flows through the system",
                },
                "implementation_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Step-by-step implementation order",
                },
                "security_notes": {
                    "type": "string",
                    "description": "Security considerations and validations required",
                },
            },
            "required": [
                "title",
                "components",
                "data_flow",
                "implementation_steps",
            ],
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
                "store_name": {
                    "type": "string",
                    "description": "Name of the DataStore (e.g. 'PlayerData')",
                },
                "data_schema": {
                    "type": "object",
                    "description": "The default data schema as a JSON object (keys and default values)",
                },
                "auto_save_interval": {
                    "type": "integer",
                    "description": "Auto-save interval in seconds (default: 60)",
                },
                "code": {
                    "type": "string",
                    "description": "The complete Luau ModuleScript code",
                },
                "notes": {
                    "type": "string",
                    "description": "Setup and usage instructions",
                },
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
                "feature": {
                    "type": "string",
                    "description": "The feature the remotes serve (e.g. 'shop purchase', 'player chat')",
                },
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
                    "description": "List of remotes to create",
                },
                "server_code": {
                    "type": "string",
                    "description": "Server-side handler code (Script in ServerScriptService)",
                },
                "client_code": {
                    "type": "string",
                    "description": "Client-side usage code (LocalScript)",
                },
            },
            "required": ["feature", "remotes", "server_code", "client_code"],
        },
    },
]

# ─── Tool result renderers ────────────────────────────────────────────────────


def render_generate_script(data: dict[str, Any]) -> None:
    script_type = data.get("script_type", "Script")
    feature = data.get("feature", "")
    placement = data.get("placement", "")
    code = data.get("code", "")
    notes = data.get("notes", "")

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


def render_review_script(data: dict[str, Any]) -> None:
    issues = data.get("issues", [])
    summary = data.get("summary", "")
    improved = data.get("improved_code", "")

    severity_color = {"critical": "bold red", "warning": "yellow", "suggestion": "cyan"}
    severity_icon = {"critical": "✖", "warning": "⚠", "suggestion": "➤"}

    console.print(Panel(summary, title="[tool]Code Review Summary[/tool]", border_style="magenta"))
    for issue in issues:
        sev = issue.get("severity", "suggestion")
        color = severity_color.get(sev, "white")
        icon = severity_icon.get(sev, "•")
        line = f" (line {issue['line_hint']})" if issue.get("line_hint") else ""
        console.print(f"  [{color}]{icon} [{sev.upper()}]{line}[/{color}] {issue['description']}")
        console.print(f"    [dim]Fix:[/dim] {issue['fix']}\n")

    if improved:
        console.print(Panel("[bold]Improved Code[/bold]", border_style="green"))
        console.print(Syntax(improved, "lua", theme="monokai", line_numbers=True))


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
        Panel(f"[bold]{title}[/bold]", title="[tool]Architecture Suggestion[/tool]", border_style="magenta")
    )
    console.print("[bold]Components:[/bold]")
    for comp in components:
        icon = type_icons.get(comp.get("type", "Other"), "🔧")
        console.print(
            f"  {icon} [cyan]{comp['name']}[/cyan] [dim]({comp['type']} → {comp['location']})[/dim]"
        )
        console.print(f"     {comp['purpose']}\n")

    console.print(f"[bold]Data Flow:[/bold]\n{data_flow}\n")

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

    console.print(
        Panel(
            f"[bold]DataStore:[/bold] {store_name}\n"
            f"[dim]Default schema:[/dim] {json.dumps(schema, indent=2)}",
            title="[tool]DataStore Module[/tool]",
            border_style="magenta",
        )
    )
    console.print(Syntax(code, "lua", theme="monokai", line_numbers=True))
    if notes:
        console.print(Panel(Markdown(notes), title="Setup Notes", border_style="dim"))


def render_generate_remote_events(data: dict[str, Any]) -> None:
    feature = data.get("feature", "")
    remotes = data.get("remotes", [])
    server_code = data.get("server_code", "")
    client_code = data.get("client_code", "")

    dir_icons = {
        "client_to_server": "→",
        "server_to_client": "←",
        "bidirectional": "↔",
    }

    console.print(
        Panel(f"[bold]Remote Events for:[/bold] {feature}", title="[tool]Remote Events[/tool]", border_style="magenta")
    )
    console.print("[bold]Remotes to create in ReplicatedStorage:[/bold]")
    for r in remotes:
        icon = dir_icons.get(r.get("direction", ""), "?")
        console.print(
            f"  [cyan]{r['name']}[/cyan] ({r['remote_type']}) {icon} {r.get('parameters', '')}"
        )

    console.print("\n[bold]Server Handler (ServerScriptService > Script):[/bold]")
    console.print(Syntax(server_code, "lua", theme="monokai", line_numbers=True))
    console.print("\n[bold]Client Usage (StarterPlayerScripts > LocalScript):[/bold]")
    console.print(Syntax(client_code, "lua", theme="monokai", line_numbers=True))


TOOL_RENDERERS = {
    "generate_script": render_generate_script,
    "review_script": render_review_script,
    "suggest_architecture": render_suggest_architecture,
    "generate_datastore": render_generate_datastore,
    "generate_remote_events": render_generate_remote_events,
}


def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Render the tool output and return a confirmation string."""
    renderer = TOOL_RENDERERS.get(tool_name)
    if renderer:
        renderer(tool_input)
    return json.dumps({"status": "displayed", "tool": tool_name})


# ─── Main chat loop ───────────────────────────────────────────────────────────


def chat(client: anthropic.Anthropic) -> None:
    messages: list[dict] = []
    console.print(
        Panel(
            "[bold bright_red]Roblox AI Dev Tool[/bold bright_red]\n"
            "[dim]Powered by Claude · Type [bold]/help[/bold] for commands · [bold]/quit[/bold] to exit[/dim]",
            border_style="bright_red",
        )
    )

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        # ── slash commands ──
        if user_input.lower() in ("/quit", "/exit", "/q"):
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input.lower() in ("/help", "/?"):
            console.print(
                Panel(
                    "[bold]Commands:[/bold]\n"
                    "  [cyan]/help[/cyan]      Show this help\n"
                    "  [cyan]/clear[/cyan]     Clear conversation history\n"
                    "  [cyan]/quit[/cyan]      Exit\n\n"
                    "[bold]Example prompts:[/bold]\n"
                    "  • Generate a round system with lobby, game, and intermission states\n"
                    "  • Create a DataStore module for saving coins, level, and inventory\n"
                    "  • Design the architecture for a trading system\n"
                    "  • Review this script: [paste code]\n"
                    "  • Set up RemoteEvents for a shop that sells items\n"
                    "  • How do I prevent exploiters from firing my RemoteEvent?\n"
                    "  • Generate a pathfinding NPC module",
                    title="Help",
                    border_style="cyan",
                )
            )
            continue

        if user_input.lower() == "/clear":
            messages.clear()
            console.print("[dim]Conversation cleared.[/dim]")
            continue

        messages.append({"role": "user", "content": user_input})

        # ── call Claude with streaming + tool use loop ──
        while True:
            console.print("\n[bold green]Claude[/bold green] ", end="")

            full_text = ""
            tool_calls: list[dict] = []
            current_tool: dict | None = None
            current_tool_input_json = ""
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
                        block = event.content_block
                        if block.type == "tool_use":
                            if full_text:
                                console.print()  # newline after streamed text
                            current_tool = {"id": block.id, "name": block.name}
                            current_tool_input_json = ""
                            console.print(
                                f"\n[tool]⚙ Using tool: {block.name}[/tool]",
                            )
                        elif block.type == "thinking":
                            console.print("[dim][thinking...][/dim]", end="", soft_wrap=True)

                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            console.print(delta.text, end="", soft_wrap=True)
                            full_text += delta.text
                        elif delta.type == "input_json_delta":
                            current_tool_input_json += delta.partial_json
                        elif delta.type == "thinking_delta":
                            pass  # suppress thinking output

                    elif event.type == "content_block_stop":
                        if current_tool and current_tool_input_json:
                            try:
                                current_tool["input"] = json.loads(current_tool_input_json)
                            except json.JSONDecodeError:
                                current_tool["input"] = {}
                            tool_calls.append(current_tool)
                            current_tool = None
                            current_tool_input_json = ""

                    elif event.type == "message_delta":
                        stop_reason = event.delta.stop_reason or "end_turn"

                final_msg = stream.get_final_message()

            if full_text and not tool_calls:
                console.print()  # trailing newline

            # Append assistant response to history
            messages.append({"role": "assistant", "content": final_msg.content})

            if stop_reason != "tool_use" or not tool_calls:
                break

            # ── execute tools and feed results back ──
            tool_results = []
            for tc in tool_calls:
                result = execute_tool(tc["name"], tc.get("input", {}))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": result,
                    }
                )

            messages.append({"role": "user", "content": tool_results})


# ─── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print(
            "[error]Error:[/error] ANTHROPIC_API_KEY environment variable not set.\n"
            "Export it with: [cyan]export ANTHROPIC_API_KEY=your-key-here[/cyan]"
        )
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    chat(client)


if __name__ == "__main__":
    main()
