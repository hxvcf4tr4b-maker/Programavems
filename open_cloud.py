"""
open_cloud.py — Roblox Open Cloud API client.

Requires:
  ROBLOX_OPEN_CLOUD_KEY  — API key from creator.roblox.com
  ROBLOX_UNIVERSE_ID     — Your game's Universe ID

Supported operations:
  DataStore  → list, read, write, delete entries
  Place      → publish a place file (.rbxl)
  Universe   → get universe info
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

_BASE = "https://apis.roblox.com"
_DS_BASE = f"{_BASE}/datastores/v1/universes"
_ASSETS_BASE = f"{_BASE}/assets/v1"
_UNIVERSES_BASE = f"{_BASE}/cloud/v2/universes"

_DEFAULT_TIMEOUT = 20.0


class OpenCloudError(Exception):
    """Raised when the Roblox Open Cloud API returns an error."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")


class OpenCloudClient:
    """
    Thin wrapper around the Roblox Open Cloud REST API.

    Parameters
    ----------
    api_key       : Open Cloud API key (defaults to ROBLOX_OPEN_CLOUD_KEY env var)
    universe_id   : Universe / experience ID (defaults to ROBLOX_UNIVERSE_ID env var)
    """

    def __init__(
        self,
        api_key: str | None = None,
        universe_id: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("ROBLOX_OPEN_CLOUD_KEY", "")
        self.universe_id = universe_id or os.environ.get("ROBLOX_UNIVERSE_ID", "")
        self._http = httpx.Client(
            timeout=_DEFAULT_TIMEOUT,
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ─── Universe ─────────────────────────────────────────────────────────────

    def get_universe(self) -> dict:
        """Return metadata for the configured universe."""
        url = f"{_UNIVERSES_BASE}/{self.universe_id}"
        return self._get(url)

    # ─── DataStore ────────────────────────────────────────────────────────────

    def list_datastores(self, prefix: str = "", limit: int = 10) -> dict:
        """List DataStores in the universe."""
        url = f"{_DS_BASE}/{self.universe_id}/standard-datastores"
        params = {"limit": limit}
        if prefix:
            params["prefix"] = prefix
        return self._get(url, params=params)

    def list_entries(self, datastore: str, prefix: str = "", limit: int = 50) -> dict:
        """List keys in a DataStore."""
        url = f"{_DS_BASE}/{self.universe_id}/standard-datastores/datastore/entries"
        params = {"datastoreName": datastore, "limit": limit}
        if prefix:
            params["prefix"] = prefix
        return self._get(url, params=params)

    def get_entry(self, datastore: str, key: str) -> tuple[Any, dict]:
        """
        Read a DataStore entry.

        Returns
        -------
        (value, metadata)  where value is the parsed JSON and metadata is a dict
        with roblox-specific headers (version, userids, attributes).
        """
        url = f"{_DS_BASE}/{self.universe_id}/standard-datastores/datastore/entries/entry"
        params = {"datastoreName": datastore, "entryKey": key}
        resp = self._http.get(url, params=params)
        self._raise_for_status(resp)
        meta = {
            "version": resp.headers.get("roblox-entry-version", ""),
            "created_time": resp.headers.get("roblox-entry-created-time", ""),
            "updated_time": resp.headers.get("last-modified", ""),
        }
        try:
            value = resp.json()
        except Exception:
            value = resp.text
        return value, meta

    def set_entry(
        self,
        datastore: str,
        key: str,
        value: Any,
        user_ids: list[int] | None = None,
        attributes: dict | None = None,
    ) -> dict:
        """Write (create or overwrite) a DataStore entry."""
        url = f"{_DS_BASE}/{self.universe_id}/standard-datastores/datastore/entries/entry"
        params = {"datastoreName": datastore, "entryKey": key}
        headers: dict = {}
        if user_ids:
            headers["roblox-entry-userids"] = json.dumps(user_ids)
        if attributes:
            headers["roblox-entry-attributes"] = json.dumps(attributes)
        resp = self._http.post(
            url,
            params=params,
            content=json.dumps(value),
            headers=headers,
        )
        self._raise_for_status(resp)
        return resp.json()

    def delete_entry(self, datastore: str, key: str) -> None:
        """Delete a DataStore entry."""
        url = f"{_DS_BASE}/{self.universe_id}/standard-datastores/datastore/entries/entry"
        params = {"datastoreName": datastore, "entryKey": key}
        resp = self._http.delete(url, params=params)
        self._raise_for_status(resp)

    def list_entry_versions(self, datastore: str, key: str, limit: int = 10) -> dict:
        """List version history for a DataStore entry."""
        url = (
            f"{_DS_BASE}/{self.universe_id}/standard-datastores/datastore/entries/entry/versions"
        )
        params = {"datastoreName": datastore, "entryKey": key, "limit": limit}
        return self._get(url, params=params)

    # ─── Place publishing ─────────────────────────────────────────────────────

    def publish_place(self, place_id: str, rbxl_path: str | Path) -> dict:
        """
        Publish a .rbxl file to a place.

        Requires the API key to have "Place → Write" scope.
        """
        path = Path(rbxl_path)
        if not path.exists():
            raise FileNotFoundError(f"Place file not found: {rbxl_path}")

        url = f"{_BASE}/universes/v1/{self.universe_id}/places/{place_id}/versions"
        params = {"versionType": "Published"}
        with open(path, "rb") as f:
            resp = self._http.post(
                url,
                params=params,
                content=f.read(),
                headers={"Content-Type": "application/octet-stream"},
            )
        self._raise_for_status(resp)
        return resp.json()

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _get(self, url: str, params: dict | None = None) -> dict:
        resp = self._http.get(url, params=params)
        self._raise_for_status(resp)
        return resp.json()

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            raise OpenCloudError(resp.status_code, resp.text[:500])

    def is_configured(self) -> bool:
        return bool(self.api_key and self.universe_id)
