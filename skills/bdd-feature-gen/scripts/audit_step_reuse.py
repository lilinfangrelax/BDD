#!/usr/bin/env python3
"""
audit_step_reuse.py — Audit BDD .feature files for step definition reuse rate.

Parses .feature files to extract Given/When/Then/And/But steps, compares them
against the teshi step index, and produces a reuse report.

Known limitation: The Rust Gherkin parser (teshi-gherkin) stops indexing steps
after encountering a multi-line step continuation (e.g. a step whose body
spans multiple lines). Steps after that break are NOT in the catalog and will
be reported as "not reused" even though they exist in the source file. To get a
complete catalog, fix multi-line steps in your .feature files or contribute a
multi-line parser fix to teshi-gherkin.

Usage:
    python scripts/audit_step_reuse.py <path> [<path> ...]
    python scripts/audit_step_reuse.py <directory> --recursive
    python scripts/audit_step_reuse.py <file.feature> --format json --threshold 70

Exit codes:
    0  — reuse rate >= threshold (or no steps found)
    1  — runtime error (e.g. cannot connect to proxy, cannot read file)
    2  — parameter error (invalid arguments)
    3  — reuse rate < threshold
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# Common locations to find teshi.exe
_TESHI_CANDIDATES = [
    # Default names (checked via PATH)
    "teshi",
    "teshi.exe",
    # TESHI_CLI env var
    str(Path(os.environ.get("TESHI_CLI", "")) / "teshi"),
    str(Path(os.environ.get("TESHI_CLI", "")) / "teshi.exe"),
    # Common teshi build directories
    "D:/dev/rust/teshi/target/debug/teshi.exe",
    "D:/dev/rust/teshi/target/release/teshi.exe",
]


def _find_teshi() -> str:
    """Locate the teshi executable.
    Search order: explicit build paths → TESHI_CLI env → bare name in PATH.
    """
    import shutil
    for c in _TESHI_CANDIDATES:
        if not c:
            continue
        if c in ("teshi", "teshi.exe"):
            continue
        if Path(c).is_file():
            return c
    for c in ("teshi", "teshi.exe"):
        p = shutil.which(c)
        if p:
            return p
    return "teshi"  # last resort


# ---------------------------------------------------------------------------
# Feature file parsing
# ---------------------------------------------------------------------------

STEP_KEYWORDS = {
    # English
    "Given", "When", "Then", "And", "But",
    # Chinese (简体中文)
    "假如", "假设", "当", "那么", "并且", "但是",
}
STEP_PATTERN = re.compile(
    r"^\s*(?P<keyword>"
    + "|".join(re.escape(k) for k in sorted(STEP_KEYWORDS, key=len, reverse=True))
    + r")\s+(?P<text>.+)$",
    re.IGNORECASE,
)


def extract_steps_from_feature(text: str) -> list[dict[str, str]]:
    """Parse .feature text and extract step lines with keyword + body text."""
    steps = []
    for line in text.splitlines():
        m = STEP_PATTERN.match(line)
        if m:
            steps.append({
                "keyword": m.group("keyword").capitalize(),
                "text": m.group("text").strip(),
            })
    return steps


def find_feature_files(paths: list[str], recursive: bool) -> list[Path]:
    """Collect .feature files from the given paths (file or directory)."""
    files: list[Path] = []
    for p in paths:
        pp = Path(p)
        if pp.is_file():
            if pp.suffix.lower() == ".feature":
                files.append(pp)
            else:
                print(f"Warning: skipping non-.feature file: {pp}", file=sys.stderr)
        elif pp.is_dir():
            glob_fn = pp.rglob if recursive else pp.glob
            for found in glob_fn("*.feature"):
                files.append(found)
        else:
            print(f"Warning: path not found: {pp}", file=sys.stderr)
    return files


# ---------------------------------------------------------------------------
# Proxy interaction
# ---------------------------------------------------------------------------


def _start_proxy(port: int | None = None) -> subprocess.Popen | None:
    proxy_script = Path(__file__).parent / "step_catalog_proxy.py"
    if not proxy_script.is_file():
        return None
    cmd = [sys.executable, str(proxy_script)]
    if port is not None:
        cmd.extend(["--port", str(port)])
    try:
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, bufsize=1)
    except OSError as exc:
        print(f"Error starting proxy: {exc}", file=sys.stderr)
        return None


def _proxy_request(proc: subprocess.Popen, method: str,
                   params: dict[str, Any] | None = None,
                   req_id: int = 1) -> dict[str, Any] | None:
    if proc.stdin is None or proc.stdout is None:
        return None
    req = {"id": req_id, "method": method}
    if params:
        req["params"] = params
    try:
        proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        return json.loads(line) if line else None
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Proxy communication error: {exc}", file=sys.stderr)
        return None


def _shutdown_proxy(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        _proxy_request(proc, "shutdown", req_id=999)
    except Exception:
        pass
    for _ in range(2):
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def get_catalog_via_proxy() -> list[dict[str, Any]] | None:
    proc = _start_proxy()
    if proc is None:
        return None
    try:
        resp = _proxy_request(proc, "top", {"n": 1000000}, req_id=1)
        if resp and "result" in resp:
            return resp["result"].get("entries")
    finally:
        _shutdown_proxy(proc)
    return None


def get_catalog_via_cli(project_root: str | None = None) -> list[dict[str, Any]] | None:
    teshi = _find_teshi()
    cmd = [teshi, "steps", "catalog", "--format", "json"]
    if project_root:
        cmd.extend(["--project-root", project_root])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"CLI fallback error: {exc}", file=sys.stderr)
        return None
    if result.returncode != 0:
        print(f"CLI catalog failed (rc={result.returncode}): {result.stderr.strip()}", file=sys.stderr)
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"CLI output parse error: {exc}", file=sys.stderr)
        return None
    # Normalise response: may be array or dict with entries key
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("entries", "steps", "catalog", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return None


def load_catalog() -> list[dict[str, Any]] | None:
    """Load step catalog — try proxy first, then CLI."""
    entries = get_catalog_via_proxy()
    if entries is not None:
        return entries
    print("Proxy unavailable, falling back to CLI...", file=sys.stderr)
    return get_catalog_via_cli()


# ---------------------------------------------------------------------------
# Normalisation & indexing
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Collapse whitespace → lowercase → strip punctuation (except <> and CJK)."""
    t = re.sub(r"\s+", " ", text).strip().lower()
    t = re.sub(r"[^\w\s<>\u4e00-\u9fff]", "", t)
    return t


