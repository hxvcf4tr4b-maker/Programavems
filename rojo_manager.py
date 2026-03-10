"""
rojo_manager.py — Rojo project integration for the Roblox AI Dev Tool.

Handles project detection, path mapping, and file I/O so generated scripts
land in the right place for Rojo to sync into Roblox Studio.

Rojo file conventions:
  .server.luau  → Script        (runs on server)
  .client.luau  → LocalScript   (runs on client)
  .luau         → ModuleScript  (shared/required)
"""

import json
import os
from pathlib import Path
from typing import Optional

# ─── File extension mapping ───────────────────────────────────────────────────

SCRIPT_EXTENSIONS: dict[str, str] = {
    "Script": ".server.luau",
    "LocalScript": ".client.luau",
    "ModuleScript": ".luau",
}

# ─── Roblox service → src subdirectory mapping ───────────────────────────────

PLACEMENT_MAP: dict[str, str] = {
    "ServerScriptService": "src/server",
    "ServerStorage": "src/server_storage",
    "ReplicatedStorage": "src/shared",
    "StarterPlayerScripts": "src/client",
    "StarterGui": "src/client/ui",
    "StarterCharacterScripts": "src/client/character",
    "Workspace": "src/workspace",
    "Lighting": "src/lighting",
}

# ─── Default project template ─────────────────────────────────────────────────

DEFAULT_PROJECT_TEMPLATE: dict = {
    "name": "MyGame",
    "tree": {
        "$className": "DataModel",
        "ServerScriptService": {
            "$className": "ServerScriptService",
            "$path": "src/server",
        },
        "ReplicatedStorage": {
            "$className": "ReplicatedStorage",
            "$path": "src/shared",
        },
        "StarterPlayer": {
            "$className": "StarterPlayer",
            "StarterPlayerScripts": {
                "$className": "StarterPlayerScripts",
                "$path": "src/client",
            },
            "StarterCharacterScripts": {
                "$className": "StarterCharacterScripts",
                "$path": "src/client/character",
            },
        },
        "StarterGui": {
            "$className": "StarterGui",
            "$path": "src/client/ui",
        },
        "ServerStorage": {
            "$className": "ServerStorage",
            "$path": "src/server_storage",
        },
    },
}

STARTER_SERVER_SCRIPT = """\
-- Main.server.luau
-- Entry point for server-side game logic.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

Players.PlayerAdded:Connect(function(player)
\tprint(player.Name .. " joined the game.")
end)

Players.PlayerRemoving:Connect(function(player)
\tprint(player.Name .. " left the game.")
end)
"""

STARTER_CLIENT_SCRIPT = """\
-- Main.client.luau
-- Entry point for client-side game logic.

local Players = game:GetService("Players")
local localPlayer = Players.LocalPlayer
local ReplicatedStorage = game:GetService("ReplicatedStorage")

print("Client ready for player:", localPlayer.Name)
"""

STARTER_SHARED_MODULE = """\
-- Shared.luau
-- Shared constants and utilities accessible by both server and client.

local Shared = {}

Shared.VERSION = "1.0.0"
Shared.GAME_NAME = "MyGame"

return Shared
"""


# ─── RojoProject class ────────────────────────────────────────────────────────

