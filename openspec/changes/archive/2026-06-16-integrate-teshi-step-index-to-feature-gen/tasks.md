## 1. Teshi 侧：StepIndex 下沉到 `teshi-gherkin` crate

- [x] 1.1 将 `src/step_index.rs` 移动到 `crates/teshi-gherkin/src/step_index.rs`，保留所有代码和测试
- [x] 1.2 在 `crates/teshi-gherkin/src/lib.rs` 中导出 `step_index` 模块
- [x] 1.3 删除 `src/step_index.rs`，更新 `main.rs` 中的模块声明
- [x] 1.4 更新 `src/app.rs` 中所有引用为 `use teshi_gherkin::StepIndex`
- [x] 1.5 运行全 workspace 测试验证无编译/测试失败

## 2. Teshi 侧：Daemon 新增 `GET /api/v1/steps/catalog` 端点

- [x] 2.1 在 `crates/teshi-daemon/src/server.rs` 中实现 `api_step_catalog` handler
- [x] 2.2 实现：读取项目根 → 扫描 `.feature` 文件 → 构建 `BddProject` → `StepIndex::build` → 序列化 JSON
- [x] 2.3 实现查询参数：`min_count`、`top`、`no_locations`
- [x] 2.4 在 protected routes 中注册 `GET /api/v1/steps/catalog`
- [x] 2.5 测试：启动 daemon，验证 JSON 输出结构和查询参数过滤

## 3. Teshi 侧：文件变更联动 StepIndex 重建 + WebSocket 事件

- [x] 3.1 在 `crates/teshi-runtime/src/gherkin.rs` 中实现 `rebuild_and_emit_step_index` 函数
- [x] 3.2 集成到 `emit_feature_refresh`：feature 文件变更后全量重建 StepIndex
- [x] 3.3 添加 debounce（300ms）避免频繁重建
- [x] 3.4 通过 `events.emit("step-index-updated", payload)` 推送
- [x] 3.5 事件 payload 与 `GET /api/v1/steps/catalog` 的 JSON 结构一致
- [x] 3.6 测试：修改 `.feature` 文件后验证 WebSocket 收到 `step-index-updated`

## 4. Skill 侧：创建 skill 目录结构与 `SKILL.md`

- [x] 4.1 创建 `.agents/skills/bdd-feature-gen/`（含 `SKILL.md`、`scripts/`、`references/`）
- [x] 4.2 编写 `SKILL.md`：metadata + sidecar 启动流程 + JSON-RPC 协议说明 + 步骤复用规则
- [x] 4.3 在 `SKILL.md` 中明确 sidecar 的进程模型（Agent 启动、stdin/stdout 通信、shutdown）
- [x] 4.4 创建 `references/step-index-schema.md` 说明 JSON 结构
- [x] 4.5 验证 `load_skill("bdd-feature-gen")` 可成功加载

## 5. Skill 侧：`step_catalog_proxy.py` Sidecar 实现

- [x] 5.1 实现 DaemonManifest 检测（发现 daemon 端口）
- [x] 5.2 实现 HTTP 客户端：`GET /api/v1/steps/catalog` 获取初始 StepIndex
- [x] 5.3 实现 WebSocket 客户端：订阅 `/api/v1/events`，处理 `step-index-updated`
- [x] 5.4 实现内存缓存：`top(n)`、`reuse_count(text)`、`search(keyword)`
- [x] 5.5 实现 stdin JSON-RPC 事件循环：逐行读入、分发到方法、写入 stdout
- [x] 5.6 实现 stdout push 事件：WebSocket 更新时向 Agent 推送通知
- [x] 5.7 实现 `shutdown` 方法：断开 WS 连接、退出进程
- [x] 5.8 实现 WebSocket 断线自动重连（3 次，间隔 1s，全量刷新）
- [x] 5.9 实现 CLI 降级：daemon 不可达时子进程调用 `teshi steps catalog`
- [x] 5.10 实现 stdin EOF 自动退出（Agent 进程终止时自然清理）
- [x] 5.11 添加 `-h/--help` 和标准退出码

## 6. Skill 侧：`audit_step_reuse.py`（独立工具，非 sidecar）

- [x] 6.1 实现 Gherkin 步骤提取（解析 `.feature` 中的 Given/When/Then/And/But 行）
- [x] 6.2 获取 StepIndex：优先连接 sidecar 的 JSON-RPC（启动临时实例），回退到 CLI
- [x] 6.3 对比步骤并输出复用率报告（总步骤数、复用数、新增数、复用率）
- [x] 6.4 支持 `--format json|text` 输出
- [x] 6.5 支持 `--threshold` 门禁模式（低于阈值退出码非零）
- [x] 6.6 检测语义等价步骤并输出优化建议
- [x] 6.7 支持目录递归审计并输出全局汇总

## 7. 集成测试与演示

- [x] 7.1 测试 sidecar 完整生命周期：启动 → 连接 daemon → 处理 JSON-RPC → shutdown
- [x] 7.2 测试降级：无 daemon 时 sidecar 的状态和 CLI 回退
- [x] 7.3 测试 WebSocket 断连重连和数据一致性
- [x] 7.4 测试 Agent 进程退出时 sidecar 自动清理
- [x] 7.5 编写端到端演示脚本 `scripts/demo_sidecar.py`：展示 sidecar 启动 → JSON-RPC 交互 → StepIndex 实时缓存 → 低重复 Feature 生成的完整链路
