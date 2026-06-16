# Step Index Service

## Purpose

Define the data model and API for the Step Index service — providing real-time step catalog queries over REST and event-driven rebuilds on file changes within the teshi daemon.

## Requirements

### Requirement: StepIndex 下沉到 `teshi-gherkin` crate

`StepIndex` 及相关类型（`StepLocation`、`normalize`）SHALL 从 `src/step_index.rs` 移动到 `crates/teshi-gherkin/src/step_index.rs`，作为 `teshi-gherkin` crate 的公开模块。

#### Scenario: StepIndex 在 teshi-gherkin 中可访问
- **WHEN** 构建 `teshi-gherkin` crate
- **THEN** `StepIndex` struct 可从 `teshi_gherkin::StepIndex` 导入
- **AND** `StepLocation` 和 `normalize` 函数一同导出
- **AND** `StepIndex::build` 接收 `&BddProject` 参数且行为不变

#### Scenario: 主二进制引用更新
- **WHEN** 打开 `src/step_index.rs`
- **THEN** 该文件不再存在（已移除）
- **WHEN** 搜索 `use crate::step_index::StepIndex` 或类似引用
- **THEN** 所有引用已更新为 `use teshi_gherkin::StepIndex`
- **AND** `src/app.rs` 中的 StepIndex 使用不受影响

#### Scenario: 现有测试全部通过
- **WHEN** 运行 `cargo test -p teshi-gherkin`
- **THEN** StepIndex 相关的测试全部通过
- **WHEN** 运行 `cargo test`（全 workspace）
- **THEN** 没有编译或测试失败

### Requirement: Daemon 新增 `GET /api/v1/steps/catalog` 端点

Teshi daemon SHALL 提供一个 REST API 端点，返回当前项目的完整 StepIndex。

#### Scenario: 查询完整步骤目录
- **WHEN** 向 daemon 发送 `GET /api/v1/steps/catalog`
- **THEN** 返回 200 JSON，包含 `project_root`、`total_raw_steps`、`unique_normalized`、`num_features`、`generated_at`、`entries`
- **AND** `entries` 按 `count` 降序排列

#### Scenario: `?min_count=N` 过滤低频步骤
- **WHEN** 向 daemon 发送 `GET /api/v1/steps/catalog?min_count=2`
- **THEN** 返回只包含 `count >= 2` 的条目

#### Scenario: `?top=N` 限制返回条数
- **WHEN** 向 daemon 发送 `GET /api/v1/steps/catalog?top=10`
- **THEN** 返回最多 10 条条目

#### Scenario: `?no_locations=true` 省略位置信息
- **WHEN** 向 daemon 发送 `GET /api/v1/steps/catalog?no_locations=true`
- **THEN** 返回的 `entries` 中不包含 `locations` 字段

#### Scenario: 无项目打开时返回 400
- **WHEN** daemon 无活动项目时收到 `GET /api/v1/steps/catalog`
- **THEN** 返回 400 状态码和错误消息

### Requirement: 文件变更自动触发 StepIndex 重建

当 `.feature` 文件发生变更时，SHALL 自动重建全量 StepIndex 并通过事件总线通知。

#### Scenario: Feature 文件变更后自动重建 StepIndex
- **WHEN** 被 watcher 监控的 `.feature` 文件发生外部编辑
- **THEN** 全量重新扫描项目中所有 `.feature` 文件
- **AND** 重建 `StepIndex`
- **AND** 通过 `events.emit("step-index-updated", ...)` 推送事件

#### Scenario: `step-index-updated` 事件包含完整索引数据
- **WHEN** `step-index-updated` 事件被触发
- **THEN** 事件 payload 与 `GET /api/v1/steps/catalog` 的 JSON 结构一致

#### Scenario: 重建不会丢失或错误统计步骤
- **WHEN** 新添加一个包含 5 个步骤的 feature 文件
- **THEN** 重建后的 StepIndex 中 `total_raw_steps` 增加 5
- **AND** `unique_normalized` 正确反映新增/去重后的计数
