## ADDED Requirements

### Requirement: Skill 是 Sidecar 进程（非按需脚本）
`bdd-feature-gen` skill SHALL 的核心组件 `step_catalog_proxy.py` 是一个 long-lived sidecar 进程，Agent 启动它一次，后续通过 stdin/stdout 的 JSON-RPC 通信。

#### Scenario: Sidecar 作为子进程启动
- **WHEN** Agent 运行 `python scripts/step_catalog_proxy.py`
- **THEN** 进程启动并初始化连接 teshi daemon
- **AND** 不在 stdout 输出任何内容（等待 stdin 命令）
- **AND** 进程保持运行，不主动退出

#### Scenario: Sidecar 启动后立即连接 Daemon
- **WHEN** sidecar 启动
- **AND** teshi daemon 运行中
- **THEN** 通过 `DaemonManifest` 发现 daemon 端口
- **AND** 发送 `GET /api/v1/steps/catalog` 获取初始 StepIndex
- **AND** 订阅 WebSocket `/api/v1/events` 监听 `step-index-updated`
- **AND** 将 StepIndex 缓存到内存

#### Scenario: Sidecar 启动时 Daemon 未运行
- **WHEN** sidecar 启动
- **AND** teshi daemon 未运行
- **THEN** sidecar 标记为 `daemon: "not_found"` 状态
- **AND** 后续方法调用降级为子进程 `teshi steps catalog`

### Requirement: 通信协议为 NDJSON over Stdin/Stdout
Sidecar 与 Agent 之间的通信协议 SHALL 是逐行 JSON（NDJSON），每行一个完整的 JSON-RPC 消息。

#### Scenario: Agent 发送 JSON-RPC 请求
- **WHEN** Agent 向 sidecar 的 stdin 写入 `{"id": 1, "method": "top", "params": {"n": 10}}\n`
- **THEN** sidecar 在 stdout 输出 `{"id": 1, "result": {"entries": [...]}}\n`
- **AND** 响应的 `id` 与请求的 `id` 严格对应

#### Scenario: Sidecar 支持的方法
- **WHEN** Agent 调用 `top` 方法
- **THEN** 返回缓存中前 N 个高频步骤
- **WHEN** Agent 调用 `reuse_count` 方法
- **THEN** 返回某步骤的复用次数
- **WHEN** Agent 调用 `search` 方法
- **THEN** 返回包含关键字的步骤列表
- **WHEN** Agent 调用 `status` 方法
- **THEN** 返回 daemon 连接状态和缓存摘要

#### Scenario: Sidecar 主动推送事件
- **WHEN** sidecar 从 WebSocket 收到 `step-index-updated` 事件
- **THEN** 更新内存缓存
- **AND** 向 stdout 输出 `{"event": "step-index-updated", "data": {...}}\n`
- **AND** 该行无 `id` 字段以区别于请求响应

#### Scenario: Sidecar 优雅关闭
- **WHEN** Agent 发送 `{"method": "shutdown"}`
- **THEN** sidecar 断开 WebSocket 连接
- **AND** 输出 `{"ok": true}` 并退出
- **WHEN** stdin 到达 EOF（Agent 进程退出）
- **THEN** sidecar 自动断开 WebSocket 并退出
- **AND** 无残留进程

### Requirement: `step_catalog_proxy.py` 支持降级策略
Sidecar SHALL 在 daemon 不可用时自动降级，保证 Agent 始终可用。

#### Scenario: Daemon 运行时的时序
- **WHEN** sidecar 启动
- **THEN** HTTP 获取全量 StepIndex → 进入事件循环等待命令
- **AND** WebSocket 连接维护增量更新
- **AND** 所有查询从内存缓存响应，零 IO

#### Scenario: Daemon 未运行时的降级
- **WHEN** sidecar 启动且 daemon 未运行
- **THEN** 初始化完成后进入降级模式
- **AND** `status` 方法返回 `daemon: "not_found"`
- **AND** `top`/`reuse_count`/`search` 方法每次调用时子进程执行 `teshi steps catalog`
- **AND** 调用结果不缓存（因为无法获知何时应刷新）

#### Scenario: WebSocket 断连重连
- **WHEN** WebSocket 连接意外断开
- **THEN** 自动重试 3 次，间隔 1 秒
- **AND** 重连成功后全量拉取一次 StepIndex
- **AND** 更新内存缓存
- **AND** 向 stdout 推送 `{"event": "ws-reconnected"}`

### Requirement: Skill 目录结构和 SKILL.md
BDD skill SHALL 创建在 `.agents/skills/bdd-feature-gen/` 目录下。

#### Scenario: 目录结构
- **WHEN** 查看目录
- **THEN** 存在 `SKILL.md`、`scripts/step_catalog_proxy.py`、`scripts/audit_step_reuse.py`、`references/`

#### Scenario: SKILL.md 定义 Sidecar 启动流程
- **WHEN** 阅读 `SKILL.md`
- **THEN** 包含以下指令：
  1. 启动 sidecar：`python scripts/step_catalog_proxy.py`
  2. 等待初始化完成（检查 `status` 响应）
  3. 通过 stdin 发送 JSON-RPC 命令查询 StepIndex
  4. 将 StepIndex 作为上下文传递给 AI
  5. 生成完成后调用 `shutdown` 或让进程自然退出

#### Scenario: SKILL.md 包含步骤复用规则
- **WHEN** 阅读 `SKILL.md`
- **THEN** 包含规则：优先复用、禁止语义等价变体、可参数化、优先扩展已有 Step
