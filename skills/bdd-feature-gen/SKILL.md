---
name: bdd-feature-gen
description: Generate BDD feature files with step-catalog-aware reuse using teshi daemon as a sidecar. Load this skill when generating .feature files from test cases.
license: MIT
metadata:
  author: openspec
  version: "1.0"
---

# bdd-feature-gen

Generate BDD feature files with awareness of existing step definitions via the teshi step index.

## Overview

This skill connects to the teshi daemon via a long-lived sidecar process (`step_catalog_proxy.py`). The sidecar:
1. Detects the teshi daemon via `DaemonManifest` (`.teshi/manifest.json`)
2. Fetches the full StepIndex via `GET /api/v1/steps/catalog`
3. Subscribes to WebSocket `/api/v1/events` for real-time `step-index-updated` events
4. Maintains an in-memory cache of normalized step texts with reuse counts
5. Communicates with the AI agent via stdin/stdout JSON-RPC (MCP-compatible)

## Sidecar Protocol

### Starting the sidecar

```bash
python scripts/step_catalog_proxy.py
```

The sidecar starts, connects to the daemon, and waits for JSON-RPC commands on stdin.

### JSON-RPC over stdin/stdout

**Request** (agent → sidecar, one JSON object per line):
```json
{"id": 1, "method": "top", "params": {"n": 10}}
{"id": 2, "method": "reuse_count", "params": {"text": "用户已登录系统"}}
{"id": 3, "method": "search", "params": {"keyword": "登录"}}
{"id": 4, "method": "status"}
{"id": 5, "method": "shutdown"}
```

**Response** (sidecar → agent, one JSON object per line):
```json
{"id": 1, "result": {"entries": [...], "total_raw_steps": 1688}}
{"id": 2, "result": {"count": 45}}
{"id": 4, "result": {"daemon": "connected", "port": 7890, "cached_entries": 860}}
{"id": 5, "result": {"ok": true}}
```

**Events** (sidecar → agent, no `id` field indicates push):
```json
{"event": "step-index-updated", "data": {"delta": "+5 entries"}}
```

### Supported Methods

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `top` | `n: int` | `{entries: [...]}` | Top N most-frequent steps |
| `reuse_count` | `text: str` | `{count: int}` | Reuse count for a step text |
| `search` | `keyword: str` | `{entries: [...]}` | Search steps containing keyword |
| `status` | — | `{daemon, port, cached}` | Connection status summary |
| `shutdown` | — | `{ok: true}` | Graceful shutdown |

### Shutdown

Send `{"method": "shutdown"}` to gracefully disconnect. When the agent process exits, stdin EOF triggers automatic cleanup.

## Step Reuse Rules

When generating .feature files, follow these rules:

1. **Reuse first**: Before writing a new step, query the catalog with `reuse_count` or `search`. If a semantically equivalent step exists, reuse it verbatim.
2. **No variants**: Do not create variants of existing steps (e.g., if "用户已登录系统" exists, do not add "用户已登录到系统中").
3. **Parameterize**: New steps MUST use `<param>` placeholders for variable data. Example: `When 用户创建任务"<task_name>"` not `When 用户创建任务"修复问题"`.
4. **Extend over create**: When semantics are close, extend an existing step with parameters rather than creating a new one.
5. **Audit after generation**: Run `audit_step_reuse.py <generated.feature>` to check reuse rate. Target: ≥ 70%.

## Feature 文件格式规范

输出的 `.feature` 文件必须遵循以下规范（详见 references/）：

| 规范 | 文件 | 适用范围 |
|------|------|---------|
| BDD Feature 文件颗粒度规范 | `references/bdd-granularity-convention.md` | UI 自动化（Playwright + Behave + WinUI3） |
| API BDD Feature 文件规范 | `references/api-bdd-granularity-convention.md` | API 自动化（Behave + Jinja2） |

### 核心规则速查

**UI Feature:**
- 三层结构：Feature → Rule(可选) → Scenario
- 每个 Scenario 只有 1 个 When（单一业务决策）
- Then 断言 ≤ 3 个，总步骤 ≤ 10 步（建议 ≤ 7）
- Given 自包含，不依赖其他 Scenario
- Step 使用业务语言，禁止控件名、ID、XPath、API 路径

**API Feature:**
- 所有 Step 加 `【API】` 前缀
- Given 描述数据状态，不描述接口调用过程
- Then 描述业务结果，不写 HTTP 状态码/响应字段
- Background 只放登录态
- Scenario 名称与对应 UI Feature 保持一致

**两者通用:**
- 文件名：`{业务对象}_{核心动词}.feature`
- 每文件 5–15 个 Scenario，≤ 200 行
- Feature 描述包含用户故事（作为/我希望/以便）
- 先查 Step Catalog，禁止语义等价变体

## Fallback

If teshi daemon is not running, the sidecar degrades gracefully:
- `status` returns `{daemon: "not_found"}`
- Methods fall back to subprocess `teshi steps catalog`
- No real-time updates (no WebSocket)
- Each method call invokes a CLI subprocess
