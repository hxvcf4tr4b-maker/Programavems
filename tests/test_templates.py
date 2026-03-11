"""Tests for templates.py — template lookup, search, and validity."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from templates import get_template, list_templates, search_templates

EXPECTED_TEMPLATES = [
    "singleton",
    "signal",
    "statemachine",
    "class",
    "roundsystem",
    "datastore",
    "netbridge",
    "promise",
]


class TestListTemplates:
    def test_returns_list(self):
        assert isinstance(list_templates(), list)

    def test_all_expected_templates_present(self):
        names = {t["name"] for t in list_templates()}
        for expected in EXPECTED_TEMPLATES:
            assert expected in names, f"Missing template: {expected}"

    def test_each_entry_has_required_keys(self):
        for t in list_templates():
            assert "name" in t
            assert "title" in t
            assert "type" in t
            assert "placement" in t
            assert "description" in t
            assert "code" in t
            assert "tags" in t

    def test_type_is_valid_script_type(self):
        valid = {"Script", "LocalScript", "ModuleScript"}
        for t in list_templates():
            assert t["type"] in valid, f"{t['name']} has invalid type: {t['type']}"

    def test_code_is_non_empty_string(self):
        for t in list_templates():
            assert isinstance(t["code"], str)
            assert len(t["code"].strip()) > 0, f"{t['name']} has empty code"

    def test_tags_is_list(self):
        for t in list_templates():
            assert isinstance(t["tags"], list)


class TestGetTemplate:
    def test_get_existing_template(self):
        for name in EXPECTED_TEMPLATES:
            t = get_template(name)
            assert t is not None
            assert t["name"] == name

    def test_get_nonexistent_returns_none(self):
        assert get_template("doesnotexist") is None
        assert get_template("") is None

    def test_singleton_is_module_script(self):
        t = get_template("singleton")
        assert t["type"] == "ModuleScript"

    def test_roundsystem_is_server_script(self):
        t = get_template("roundsystem")
        assert t["type"] == "Script"

    def test_datastore_code_mentions_datastore(self):
        t = get_template("datastore")
        assert "DataStore" in t["code"] or "datastore" in t["code"].lower()

    def test_netbridge_code_has_remote(self):
        t = get_template("netbridge")
        code_lower = t["code"].lower()
        assert "remote" in code_lower or "replicatedstorage" in code_lower

    def test_promise_code_has_promise_structure(self):
        t = get_template("promise")
        assert "Promise" in t["code"]


class TestSearchTemplates:
    def test_search_returns_list(self):
        assert isinstance(search_templates("data"), list)

    def test_search_finds_datastore_by_keyword(self):
        results = search_templates("datastore")
        names = [r["name"] for r in results]
        assert "datastore" in names

    def test_search_finds_by_tag(self):
        results = search_templates("singleton")
        assert len(results) > 0

    def test_search_empty_query_returns_all(self):
        results = search_templates("")
        assert len(results) == len(list_templates())

    def test_search_no_match_returns_empty(self):
        results = search_templates("xyznonexistentkeyword999")
        assert results == []

    def test_search_is_case_insensitive(self):
        lower = search_templates("signal")
        upper = search_templates("SIGNAL")
        assert len(lower) == len(upper)
