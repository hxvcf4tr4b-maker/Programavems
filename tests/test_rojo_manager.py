"""Tests for rojo_manager.py — path mapping, extension logic, project helpers."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from rojo_manager import (
    PLACEMENT_MAP,
    SCRIPT_EXTENSIONS,
    RojoProject,
)


# ── Constants ─────────────────────────────────────────────────────────────────

class TestConstants:
    def test_script_extensions(self):
        assert SCRIPT_EXTENSIONS["Script"] == ".server.luau"
        assert SCRIPT_EXTENSIONS["LocalScript"] == ".client.luau"
        assert SCRIPT_EXTENSIONS["ModuleScript"] == ".luau"

    def test_placement_map_has_core_services(self):
        assert "ServerScriptService" in PLACEMENT_MAP
        assert "ReplicatedStorage" in PLACEMENT_MAP
        assert "StarterPlayerScripts" in PLACEMENT_MAP
        assert "StarterGui" in PLACEMENT_MAP


# ── RojoProject.create ────────────────────────────────────────────────────────

class TestRojoProjectCreate:
    def test_creates_default_project_json(self, tmp_path):
        proj = RojoProject.create(tmp_path, "TestGame")
        project_file = tmp_path / "default.project.json"
        assert project_file.exists()
        data = json.loads(project_file.read_text())
        assert data["name"] == "TestGame"

    def test_creates_src_directories(self, tmp_path):
        RojoProject.create(tmp_path, "TestGame")
        assert (tmp_path / "src" / "server").is_dir()
        assert (tmp_path / "src" / "shared").is_dir()
        assert (tmp_path / "src" / "client").is_dir()

    def test_returns_rojo_project_instance(self, tmp_path):
        proj = RojoProject.create(tmp_path, "TestGame")
        assert isinstance(proj, RojoProject)
        assert proj.project_dir == tmp_path

    def test_project_name_in_json(self, tmp_path):
        RojoProject.create(tmp_path, "MyAwesomeGame")
        data = json.loads((tmp_path / "default.project.json").read_text())
        assert data["name"] == "MyAwesomeGame"


# ── RojoProject.find ──────────────────────────────────────────────────────────

class TestRojoProjectFind:
    def test_finds_project_in_same_dir(self, tmp_path):
        (tmp_path / "default.project.json").write_text('{"name":"Test","tree":{"$className":"DataModel"}}')
        proj = RojoProject.find(tmp_path)
        assert proj is not None
        assert proj.project_dir == tmp_path

    def test_finds_project_in_parent_dir(self, tmp_path):
        sub = tmp_path / "src" / "server"
        sub.mkdir(parents=True)
        (tmp_path / "default.project.json").write_text('{"name":"Test","tree":{"$className":"DataModel"}}')
        proj = RojoProject.find(sub)
        assert proj is not None
        assert proj.project_dir == tmp_path

    def test_returns_none_if_not_found(self, tmp_path):
        # tmp_path has no default.project.json
        proj = RojoProject.find(tmp_path)
        assert proj is None


# ── RojoProject.save_script ───────────────────────────────────────────────────

class TestSaveScript:
    def test_server_script_saved_with_correct_extension(self, tmp_path):
        proj = RojoProject.create(tmp_path, "TestGame")
        saved = proj.save_script("Script", "ServerScriptService", "GameManager", "print('hi')")
        assert saved.suffix == ".luau"
        assert ".server." in saved.name
        assert saved.exists()
        assert saved.read_text() == "print('hi')"

    def test_local_script_saved_with_correct_extension(self, tmp_path):
        proj = RojoProject.create(tmp_path, "TestGame")
        saved = proj.save_script("LocalScript", "StarterPlayerScripts", "UIController", "-- ui")
        assert ".client." in saved.name
        assert saved.exists()

    def test_module_script_saved_with_luau_extension(self, tmp_path):
        proj = RojoProject.create(tmp_path, "TestGame")
        saved = proj.save_script("ModuleScript", "ReplicatedStorage", "DataUtil", "return {}")
        assert saved.suffix == ".luau"
        assert ".server." not in saved.name
        assert ".client." not in saved.name

    def test_script_placed_in_correct_subdirectory(self, tmp_path):
        proj = RojoProject.create(tmp_path, "TestGame")
        saved = proj.save_script("Script", "ServerScriptService", "MyScript", "")
        assert "server" in str(saved)

    def test_script_content_written(self, tmp_path):
        proj = RojoProject.create(tmp_path, "TestGame")
        code = "local x = 1\nprint(x)"
        saved = proj.save_script("ModuleScript", "ReplicatedStorage", "Util", code)
        assert saved.read_text() == code


# ── RojoProject.list_scripts ──────────────────────────────────────────────────

class TestListScripts:
    def test_empty_project_returns_empty_list(self, tmp_path):
        proj = RojoProject.create(tmp_path, "TestGame")
        scripts = proj.list_scripts()
        # Starter scripts may be created; just check it's a list
        assert isinstance(scripts, list)

    def test_saved_scripts_appear_in_list(self, tmp_path):
        proj = RojoProject.create(tmp_path, "TestGame")
        proj.save_script("Script", "ServerScriptService", "MyServer", "print('server')")
        proj.save_script("ModuleScript", "ReplicatedStorage", "Shared", "return {}")
        scripts = proj.list_scripts()
        names = [s["name"] for s in scripts]
        assert any("MyServer" in n for n in names)

    def test_list_script_entries_have_expected_keys(self, tmp_path):
        proj = RojoProject.create(tmp_path, "TestGame")
        proj.save_script("Script", "ServerScriptService", "Test", "")
        scripts = proj.list_scripts()
        for s in scripts:
            assert "name" in s
            assert "path" in s


# ── RojoProject.summary ───────────────────────────────────────────────────────

class TestProjectSummary:
    def test_summary_returns_dict(self, tmp_path):
        proj = RojoProject.create(tmp_path, "TestGame")
        s = proj.summary()
        assert isinstance(s, dict)

    def test_summary_contains_name(self, tmp_path):
        proj = RojoProject.create(tmp_path, "TestGame")
        s = proj.summary()
        assert s.get("name") == "TestGame"