class RojoProject:
    """Represents a Rojo project on disk."""

    def __init__(self, project_dir: str | Path) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.config_path = self.project_dir / "default.project.json"
        self.config: dict = {}

    # ── Discovery ─────────────────────────────────────────────────────────────

    @classmethod
    def find(cls, search_dir: str | Path = ".") -> Optional["RojoProject"]:
        """Walk up from search_dir to find a default.project.json."""
        current = Path(search_dir).resolve()
        for _ in range(10):
            candidate = current / "default.project.json"
            if candidate.exists():
                proj = cls(current)
                proj.load()
                return proj
            parent = current.parent
            if parent == current:
                break
            current = parent
        return None

    # ── Creation ──────────────────────────────────────────────────────────────

    @classmethod
    def create(cls, project_dir: str | Path, name: str = "MyGame") -> "RojoProject":
        """Create a new Rojo project with standard src structure and starter scripts."""
        proj = cls(project_dir)
        proj.project_dir.mkdir(parents=True, exist_ok=True)

        config = json.loads(json.dumps(DEFAULT_PROJECT_TEMPLATE))  # deep copy
        config["name"] = name

        # Create directory tree
        for rel in [
            "src/server",
            "src/shared",
            "src/client",
            "src/client/ui",
            "src/client/character",
            "src/server_storage",
            "src/workspace",
        ]:
            (proj.project_dir / rel).mkdir(parents=True, exist_ok=True)

        # Write starter scripts
        (proj.project_dir / "src/server/Main.server.luau").write_text(
            STARTER_SERVER_SCRIPT, encoding="utf-8"
        )
        (proj.project_dir / "src/client/Main.client.luau").write_text(
            STARTER_CLIENT_SCRIPT, encoding="utf-8"
        )
        (proj.project_dir / "src/shared/Shared.luau").write_text(
            STARTER_SHARED_MODULE, encoding="utf-8"
        )

        # Write project config
        proj.config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        proj.config = config
        return proj

    # ── I/O ───────────────────────────────────────────────────────────────────

    def load(self) -> bool:
        """Load config from disk. Returns False if file not found."""
        if not self.config_path.exists():
            return False
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        return True

    @property
    def name(self) -> str:
        return self.config.get("name", "Unknown")

    # ── Path resolution ───────────────────────────────────────────────────────

    def get_file_path(
        self, script_type: str, placement: str, script_name: str
    ) -> Path:
        """
        Resolve the full filesystem path for a script.

        Args:
            script_type: "Script", "LocalScript", or "ModuleScript"
            placement:   Roblox hierarchy string, e.g. "ServerScriptService",
                         "ReplicatedStorage/Modules", or "ReplicatedStorage.Modules"
            script_name: The desired filename (without extension)

        Returns:
            Absolute Path where the script file should be written.
        """
        ext = SCRIPT_EXTENSIONS.get(script_type, ".luau")

        # Normalise placement separators
        placement = placement.strip("/").replace(".", "/")
        parts = [p for p in placement.split("/") if p]
        service = parts[0] if parts else "ReplicatedStorage"
        sub_parts = parts[1:] if len(parts) > 1 else []

        base_dir = PLACEMENT_MAP.get(service, f"src/{service.lower()}")
        file_dir = self.project_dir / base_dir
        for part in sub_parts:
            file_dir = file_dir / part

        file_dir.mkdir(parents=True, exist_ok=True)
        return file_dir / f"{script_name}{ext}"

    # ── File operations ───────────────────────────────────────────────────────

    def save_script(
        self, script_type: str, placement: str, script_name: str, code: str
    ) -> Path:
        """Write a script to the correct Rojo project location. Returns saved path."""
        path = self.get_file_path(script_type, placement, script_name)
        path.write_text(code, encoding="utf-8")
        return path

    def read_script(self, path: str | Path) -> str:
        """Read a script file (absolute or relative to project root)."""
        p = Path(path)
        if not p.is_absolute():
            p = self.project_dir / p
        return p.read_text(encoding="utf-8")

    def list_scripts(self) -> list[dict]:
        """
        Walk the src/ directory and return info about every Luau script.

        Returns a list of dicts with keys: path, type, name, size_lines.
        """
        scripts: list[dict] = []
        src = self.project_dir / "src"
        if not src.exists():
            return scripts

        for p in sorted(src.rglob("*")):
            if p.suffix not in (".lua", ".luau"):
                continue
            stem = p.stem  # e.g. "Main.server" or "DataStore"
            if ".server" in stem:
                stype = "Script"
            elif ".client" in stem:
                stype = "LocalScript"
            else:
                stype = "ModuleScript"

            rel = p.relative_to(self.project_dir)
            lines = len(p.read_text(encoding="utf-8").splitlines())
            scripts.append(
                {
                    "path": str(rel),
                    "type": stype,
                    "name": stem.split(".")[0],
                    "size_lines": lines,
                }
            )
        return scripts

    # ── Info ──────────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Return a summary dict for display."""
        scripts = self.list_scripts()
        return {
            "name": self.name,
            "project_dir": str(self.project_dir),
            "config_path": str(self.config_path),
            "script_count": len(scripts),
            "scripts": scripts,
        }
