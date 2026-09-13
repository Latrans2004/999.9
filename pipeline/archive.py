"""Content-addressed upstream bytes; no credentials, no destructive overwrites."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from pathlib import Path


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def save(root: Path, source: str, body: bytes, *, url: str, query=None, suffix=".json"):
    query = query or {}
    identity = hashlib.sha256(encode({"url": url, "query": query}) + body).hexdigest()
    folder = root / "data" / "raw" / source
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (identity + suffix)
    sidecar = folder / (identity + ".meta.json")
    metadata = {"source": source, "url": url, "query": query,
                "retrieved_at": now(), "sha256": hashlib.sha256(body).hexdigest(),
                "path": target.relative_to(root).as_posix()}
    if sidecar.exists():
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        if target.read_bytes() != body:
            raise ValueError("Raw archive hash collision or corrupt file")
    else:
        target.write_bytes(body)
        sidecar.write_bytes(encode(metadata))
    return metadata
