#!/usr/bin/env python3
"""
demo_sidecar.py — End-to-end demonstration of the bdd-feature-gen skill.

Shows the complete flow:
1. Locate teshi CLI / daemon
2. Start sidecar and connect via JSON-RPC
3. Query step catalog (top steps, reuse count, search)
4. Audit a .feature file for step reuse
5. Shut down

Usage:
    python scripts/demo_sidecar.py <project-root>
    python scripts/demo_sidecar.py D:/dev/rust/teshi
"""
import json, subprocess, sys, time, threading
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent  # .agents/skills/bdd-feature-gen
PROXY = SKILL_DIR / "scripts" / "step_catalog_proxy.py"
AUDIT = SKILL_DIR / "scripts" / "audit_step_reuse.py"


def run_demo(project_root: str) -> None:
    print("=" * 60)
    print("bdd-feature-gen — Sidecar Demo")
    print("=" * 60)

    # ── Find a .feature file for audit ──
    feature_files = list(Path(project_root).rglob("*.feature"))
    if not feature_files:
        print(f"No .feature files found in {project_root}")
        sys.exit(1)
    demo_feature = feature_files[0]
    print(f"\n1. Demo feature file: {demo_feature}")

    # ── Start sidecar ──
    print(f"\n2. Starting sidecar: python {PROXY.name}")
    print(f"   (from {project_root})")
    proxy = subprocess.Popen(
        [sys.executable, str(PROXY)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1,
        cwd=project_root,
    )
    time.sleep(1)

    def send(method: str, params: dict | None = None, req_id: int = 1) -> dict:
        req = {"id": req_id, "method": method}
        if params:
            req["params"] = params
        proxy.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        proxy.stdin.flush()
        line = proxy.stdout.readline()
        return json.loads(line)

    # ── Status ──
    resp = send("status", req_id=1)
    daemon_status = resp["result"].get("daemon", "unknown")
    cached = resp["result"].get("cached_entries", 0)
    print(f"   Status: daemon={daemon_status}, cached={cached} entries")

    # ── Top 5 ──
    resp = send("top", {"n": 5}, req_id=2)
    entries = resp["result"].get("entries", [])
    print(f"\n3. Top 5 most-reused steps:")
    for e in entries:
        print(f"   ({e['count']}x) {e['text'][:70]}")

    # ── Search ──
    resp = send("search", {"keyword": "login"}, req_id=3)
    found = resp["result"].get("entries", [])
    print(f"\n4. Search 'login': {len(found)} matching steps")
    for e in found[:3]:
        print(f"   ({e['count']}x) {e['text'][:70]}")

    # ── Shutdown ──
    send("shutdown", req_id=99)
    proxy.wait(timeout=5)
    print(f"\n5. Sidecar shut down.")

    # ── Audit a feature file ──
    print(f"\n6. Running audit on {demo_feature.name}:")
    result = subprocess.run(
        [sys.executable, str(AUDIT), "--format", "text", str(demo_feature)],
        capture_output=True, text=True, timeout=30, cwd=project_root,
    )
    for line in result.stdout.split("\n"):
        if any(kw in line for kw in ("Reuse rate", "Total steps", "File:")):
            print(f"   {line.strip()}")

    print(f"\n{'=' * 60}")
    print("Demo complete. The skill is ready for use.")
    print("Load it: load_skill(\"bdd-feature-gen\")")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/demo_sidecar.py <project-root>")
        print("Example: python scripts/demo_sidecar.py D:/dev/rust/teshi")
        sys.exit(2)
    run_demo(sys.argv[1])
