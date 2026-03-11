# Roblox AI Dev Tool

An interactive CLI (and IDE extension) that uses AI to help you build, debug, and architect Roblox game servers. Supports **8 AI providers** and integrates with **Rojo**, **Selene**, **Git**, and the **Roblox Open Cloud API**.

```
┌─────────────────────────────────────────────────────┐
│            Roblox AI Dev Tool — Architecture         │
├─────────────┬─────────────────┬─────────────────────┤
│  CLI (main) │  VS Code Ext.   │  Studio Plugin       │
│  main.py    │  extension.ts   │  RobloxAIDevTool.lua │
└──────┬──────┴────────┬────────┴──────────┬──────────┘
       │               │ stdio JSON-RPC     │ HTTP JSON-RPC
       │           server_mode.py      http_server.py
       │               │                   │
       └───────────────┴───────────────────┘
                       │
                  ai_backend.py
          ┌────────────┼────────────────────┐
     Anthropic    OpenAI-compat       Gemini
    (Claude)    Groq/Mistral/         Google
               OpenRouter/Ollama
```

## Features

- **Multi-model AI** — switch between Claude, GPT-4o, Gemini, Llama, Mistral and more with one flag
- **6 AI tools** — generate scripts, review code, design architecture, create DataStores, set up RemoteEvents, generate TestEZ tests
- **Rojo integration** — auto-detects your project; saves scripts to the correct `src/` paths with proper `.server.luau` / `.client.luau` extensions
- **8 Luau templates** — Singleton, Signal, StateMachine, Class, RoundSystem, DataStore, NetBridge, Promise
- **Selene linting** — automatic static analysis after every generation
- **Watch mode** — auto-review files on save
- **Dependency graph** — detect `require()` cycles and visualise your module tree
- **Git auto-commit** — AI-written commit messages for generated scripts
- **Roblox Open Cloud** — read/write DataStores and publish places from the CLI
- **VS Code extension** — chat panel, right-click review, command palette generate/template/deps
- **Studio plugin** — docked chat widget, toolbar review/generate buttons

---

## Installation

### Python (CLI)

```bash
pip install -r requirements.txt
python main.py
```

### Build a standalone .exe

```bash
python build.py
# Output: dist/roblox-dev-tool.exe  (Windows)
#         dist/roblox-dev-tool       (Linux/macOS)
```

---

## AI Provider Setup

Set the relevant environment variable for your chosen provider:

| Provider | Model example | Environment variable |
|---|---|---|
| **Anthropic** (default) | `claude-opus-4-6` | `ANTHROPIC_API_KEY` |
| **OpenAI** | `openai:gpt-4o` | `OPENAI_API_KEY` |
| **Groq** | `groq:llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| **Google Gemini** | `gemini:gemini-2.0-flash-exp` | `GOOGLE_API_KEY` |
| **Mistral** | `mistral:mistral-large-latest` | `MISTRAL_API_KEY` |
| **OpenRouter** | `openrouter:anthropic/claude-3.5-sonnet` | `OPENROUTER_API_KEY` |
| **Ollama** (local) | `ollama:llama3` | *(none — Ollama must be running)* |
| **Together AI** | `together:meta-llama/Llama-3-70b` | `TOGETHER_API_KEY` |

```bash
# Example: use Groq
export GROQ_API_KEY=gsk_...
python main.py --model groq:llama-3.3-70b-versatile
```

---

## CLI Usage

```bash
python main.py                            # auto-detect Rojo project, use Claude
python main.py --model openai:gpt-4o      # GPT-4o
python main.py --model ollama:llama3      # local Ollama
python main.py --project ./my-game        # specify Rojo project directory
python main.py --new-project MyGame       # scaffold a new Rojo project
python main.py --serve                    # start HTTP bridge for Studio plugin
```

### Slash Commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/model <spec>` | Switch AI model mid-session (e.g. `/model groq:llama-3.3-70b-versatile`) |
| `/models` | List all providers and their status |
| `/save` | Save last generated script to Rojo project |
| `/review <path>` | Review a specific file |
| `/deps` | Show `require()` dependency graph |
| `/watch` | Toggle file-watcher (auto-review on save) |
| `/templates` | List all built-in Luau templates |
| `/template <name>` | Insert a template (e.g. `/template singleton`) |
| `/cloud-info` | Show Roblox Open Cloud universe info |
| `/cloud-list <datastore>` | List DataStore entries |
| `/cloud-read <datastore> <key>` | Read a DataStore entry |
| `/autocommit` | Toggle git auto-commit for saved scripts |
| `/lint` | Run Selene on last generated script |
| `/quit` | Exit |

---

## Rojo Integration

The tool auto-detects `default.project.json` by walking up from your working directory.

**Scaffold a new project:**
```bash
python main.py --new-project MyGame
```

This creates:
```
MyGame/
├── default.project.json
└── src/
    ├── server/          → ServerScriptService
    ├── shared/          → ReplicatedStorage
    ├── client/          → StarterPlayerScripts
    └── server_storage/  → ServerStorage
```

