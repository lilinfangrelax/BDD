#!/usr/bin/env python3
"""
step_catalog_proxy.py — Long-lived sidecar for step-catalog-aware BDD feature generation.

Connects to the teshi daemon via DaemonManifest, fetches the StepIndex via HTTP,
subscribes to WebSocket events for real-time updates, and communicates with the
AI agent via stdin/stdout JSON-RPC.

Usage:
    python scripts/step_catalog_proxy.py
    python scripts/step_catalog_proxy.py -h

Dependencies:
    - Python 3.9+
    - websockets  (optional; falls back to HTTP polling)
"""

from __future__ import annotations

import argparse
import json
import os
import select
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

MANIFEST_PATH = Path(".teshi/manifest.json")
CATALOG_ENDPOINT = "/api/v1/steps/catalog"

# Common locations to find teshi.exe
_TESHI_CANDIDATES = [
    # Default names (checked via PATH)
    "teshi",
    "teshi.exe",
    # TESHI_CLI env var
    str(Path(os.environ.get("TESHI_CLI", "")) / "teshi"),
    str(Path(os.environ.get("TESHI_CLI", "")) / "teshi.exe"),
    # Common teshi build directories (parent of skill dir is BDD repo, teshi is separate)
    "D:/dev/rust/teshi/target/debug/teshi.exe",
    "D:/dev/rust/teshi/target/release/teshi.exe",
    # Fallback: teshi in PATH (via shutil)
]


def _find_teshi() -> str:
    """Locate the teshi executable.
    Search order: explicit build paths → TESHI_CLI env → bare name in PATH.
    """
    import shutil
    for c in _TESHI_CANDIDATES:
        if not c:
            continue
        # Skip bare names here — check explicit paths first
        if c in ("teshi", "teshi.exe"):
            continue
        if Path(c).is_file():
            return c
    # Fallback: check PATH for bare names
    for c in ("teshi", "teshi.exe"):
        p = shutil.which(c)
        if p:
            return p
    return "teshi"  # last resort, will fail gracefully

EVENTS_ENDPOINT = "/api/v1/events"
POLL_INTERVAL = 5.0  # seconds between fallback polls

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

StepIndex = list[dict[str, Any]]


def eprint(*args: Any, **kwargs: Any) -> None:
    """Print to stderr (logging, not part of JSON-RPC protocol)."""
    print(*args, file=sys.stderr, flush=True, **kwargs)


def jsonrpc_error(id: Any, code: int, message: str) -> dict[str, Any]:
    return {"id": id, "error": {"code": code, "message": message}}


def jsonrpc_result(id: Any, result: Any) -> dict[str, Any]:
    return {"id": id, "result": result}


def jsonrpc_event(event: str, data: Any) -> dict[str, Any]:
    return {"event": event, "data": data}


# ---------------------------------------------------------------------------
# Manifest / daemon discovery
# ---------------------------------------------------------------------------


def discover_daemon() -> dict[str, Any] | None:
    """Read .teshi/manifest.json and return daemon info or None."""
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = json.load(f)
        port = manifest.get("port")
        pid = manifest.get("pid")
        if port is not None:
            return {"port": int(port), "pid": pid, "manifest": str(MANIFEST_PATH)}
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        eprint(f"[proxy] Manifest not found or invalid: {exc}")
    return None


# ---------------------------------------------------------------------------
# HTTP client (stdlib — no external dependency)
# ---------------------------------------------------------------------------


def http_get(port: int, path: str) -> dict[str, Any] | list[Any] | None:
    """Perform a blocking HTTP GET and return the parsed JSON response."""
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        eprint(f"[proxy] HTTP GET {url} failed: {exc}")
        return None
    except (json.JSONDecodeError, OSError) as exc:
        eprint(f"[proxy] HTTP response error from {url}: {exc}")
        return None


# ---------------------------------------------------------------------------
# WebSocket client (optional, graceful fallback)
# ---------------------------------------------------------------------------

_ws_lib = None  # lazily imported


def _import_websockets() -> bool:
    """Try importing websockets library; return True if available."""
    global _ws_lib
    if _ws_lib is not None:
        return _ws_lib is not False
    try:
        import websockets  # type: ignore[import-untyped]

        _ws_lib = websockets
        return True
    except ImportError:
        _ws_lib = False
        return False


