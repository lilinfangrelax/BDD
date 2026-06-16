## Context

Teshi 项目已经拥有实现工程级一致性状态的关键基础设施：

- **StepIndex**（`src/step_index.rs`）：全量步骤归一化索引，支持复用统计和 Top N 查询
- **App 集成**（`src/app.rs:1602`）：AI Agent 上下文自动注入 Top 8 最常用步骤
- **Daemon HTTP API**（`crates/teshi-daemon/src/server.rs`）：基于 axum 的 REST 服务，已有的步骤相关端点（`/api/v1/steps/statuses`、`/api/v1/locator/sync-step` 等）
- **WebSocket 事件总线**（`crates/teshi-runtime/src/events.rs`）：`RuntimeEvents` 通过 broadcast channel 推送事件，WebSocket 端点 `GET /api/v1/events` 已存在
- **文件变更检测**（`crates/teshi-runtime/src/watcher.rs`）：`notify` 文件系统监控，变更后通过 `emit_feature_refresh` 推送 `feature-refreshed` 事件

当前瓶颈：StepIndex 位于主二进制 `src/step_index.rs`，daemon 无法访问。文件变更后不会自动重建 StepIndex。

Skill 侧当前无任何状态代理机制，每次需通过 CLI 子进程全量查询。

## Goals / Non-Goals

**Goals:**

1. **StepIndex 下沉到 `teshi-gherkin` crate**，使其可被 daemon/runtime/主二进制三方共享
2. **Daemon 新增 `GET /api/v1/steps/catalog` 端点**，输出完整 StepIndex JSON
3. **文件变更联动 StepIndex 重建**，变更后自动重建并通过 WebSocket 推送 `step-index-updated` 事件
4. **Skill 作为状态代理**，通过 HTTP + WebSocket 连接 daemon，维护本地缓存
5. **端到端可演示**：展示 skill（持久的 StepIndex 缓存）与 CLI（一次性查询）的差距

**Non-Goals:**

- 不修改 teshi 的 TUI 模式
- 不修改现有的 StepIndex 构建逻辑（只移动位置）
- 不修改 `01 制定Feature文件规范/` 下的任何文档
- Skill 侧不做全量 Gherkin 解析（依赖 daemon）

## Decisions

### Decision 1：StepIndex 下沉到 `crates/teshi-gherkin`

| 方案 | 说明 | 评价 |
|------|------|------|
| **A. 移到 `teshi-gherkin`** | `crates/teshi-gherkin/src/` 已有 `BddProject`、`parse_feature` 等核心类型，StepIndex 的 `build()` 方法依赖 `BddProject`，放在这里最自然 | ✅ 依赖链最短，daemon → runtime → gherkin 链路上所有组件都能访问 |
| B. 新 crate `teshi-step-index` | 可以独立演进，但 crate 内容太少，过度工程 | ❌ |
| C. 留在主二进制，通过环境变量/进程间通信暴露 | 复杂，且无法被 daemon 直接使用 | ❌ |

**选择 A**。StepIndex 的核心依赖就是 `BddProject`，与 `teshi-gherkin` 的职责一致。移动后更新所有引用点（`src/app.rs`、`src/step_index.rs` 本身、测试代码）。

### Decision 2：Daemon API 端点设计

```
GET /api/v1/steps/catalog?min_count=N&top=N&no_locations=true
```

响应 JSON：

```json
{
  "project_root": "D:/projects/my-bdd-project",
  "total_raw_steps": 1688,
  "unique_normalized": 860,
  "num_features": 25,
  "generated_at": "2026-06-13T17:00:00+08:00",
  "entries": [
    {
      "text": "用户已登录系统",
      "normalized": "用户已登录系统",
      "count": 45,
      "locations": [
        {"feature": "auth/login.feature", "scenario": "有效凭据登录", "line": 10}
      ]
    }
  ]
}
```

实现模式参照已有的 `api_step_statuses`（`server.rs:451`）：
1. 从 `TeshiRuntime` 读取项目根目录
2. 扫描 `.feature` 文件
3. 构建 `BddProject` + `StepIndex`
4. 序列化为 JSON

### Decision 3：StepIndex 联动文件变更 → WebSocket 事件

已有的流程链路：

```
notify::Watcher → emit_feature_refresh → events.emit("feature-refreshed", ...)
```

在 `emit_feature_refresh`（或并行 hook）中增加：

```rust
// 在 emit_feature_refresh 中或之后
pub fn rebuild_and_emit_step_index(events: &RuntimeEvents, path: &Path, project_root: &Path) {
    // 扫描 project_root 下所有 .feature 文件
    let project = build_project(project_root);
    let index = StepIndex::build(&project);
    events.emit("step-index-updated", &index);
}
```

注意：当前 `emit_feature_refresh` 只刷新单个 feature 文件。StepIndex 是全量重建（需扫描所有 `.feature` 文件）。为避免每次变更都全量扫描，有两种策略：