When you ask the AI to generate a script and then `/save`, it writes to the correct path:
- `Script` → `src/server/Name.server.luau`
- `LocalScript` → `src/client/Name.client.luau`
- `ModuleScript` → `src/shared/Name.luau`

---

## Luau Templates

```
/template singleton      Singleton service pattern
/template signal         Custom event/signal (like BindableEvent)
/template statemachine   Finite state machine
/template class          OOP class with metatables
/template roundsystem    Game round loop with lobby/intermission
/template datastore      DataStore wrapper with retry + auto-save
/template netbridge      RemoteEvent/RemoteFunction bridge
/template promise        Promise implementation for async Luau
```

---

## Selene Linting

If [Selene](https://kampfkarren.github.io/selene/) is on your `PATH`, the tool lints every generated script automatically. Install it:

```bash
# Cargo
cargo install selene

# Or download from GitHub releases
```

---

## Open Cloud API

Set your credentials:

```bash
export ROBLOX_OPEN_CLOUD_KEY=your_api_key
export ROBLOX_UNIVERSE_ID=your_universe_id
```

Then use the `/cloud-*` commands in the CLI, or call `OpenCloudClient` from code:

```python
from open_cloud import OpenCloudClient
client = OpenCloudClient()
value, metadata = client.get_entry("PlayerData", "user_123")
client.set_entry("PlayerData", "user_123", {"coins": 500})
```

---

## VS Code Extension

### Setup

1. Make sure Python dependencies are installed and your `ANTHROPIC_API_KEY` (or other) is set
2. Open `vscode-extension/` in VS Code
3. Press `F5` to run in Extension Development Host
4. Or compile TypeScript: `cd vscode-extension && npm install && npm run compile`

### Configuration (`settings.json`)

```json
{
  "robloxAI.model": "claude-opus-4-6",
  "robloxAI.anthropicApiKey": "sk-ant-...",
  "robloxAI.openaiApiKey": "",
  "robloxAI.pythonPath": "python"
}
```

### Commands (Command Palette)

| Command | Shortcut |
|---|---|
| Roblox AI: Open Chat | Activity bar icon |
| Roblox AI: Review File | Right-click a `.lua`/`.luau` file |
| Roblox AI: Generate Script | `Ctrl+Shift+P` → Generate |
| Roblox AI: Insert Template | `Ctrl+Shift+P` → Template |
| Roblox AI: Show Dependency Graph | `Ctrl+Shift+P` → Deps |

---

## Roblox Studio Plugin

### Setup

1. Start the HTTP bridge:
   ```bash
   python main.py --serve
   # or
   python http_server.py
   ```
   This starts a local server on `http://localhost:8765`.

2. In Roblox Studio → Plugins → Plugin Manager → Install from File → select `studio-plugin/RobloxAIDevTool.lua`

3. Enable **HttpService** in Studio:
   - Home → Game Settings → Security → Allow HTTP Requests ✓

4. Edit `CONFIG` at the top of the plugin if needed:
   ```lua
   local CONFIG = {
       BackendURL = "http://localhost:8765",
       Model = "claude-opus-4-6",
   }
   ```

### Usage

- **AI Chat** toolbar button → opens/closes the chat panel
- **Review** button → reviews the currently selected Script/LocalScript/ModuleScript
- **Generate** button → prompts you to type what to generate in the chat box

---

## Git Auto-commit

Enable auto-commit so every saved script gets a commit with an AI-written message:

```
/autocommit
```

Requires Git initialised in your project directory (`git init`).

---

## Development

```bash
# Run tests
pip install pytest
pytest tests/ -v

# Build executable
python build.py

# Run HTTP bridge directly
python http_server.py
```

### Project Structure

```
main.py              CLI entry point and chat loop
ai_backend.py        Multi-provider AI abstraction (Anthropic, OpenAI, Gemini, …)
rojo_manager.py      Rojo project detection and file I/O
templates.py         8 built-in Luau templates
selene_linter.py     Selene static analysis integration
watch_mode.py        File watcher (watchdog)
dependency_graph.py  require() cycle detection and ASCII graph
git_manager.py       Git auto-commit with AI commit messages
open_cloud.py        Roblox Open Cloud REST client
server_mode.py       JSON-RPC stdio server (VS Code extension backend)
http_server.py       JSON-RPC HTTP server (Studio plugin bridge)
build.py             PyInstaller build script
roblox_devtool.spec  PyInstaller spec file

vscode-extension/
  src/extension.ts   VS Code extension (TypeScript)
  package.json       Extension manifest

studio-plugin/
  RobloxAIDevTool.lua  Roblox Studio plugin (Lua)
```

---

## Requirements

- Python 3.10+
- Rojo (optional, for file sync)
- Selene (optional, for linting)
- Git (optional, for auto-commit)
- Roblox Studio + HttpService enabled (for Studio plugin)
