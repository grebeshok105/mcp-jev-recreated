"""Layered local cache for the knowledge base.

  resource bytes ──content-hash──▶ static passport (per resource file/key)
                  ──capture-key──▶ capture bundle (frames + measurements)
                  ──visual-key───▶ visual analysis (merged semantics)

Keys compose the layers so upstream changes invalidate only what depends on
them:

  static_key  = sha(source | content_hash | provider_version | schema_version)
  capture_key = sha(static_key | capture_version)
  visual_key  = sha(static_key | capture_version | analysis_version | pass_config)
  query_key   = sha(query | catalog_fingerprint | ranker_version)

Plain filesystem storage — no database. JSON files under data/cache/.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

CACHE_SCHEMA_VERSION = 1


def _sha(*parts: Any) -> str:
    blob = json.dumps(parts, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


class LayeredCache:
    def __init__(self, root: str):
        self.root = root
        for layer in ("static", "capture", "visual", "query"):
            os.makedirs(os.path.join(root, layer), exist_ok=True)

    # ---------------------------------------------------------------- keys

    def static_key(self, source: str, content_hash: str,
                   provider_version: int, schema_version: int) -> str:
        return _sha("static", source, content_hash,
                    provider_version, schema_version, CACHE_SCHEMA_VERSION)

    def capture_key(self, static_key: str, capture_version: int) -> str:
        return _sha("capture", static_key, capture_version, CACHE_SCHEMA_VERSION)

    def visual_key(self, static_key: str, capture_version: int,
                   analysis_version: int, pass_config: str) -> str:
        return _sha("visual", static_key, capture_version,
                    analysis_version, pass_config, CACHE_SCHEMA_VERSION)

    def query_key(self, query: str, catalog_fingerprint: str,
                  ranker_version: int) -> str:
        return _sha("query", query, catalog_fingerprint,
                    ranker_version, CACHE_SCHEMA_VERSION)

    # ------------------------------------------------------------- storage

    def _path(self, layer: str, key: str) -> str:
        if not key or "/" in key or ".." in key:
            raise ValueError(f"bad cache key: {key!r}")
        return os.path.join(self.root, layer, key + ".json")

    def get(self, layer: str, key: str) -> dict[str, Any] | None:
        path = self._path(layer, key)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None  # corrupt cache entry = miss, never fatal

    def put(self, layer: str, key: str, payload: dict[str, Any]) -> None:
        payload = dict(payload)
        payload["_cached_at"] = time.time()
        path = self._path(layer, key)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    def invalidate(self, layer: str, key: str) -> bool:
        path = self._path(layer, key)
        if os.path.isfile(path):
            os.remove(path)
            return True
        return False

    def stats(self) -> dict[str, int]:
        out = {}
        for layer in ("static", "capture", "visual", "query"):
            d = os.path.join(self.root, layer)
            out[layer] = sum(1 for f in os.listdir(d) if f.endswith(".json"))
        return out


def catalog_fingerprint(resource_ids_and_hashes: dict[str, str]) -> str:
    """Fingerprint of the catalog's content — query cache invalidates when
    the resource set or any resource's content changes."""
    return _sha("catalog", sorted(resource_ids_and_hashes.items()))