| 方案 | 说明 | 评价 |
|------|------|------|
| **A. 变更时全量重建** | 每次 `feature-refreshed` 事件后全量扫描所有 feature 文件重建 StepIndex | ✅ 实现简单，StepIndex::build O(n) 在中等规模项目可接受 |
| B. 增量更新 | 只更新变更文件对索引的影响 | ❌ 复杂度高，需要 diff 算法；可作为后续优化 |

**选择 A**。初期实现全量重建，通过 `--top` 和 `--min-count` 控制透出数据量。

### Decision 4：Skill 架构 —— Sidecar 模式（JSON-RPC over Stdin/Stdout）

Skill 不是一个"按需调用的脚本集"，而是一个 **long-lived sidecar 进程**。Agent 启动它一次，之后所有交互通过 stdin/stdout 的 JSON-RPC 消息流完成。这完全对标 MCP（Model Context Protocol）的标准模式。

```
AI Agent                                   Teshi Daemon
   │                                            │
   ├── spawn step_catalog_proxy.py              │
   │        │                                   │
   │        ├── DaemonManifest 检测 ───────────→ │
   │        ├── HTTP GET /api/v1/steps/catalog → │
   │        │        ←─── JSON StepIndex ─────── │
   │        ├── WS /api/v1/events ─────────────→ │
   │        │        ←─── step-index-updated ─── │
   │        │                                   │
   │        ├── 初始化完成，进入事件循环           │
   │        │    等待 stdin 上的 JSON-RPC         │
   │        │                                   │
   ├── stdin: {"id":1, "method":"top",          │
   │           "params":{"n":10}}               │
   │        │                                   │
   │        ├── 查询内存缓存（无 IO 无锁）        │
   │        │                                   │
   ├── stdout: {"id":1, "result":              │
   │           {"entries":[...]}}               │
   │                                            │
   ├── 进程退出                                 │
   │        │                                   │
   │        ├── stdin EOF（SIGPIPE/SIGTERM）     │
   │        ├── WS 优雅关闭 ──────────────────→ │
   │                                            │
```

**通信协议**：逐行 JSON（NDJSON），每行一个完整的 JSON-RPC 消息。

请求（Agent → Sidecar · stdin）：
```json
{"id": 1, "method": "top", "params": {"n": 10}}
{"id": 2, "method": "reuse_count", "params": {"text": "用户已登录系统"}}
{"id": 3, "method": "search", "params": {"keyword": "登录"}}
{"id": 4, "method": "status"}
```

响应（Sidecar → Agent · stdout）：
```json
{"id": 1, "result": {"entries": [...], "total_raw_steps": 1688}}
{"id": 2, "result": {"count": 45}}
{"id": 4, "result": {"daemon": "connected", "port": 7890, "cached_entries": 860}}
```

事件（Sidecar → Agent · stdout，无 id 表示推送）：
```json
{"event": "step-index-updated", "data": {"delta": "+5 entries"}}
```

**支持的方法**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `top` | `n: int` | `{entries: [...]}` | 前 N 个高频步骤 |
| `reuse_count` | `text: str` | `{count: int}` | 某步骤的复用次数 |
| `search` | `keyword: str` | `{entries: [...]}` | 搜索包含关键字的步骤 |
| `status` | — | `{daemon, port, cached}` | 连接状态和缓存摘要 |
| `shutdown` | — | `{ok: true}` | 优雅关闭（断开 WS） |

**降级策略**：

| 场景 | 行为 |
|------|------|
| daemon 运行中 | HTTP 全量初始 + WebSocket 增量更新 |
| daemon 未运行 | 启动 sidecar 时返回 `status: {daemon: "not_found"}`，方法调用降级为子进程 CLI `teshi steps catalog` |
| WebSocket 断连 | 自动重连（3 次，间隔 1s），重连成功后全量拉取一次确保一致性 |

### Decision 5：StepIndex 的数据移动

当前 `StepIndex` 在 `src/step_index.rs`。移动后：

- **新位置**：`crates/teshi-gherkin/src/step_index.rs`
- **公开**：`StepIndex`、`StepLocation`、`StepIndex::build`、`most_common`、`reuse_count`、`is_empty`、`normalize`
- **主二进制引用**：`src/step_index.rs` → `use teshi_gherkin::StepIndex`（删除原文件）
- **`teshi-gherkin` 的 lib.rs** 需要导出新模块

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|---------|
| `StepIndex::build` 全量扫描，大型项目性能 | `--top N` 控制输出；增量更新作为后续优化 |
| daemon 未运行时 skill 不可用 | 降级到 `--mode=cli`，保证可用性 |
| WebSocket 断连时状态不一致 | 代理检测到断连后自动重连并全量拉取一次 |
| 文件变更频繁时 StepIndex 重建过密 | 在 `emit_feature_refresh` 中加 debounce（300ms） |
| Skill 需要启动 daemon（权限、端口占用） | `DaemonManifest` 已有端口发现机制；由用户按需启动 |