def build_normalized_index(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Build {normalized_text: total_reuse_count} from catalog entries."""
    index: dict[str, int] = {}
    for entry in entries:
        text = entry.get("text", "")
        count = int(entry.get("count", 1))
        norm = _normalize(text)
        index[norm] = index.get(norm, 0) + count
    return index


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def audit_feature_files(
    files: list[Path],
    catalog_index: dict[str, int],
) -> dict[str, Any]:
    """Compare steps in .feature files against the catalog index.

    NOTE: The Rust Gherkin parser stops indexing after a multi-line step
    continuation.  If a step is not in the catalog it may be genuinely new,
    or it may be a step the parser skipped.  The `new_step_texts` list shows
    what was not found; manually review whether those are truly new.
    """
    total_steps = 0
    reused_steps = 0
    file_reports: list[dict[str, Any]] = []
    all_new_texts: list[str] = []

    for fpath in files:
        try:
            text = fpath.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Error reading {fpath}: {exc}", file=sys.stderr)
            continue

        steps = extract_steps_from_feature(text)
        file_reused = 0
        file_new_texts: list[str] = []

        for step in steps:
            norm = _normalize(step["text"])
            if norm in catalog_index:
                file_reused += 1
            else:
                file_new_texts.append(f"{step['keyword']} {step['text']}")

        file_reports.append({
            "file": str(fpath),
            "total_steps": len(steps),
            "reused_steps": file_reused,
            "new_steps": len(steps) - file_reused,
            "new_step_texts": file_new_texts,
        })
        total_steps += len(steps)
        reused_steps += file_reused
        all_new_texts.extend(file_new_texts)

    reuse_rate = (reused_steps / total_steps * 100.0) if total_steps > 0 else 100.0

    return {
        "total_steps": total_steps,
        "reused_steps": reused_steps,
        "new_steps": total_steps - reused_steps,
        "reuse_rate": round(reuse_rate, 2),
        "file_reports": file_reports,
        "new_step_texts": all_new_texts,
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_text_report(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("BDD Step Reuse Audit Report")
    lines.append("=" * 60)
    lines.append("")

    for fr in result["file_reports"]:
        lines.append(f"File: {fr['file']}")
        lines.append(f"  Total steps : {fr['total_steps']}")
        lines.append(f"  Reused steps: {fr['reused_steps']}")
        lines.append(f"  New steps   : {fr['new_steps']}")
        if fr["new_step_texts"]:
            lines.append("  New step texts (not found in catalog):")
            for t in fr["new_step_texts"]:
                lines.append(f"    - {t}")
        lines.append("")

    lines.append("-" * 60)
    lines.append(f"Total steps      : {result['total_steps']}")
    lines.append(f"Reused steps     : {result['reused_steps']}")
    lines.append(f"New steps        : {result['new_steps']}")
    lines.append(f"Reuse rate       : {result['reuse_rate']}%")
    lines.append("-" * 60)
    if result.get("new_steps", 0) > 0:
        lines.append("")
        lines.append("Note: Steps reported as 'new' may be genuinely new, or they may be")
        lines.append("steps the Rust Gherkin parser skipped after encountering a multi-line")
        lines.append("step continuation.  Review the 'New step texts' above to decide.")
    lines.append("")
    return "\n".join(lines)


def format_json_report(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit BDD .feature files for step definition reuse rate.",
    )
    parser.add_argument("path", nargs="+", help="Feature file(s) or directory to scan")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="Recursively scan directories for .feature files")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                        help="Output format (default: text)")
    parser.add_argument("--threshold", "-t", type=float, default=70.0,
                        help="Minimum reuse rate %% (default: 70). Exit code 3 if below.")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    files = find_feature_files(args.path, args.recursive)
    if not files:
        print("No .feature files found.", file=sys.stderr)
        sys.exit(0)

    entries = load_catalog()
    if not entries:
        print("Error: could not load step catalog.", file=sys.stderr)
        sys.exit(1)

    index = build_normalized_index(entries)
    result = audit_feature_files(files, index)

    if args.format == "json":
        print(format_json_report(result))
    else:
        print(format_text_report(result))

    rate = result["reuse_rate"]
    if rate < args.threshold:
        sys.exit(3)


if __name__ == "__main__":
    main()
