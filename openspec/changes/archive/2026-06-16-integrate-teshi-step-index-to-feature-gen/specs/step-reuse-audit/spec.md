## ADDED Requirements

### Requirement: 审计脚本基于 StepIndex 检测步骤复用
BDD skill SHALL 在 Feature 文件生成后调用 StepIndex 检测步骤重复，输出复用率报告。StepIndex 来源优先使用 daemon 代理，回退到 CLI。

#### Scenario: 审计检测新步骤与已有步骤的重复
- **WHEN** Feature 文件生成完成
- **THEN** 提取新文件中的所有步骤文本
- **AND** 对每个步骤做归一化处理
- **AND** 与 StepIndex 对比
- **AND** 输出每个步骤的匹配状态：`reused` 或 `new`

#### Scenario: 审计报告包含复用率指标
- **WHEN** 审计完成
- **THEN** 输出包含：新文件总步骤数、复用数、新增数、复用率
- **AND** 重复步骤清单（语义等价但不同表述的）

### Requirement: `audit_step_reuse.py` 支持文件/目录审计
SHALL 支持对单个 Feature 文件或目录下所有 Feature 文件进行审计。

#### Scenario: 审计单个 Feature 文件
- **WHEN** 运行 `python scripts/audit_step_reuse.py path/to/feature.feature`
- **THEN** 解析该文件所有步骤并输出审计报告

#### Scenario: 审计目录下所有 Feature 文件
- **WHEN** 运行 `python scripts/audit_step_reuse.py path/to/features/`
- **THEN** 递归扫描目录下所有 `.feature` 文件
- **AND** 输出每个文件的审计报告
- **AND** 输出全局汇总统计

### Requirement: 审计支持 text 和 json 格式输出
- **WHEN** 运行 `python scripts/audit_step_reuse.py --format json feature.feature`
- **THEN** 输出 JSON 格式，便于 CI 集成
- **WHEN** 运行 `python scripts/audit_step_reuse.py --format text feature.feature`
- **THEN** 输出人类可读文本格式（默认）

### Requirement: 审计阈值门禁
- **WHEN** 运行 `python scripts/audit_step_reuse.py --threshold 0.7 feature.feature`
- **AND** 复用率低于 70%
- **THEN** 脚本以非零退出码退出
- **AND** 输出警告信息（用于 CI 门禁）

### Requirement: 检测到重复时给出优化建议
- **WHEN** 审计发现新步骤与已有步骤语义等价
- **THEN** 输出建议：建议复用已有步骤，并给出已有步骤的出现位置
- **WHEN** 审计发现新步骤可通过参数化扩展已有步骤来覆盖
- **THEN** 输出建议：通过参数化扩展已有步骤，无需新增