async def _ws_listen(port: int, on_event: Callable[[dict[str, Any]], None]) -> None:
    """Listen for events via WebSocket (async). Calls on_event for each message."""
    if not _import_websockets():
        return  # fallback to polling handled by caller
    uri = f"ws://127.0.0.1:{port}{EVENTS_ENDPOINT}"
    try:
        async with _ws_lib.connect(uri) as ws:  # type: ignore[union-attr]
            async for raw in ws:  # type: ignore[union-attr]
                try:
                    msg = json.loads(raw)
                    on_event(msg)
                except json.JSONDecodeError:
                    pass
    except Exception as exc:
        eprint(f"[proxy] WebSocket connection error: {exc}")


# ---------------------------------------------------------------------------
# Core cache
# ---------------------------------------------------------------------------


class StepCache:
    """In-memory step index with lookup helpers."""

    def __init__(self) -> None:
        self.entries: StepIndex = []
        self._normalized: dict[str, int] = {}  # normalized_text -> reuse_count

    def load(self, entries: StepIndex) -> None:
        self.entries = entries
        self._build_index()

    def _build_index(self) -> None:
        self._normalized = {}
        for entry in self.entries:
            text = entry.get("text", entry.get("keyword", ""))
            norm = self._normalize(text)
            count = entry.get("reuse_count", entry.get("count", 0))
            self._normalized[norm] = self._normalized.get(norm, 0) + int(count)

    @staticmethod
    def _normalize(text: str) -> str:
        """Collapse whitespace, lowercase, strip punctuation for comparison."""
        import re

        t = re.sub(r"\s+", " ", text).strip().lower()
        t = re.sub(r"[^\w\s<>\u4e00-\u9fff]", "", t)
        return t

    def reuse_count(self, text: str) -> int:
        return self._normalized.get(self._normalize(text), 0)

    def search(self, keyword: str) -> list[dict[str, Any]]:
        kw = keyword.lower()
        results = []
        for entry in self.entries:
            text = entry.get("text", entry.get("keyword", ""))
            if kw in text.lower():
                results.append(entry)
        return results

    def top(self, n: int) -> list[dict[str, Any]]:
        sorted_entries = sorted(
            self.entries,
            key=lambda e: int(e.get("reuse_count", e.get("count", 0))),
            reverse=True,
        )
        return sorted_entries[:n]

    @property
    def total_raw_steps(self) -> int:
        return len(self.entries)


# ---------------------------------------------------------------------------
# Daemon / CLI fallback loader
# ---------------------------------------------------------------------------


def fetch_catalog_from_daemon(port: int) -> StepIndex | None:
    """Fetch step catalog from teshi daemon via HTTP."""
    data = http_get(port, CATALOG_ENDPOINT)
    if data is None:
        return None
    # The response might be wrapped in a top-level key or be an array directly.
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("entries", "steps", "catalog", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        # If the dict itself looks like a single entry list, wrap it
        if "text" in data or "keyword" in data:
            return [data]
    return None


def fetch_catalog_from_cli(project_root: str | None = None) -> StepIndex | None:
    """Fallback: run `teshi steps catalog` and parse JSON from stdout."""
    teshi = _find_teshi()
    if not teshi:
        eprint("[proxy] teshi CLI not found.")
        return None
    cmd = [teshi, "steps", "catalog", "--format", "json"]
    if project_root:
        cmd.extend(["--project-root", project_root])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,)
        if result.returncode != 0:
            eprint(f"[proxy] CLI catalog failed (rc={result.returncode}): {result.stderr}")
            return None
        data = json.loads(result.stdout)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("entries", "steps", "catalog", "data"):
                if key in data and isinstance(data[key], list):
                    return data[key]
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        eprint(f"[proxy] CLI fallback error: {exc}")
    return None


# ---------------------------------------------------------------------------
# Main sidecar
# ---------------------------------------------------------------------------


