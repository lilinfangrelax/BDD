## Why

BDD Feature 生成的竞争壁垒不在 Prompt 工程，而在于**应用级状态一致性**。

通用 Agent + 工具（Skill）的方案有结构性缺陷：每次生成 Feature 文件都是一锤子买卖。当生成第 101 个文件时，它记不住前 100 个文件里已经定义过哪些 Step Definitions。Prompt 注入 Step Catalog 只能缓解、不能根治，因为缺少**增量更新**和**一致性保障**。

Teshi 已经解决了这个问题——`StepIndex` 随项目加载常驻内存，每次 AI 上下文构建时自动注入 Top N 复用步骤，每次 `rebuild_project_views` 时增量重建索引。这种**工程级的一致性视角**是 teshi 相比通用 Agent 的核心差异化优势。

本变更的目标：**将 teshi 的 Step Index 能力通过 Daemon 协议暴露为可持久连接的 Skill，使外部 AI Agent 不再通过 CLI 一次性查询，而是通过 HTTP API + WebSocket 事件流获得与 teshi TUI 内部一致的、增量更新的步骤索引状态**。这将成为 teshi 项目最有说服力的架构亮点——展示"专用 Agent 的应用状态"如何碾压"通用 Agent + Prompt"。

## What Changes

- **Teshi 侧 — StepIndex 下沉到 `teshi-gherkin` crate**：将 `StepIndex` 从 `src/step_index.rs`（主二进制）移到 `crates/teshi-gherkin/src/`，使其可被 daemon 和 runtime 共享使用。
- **Teshi 侧 — 新增 Daemon API 端点 `GET /api/v1/steps/catalog`**：返回当前项目的完整 Step Index JSON，支持 `?min_count=N&top=N&no_locations=true` 查询参数。
- **Teshi 侧 — 新增 WebSocket 事件 `step-index-updated`**：当 `.feature` 文件发生变更（增/删/改）时，自动重建 StepIndex 并通过 WebSocket 推送增量事件。
- **Teshi 侧 — 文件变更联动 StepIndex 重建**：集成到已有的 `emit_feature_refresh` 流程中，Feature 文件变更后自动触发 StepIndex 重建并推送事件。
- **Skill 侧 — 创建 `bdd-feature-gen` skill**：作为状态代理，通过 HTTP + WebSocket 连接 teshi daemon，维护本地缓存的 StepIndex，提供实时查询接口。
- **Skill 附带脚本**：`scripts/step_catalog_proxy.py`（daemon 连接与状态缓存）和 `scripts/audit_step_reuse.py`（审计复用率，可作为离线备选）。

## Capabilities

### New Capabilities
- `step-index-service`: Teshi daemon 提供的 StepIndex 服务，包含 REST API（查询）和 WebSocket 事件流（增量更新），是 skill 状态代理的后端基础设施
- `step-index-proxy-skill`: 位于 `.agents/skills/bdd-feature-gen/` 的可加载 skill，作为状态代理连接 teshi daemon，维护本地 StepIndex 缓存，为 AI Agent 提供实时、增量的步骤索引查询

### Modified Capabilities
- （无）

## Impact

- **Teshi 项目**：`StepIndex` 从主二进制下沉到 `teshi-gherkin` crate；daemon 新增 API 端点和 WebSocket 事件；文件变更流程联动 StepIndex 重建
- **BDD skill 目录**：创建 `.agents/skills/bdd-feature-gen/` skill，不修改现有规范文件
- **Feature 生成质量**：通过实时 StepIndex 感知，步骤复用率目标 ≥ 70%
- **架构亮点**：证明"专用 Agent 的应用级状态"优于"通用 Agent + Prompt"的工程案例