class Sidecar:
    """Reads JSON-RPC commands from stdin, writes responses to stdout."""

    def __init__(self, port: int | None, cache: StepCache) -> None:
        self.port = port
        self.cache = cache
        self._running = True
        self._event_queue: list[dict[str, Any]] = []

    def _on_ws_event(self, msg: dict[str, Any]) -> None:
        """Callback for WebSocket events."""
        self._event_queue.append(msg)
        # Also push to stdout as a server-sent event
        event_name = msg.get("event", msg.get("name", "unknown"))
        print(json.dumps({"event": event_name, "data": msg}), flush=True)

    def handle_request(self, req: dict[str, Any]) -> dict[str, Any] | None:
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        if method == "shutdown":
            self._running = False
            return jsonrpc_result(req_id, {"ok": True})

        if method == "status":
            if self.port:
                return jsonrpc_result(
                    req_id,
                    {
                        "daemon": "connected",
                        "port": self.port,
                        "cached_entries": len(self.cache.entries),
                    },
                )
            else:
                return jsonrpc_result(
                    req_id,
                    {
                        "daemon": "not_found",
                        "cached_entries": len(self.cache.entries),
                    },
                )

        if method == "top":
            n = int(params.get("n", 10))
            return jsonrpc_result(
                req_id,
                {
                    "entries": self.cache.top(n),
                    "total_raw_steps": self.cache.total_raw_steps,
                },
            )

        if method == "reuse_count":
            text = params.get("text", "")
            return jsonrpc_result(req_id, {"count": self.cache.reuse_count(text)})

        if method == "search":
            keyword = params.get("keyword", "")
            return jsonrpc_result(req_id, {"entries": self.cache.search(keyword)})

        return jsonrpc_error(req_id, -32601, f"Method not found: {method}")

    def run(self) -> None:
        """Main loop: read stdin line by line, handle requests, write responses."""
        eprint("[proxy] Sidecar started, waiting for JSON-RPC on stdin...")
        sys.stdout.reconfigure(line_buffering=True)

        # Start WebSocket listener in a daemon thread if daemon is connected
        ws_thread = None
        if self.port is not None and _import_websockets():
            def _run_ws():
                import asyncio
                try:
                    asyncio.run(_ws_listen(self.port, self._on_ws_event))
                except Exception as exc:
                    eprint(f"[proxy] WS listener exited: {exc}")

            ws_thread = threading.Thread(target=_run_ws, daemon=True)
            ws_thread.start()
            eprint(f"[proxy] WS listener started on port {self.port}")

        while self._running:
            # Use select for non-blocking read with a timeout, allowing us to
            # periodically poll for events when WebSocket is unavailable.
            try:
                rlist, _, _ = select.select([sys.stdin.buffer], [], [], POLL_INTERVAL)
            except (ValueError, TypeError, OSError):
                # On Windows, select.select() does not support stdin — fall back
                # to blocking line-by-line read.
                self._blocking_read_loop()
                return

            if rlist:
                line = sys.stdin.buffer.readline()
                if not line:
                    eprint("[proxy] stdin closed, shutting down.")
                    break
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    req = json.loads(line)
                except json.JSONDecodeError as exc:
                    eprint(f"[proxy] Invalid JSON: {exc}")
                    resp = jsonrpc_error(None, -32700, f"Parse error: {exc}")
                    print(json.dumps(resp, ensure_ascii=False), flush=True)
                    continue

                resp = self.handle_request(req)
                if resp is not None:
                    print(json.dumps(resp, ensure_ascii=False), flush=True)

        eprint("[proxy] Shutdown complete.")

    def _blocking_read_loop(self) -> None:
        """Fallback: blocking readline loop for environments without select support."""
        while self._running:
            line = sys.stdin.buffer.readline()
            if not line:
                eprint("[proxy] stdin closed, shutting down.")
                break
            line = line.decode("utf-8").strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as exc:
                eprint(f"[proxy] Invalid JSON: {exc}")
                resp = jsonrpc_error(None, -32700, f"Parse error: {exc}")
                print(json.dumps(resp, ensure_ascii=False), flush=True)
                continue

            resp = self.handle_request(req)
            if resp is not None:
                print(json.dumps(resp, ensure_ascii=False), flush=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Step catalog proxy — JSON-RPC sidecar for BDD step reuse.",
    )
    parser.add_argument(
        "--manifest",
        default=str(MANIFEST_PATH),
        help=f"Path to DaemonManifest (default: {MANIFEST_PATH})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Daemon port (overrides manifest lookup)",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Project root directory (for CLI fallback; default: cwd)",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    cache = StepCache()

    # Discover daemon
    port = args.port
    daemon_info = None
    if port is None:
        daemon_info = discover_daemon()
        if daemon_info:
            port = daemon_info["port"]

    # Load catalog
    entries = None
    if port is not None:
        eprint(f"[proxy] Fetching catalog from daemon on port {port}...")
        entries = fetch_catalog_from_daemon(port)
        if entries is not None:
            eprint(f"[proxy] Loaded {len(entries)} entries from daemon.")
    else:
        eprint("[proxy] No daemon detected, falling back to CLI...")

    if entries is None:
        eprint("[proxy] Trying CLI fallback: teshi steps catalog")
        entries = fetch_catalog_from_cli(args.project_root)
        if entries is not None:
            eprint(f"[proxy] Loaded {len(entries)} entries from CLI.")
        else:
            eprint("[proxy] No step index available — starting with empty cache.")

    if entries:
        cache.load(entries)

    # Start sidecar
    sidecar = Sidecar(port=port, cache=cache)
    sidecar.run()


if __name__ == "__main__":
    main()
