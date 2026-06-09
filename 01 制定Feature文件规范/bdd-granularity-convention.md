# BDD Feature 文件颗粒度规范

> 适用范围：Python · Playwright · Behave · WinUI3 UI 自动化项目  
> 维护者：测试架构组  
> 最后更新：2026-06

---

## 目录

1. [为什么要定义颗粒度](#1-为什么要定义颗粒度)
2. [三层结构模型](#2-三层结构模型)
3. [Feature 文件规范](#3-feature-文件规范)
4. [Scenario 原子性规范](#4-scenario-原子性规范)
5. [Step 语言层级规范](#5-step-语言层级规范)
6. [典型反例与修正示例](#6-典型反例与修正示例)
7. [AI 生成链路的颗粒度约束](#7-ai-生成链路的颗粒度约束)
8. [自动化检查工具](#8-自动化检查工具)
9. [Code Review Checklist](#9-code-review-checklist)
10. [快速判断卡片](#10-快速判断卡片)

---

## 1. 为什么要定义颗粒度

BDD 规范本身（Gherkin）对颗粒度没有硬性约束。若不统一定义，多人/多 AI 并行编写 Feature 会导致：

- **步骤膨胀**：语义相同的 Step 出现多种表达，Step Catalog 重复率上升
- **覆盖空洞**：Feature 边界不清时，核心业务场景被跨文件稀释
- **维护成本倍增**：一次需求变更需修改散落在多个文件的 Scenario
- **AI 输出漂移**：`trace→BDD` 管道在无约束时，倾向生成 UI 操作级步骤（过细）或端到端流水账（过粗）

---

## 2. 三层结构模型

```
Feature 文件
└── Rule（可选，用于分组业务规则）
    └── Scenario / Scenario Outline
        └── Given / When / Then Steps
```

| 层次 | 对应业务概念 | 颗粒度定语 | 典型示例 |
|------|------------|-----------|---------|
| **Feature 文件** | 一个用户旅程阶段 / 一个业务能力域 | 宽 | `task_management.feature` |
| **Rule**（可选） | 一条独立业务规则或约束 | 中 | `Rule: 未登录用户不能创建任务` |
| **Scenario** | 一个可独立验证的业务结果 | 窄 | `Scenario: 任务名称为空时提交被拒` |

### 2.1 何时使用 `Rule:` 关键字

当一个 Feature 文件中有 **5 个以上 Scenario** 且可按业务规则分组时，使用 `Rule:` 块：

```gherkin
Feature: 任务管理

  Rule: 权限校验

    Scenario: 普通用户无法删除他人任务
      ...

    Scenario: 管理员可以删除任何任务
      ...

  Rule: 任务状态流转

    Scenario: 待办任务可以被标记为进行中
      ...
```

当 Feature 文件 Scenario 数量 ≤ 4 时，`Rule:` 可省略。

---

## 3. Feature 文件规范

### 3.1 文件边界：一个文件 = 一个业务旅程阶段

| 指标 | 建议值 | 说明 |
|------|--------|------|
| Scenario 总数 | **5–15 个** | 少于 5 考虑合并；超过 15 需要拆分 |
| 文件总行数 | **≤ 200 行** | 包含注释和空行 |
| Background 步骤数 | **≤ 4 步** | 超出说明前置条件太复杂，考虑夹具化 |
| 嵌套 Rule 数 | **≤ 5 个** | 超出说明该功能域过宽 |

### 3.2 文件命名规范

```
格式：{业务对象}_{核心动词}.feature

✅ 好的命名
  task_creation.feature       ← 业务对象 + 核心动词
  user_authentication.feature
  order_checkout.feature

❌ 不好的命名
  test_task.feature           ← "test_" 前缀是测试思维，不是业务思维
  task_management_full.feature ← "full" 意味着边界无限
  ui_task_form.feature        ← UI 实现细节渗入文件名
```

### 3.3 Feature 描述要求

每个 Feature 文件的描述（`Feature:` 之后的多行文本）须包含：

```gherkin
Feature: 任务创建

  作为一名项目成员
  我希望能够创建新任务
  以便跟踪待完成的工作项

  业务规则：
    - 任务名称不能为空
    - 截止日期不能早于今天
    - 仅已登录用户可以创建任务
```

**用户故事（作为/我希望/以便）是必填的**，业务规则列表是推荐的。

---

## 4. Scenario 原子性规范

### 4.1 原子性三原则

**原则一：单一结果原则（One Outcome）**

每个 Scenario 只验证一个业务结果。

```gherkin
# ❌ 过粗：同时验证创建成功和列表刷新
Scenario: 创建任务并验证列表
  Given 用户在任务列表页
  When 用户填写任务名称"修复登录问题"并提交
  Then 任务创建成功
  And 任务列表中显示"修复登录问题"
  And 任务数量加一

# ✅ 拆分为两个 Scenario
Scenario: 提交有效任务后显示成功反馈
  Given 用户在任务列表页
  When 用户填写任务名称"修复登录问题"并提交
  Then 系统显示"任务已创建"的确认提示

Scenario: 新建任务出现在列表顶部
  Given 系统中已有任务列表
  When 用户创建任务"修复登录问题"
  Then 任务列表首条记录为"修复登录问题"
```

**原则二：单一触发原则（One Trigger）**

每个 Scenario 只有一个核心 `When` 动作（用户的一次业务操作决策）。

```gherkin
# ❌ 过粗：两次用户决策行为
Scenario: 登录后创建任务
  Given 用户未登录
  When 用户输入账号密码并登录      ← 第一个业务动作
  And 用户创建任务"修复问题"        ← 第二个业务动作
  Then 任务出现在列表中

# ✅ 每个 Scenario 一个触发
Scenario: 有效凭据登录成功
  Given 用户在登录页
  When 用户使用有效账号密码登录
  Then 用户进入系统主界面

Scenario: 已登录用户可以创建任务
  Given 用户已登录系统
  When 用户创建任务"修复问题"
  Then 任务出现在列表中
```

**原则三：独立执行原则（Self-Contained）**

每个 Scenario 的 `Given` 必须完整描述前置状态，不依赖其他 Scenario 的执行结果。

```gherkin
# ❌ 隐式依赖：假设上一个 Scenario 已创建了任务
Scenario: 编辑已有任务
  Given 存在上一步创建的任务     ← 依赖执行顺序
  When 用户修改任务名称
  Then 修改后的名称显示正确

# ✅ 自包含的前置条件
Scenario: 编辑已有任务
  Given 系统中存在任务"修复登录问题"
  When 用户将任务名称修改为"修复注册问题"
  Then 任务名称更新为"修复注册问题"
```

### 4.2 步骤数量约束

| 指标 | 建议值 | 警戒值 |
|------|--------|--------|
| 总步骤数（Given + When + Then） | **3–7 步** | > 10 步触发审查 |
| `When` 步骤数（含后续 `And`） | **整组代表 1 个业务决策** | `And` 后出现独立业务动作，必须拆分 Scenario |
| `Then` 步骤数（含后续 `And`） | **1–3 步** | > 3 步考虑是否验证了多个不同结果 |
| `Given` 步骤数（含后续 `And`） | **1–3 步** | > 3 步考虑下沉为夹具或 `Background` |

> **关于 `And` / `But` 的语义继承**
>
> `And` 和 `But` 没有独立语义，始终继承前一个 `Given` / `When` / `Then` 的角色。因此不应对 `And` 单独计数，应按其所属语义组归入上表对应行。
>
> When 组判断标准：多个 `And` 若描述的是**同一业务决策的组成步骤**（如填写表单的各字段）则允许；若其中任意一个 `And` 可以独立成为另一个 Scenario 的 `When`，则必须拆分。

```gherkin
# ✅ When 组有 3 行，但只有 1 个业务决策（填写并提交表单是整体动作）
When  用户填写任务名称"修复问题"
And   用户设置截止日期为明天
And   用户点击提交

# ❌ When 组有 2 行，但包含 2 个独立业务决策，必须拆分
When  用户创建任务"修复问题"
And   用户将任务标记为完成
```

### 4.3 Scenario 命名规范

命名模式：**[条件] + 动作/事件 + 预期结果**

```
✅ 好的命名（结果清晰，可读懂）
  任务名称为空时提交被拒绝
  管理员删除任务后列表刷新
  超时未操作后系统自动登出

❌ 不好的命名
  测试创建任务               ← "测试" 前缀、无结果描述
  task_creation_success      ← 代码风格命名
  验证表单提交后的行为         ← "验证/行为" 是测试语言，不是业务语言
```

---

## 5. Step 语言层级规范

本项目涉及 **业务层**和 **UI 自动化层**，两层严格隔离：

```
Feature 文件（.feature）      ← 业务语言，不涉及任何实现细节
        ↓
Step Definitions（steps/）    ← 桥接层：接收业务语言，调用 PO 方法
        ↓
Page Objects（pages/）        ← UI 操作层：封装 Playwright / UIA 调用
```

### 5.1 Feature 文件中禁止出现的内容

以下内容属于**实现细节**，必须下沉到 Step Definitions 或 Page Objects：

| 禁止项 | 示例（❌） | 替代写法（✅） |
|--------|----------|-------------|
| UI 控件名称 | `When 用户点击 id="submit-btn" 的按钮` | `When 用户提交任务表单` |
| automationId / testId | `Then "task-list-item" 元素可见` | `Then 任务出现在列表中` |
| CSS 选择器 / XPath | `When 用户点击 .btn-primary` | `When 用户确认操作` |
| 数据库字段名 | `Given tasks 表中存在 status=1 的记录` | `Given 系统中存在一个进行中的任务` |
| API 路径 | `Then POST /api/tasks 返回 201` | `Then 任务创建成功` |
| 精确等待时间 | `When 等待 3 秒后` | （封装进 PO，Feature 不写等待） |
| 截图/日志断言 | `Then 截图匹配基线图片` | （限于 Step Definitions 内部） |

### 5.2 Step 语言三个层次

**业务层**（Feature 文件）：描述业务意图，谁在做什么，期望什么结果。

```gherkin
Given 用户已登录系统
When  用户创建任务"修复登录问题"并设置截止日期为明天
Then  新任务出现在待办列表的顶部
```

**领域层**（可用于复杂前置条件，仍属 Feature 文件可接受范围）：

```gherkin
Given 系统中存在 3 个待办任务和 1 个已完成任务
Given 用户账户余额为 500 元
Given 上一个工作日是假期
```

**实现层**（禁止出现在 Feature 文件）：

```gherkin
# 以下均属于实现层，不得出现在 .feature 文件
Given 页面 URL 为 "http://localhost:8765/tasks"
When  用户在 automationId="TaskNameInput" 的输入框输入"修复问题"
Then  automationId="SubmitButton" 的按钮状态为 enabled
```

### 5.3 Step Catalog 复用原则

新增 Step 前必须检查 Step Catalog，避免语义重复：

```python
# Step Catalog 中已有：
@when('用户创建任务"{task_name}"')

# ❌ 不应新增（语义等价的变体）：
@when('用户新建任务"{task_name}"')
@when('用户添加任务"{task_name}"')
@when('用户提交新任务"{task_name}"')

# ✅ 应新增（有实质区别）：
@when('用户创建任务"{task_name}"并设置优先级为"{priority}"')
```

**Step 命名必须可参数化**，避免将数据硬编码进 Step 表达式：

```gherkin
# ❌ 数据写死
When 用户创建任务"修复登录问题"

# ✅ 参数化
When 用户创建任务"<task_name>"
# 配合 Scenario Outline + Examples 使用
```

---

## 6. 典型反例与修正示例

### 反例 1：流水账式 Scenario（过粗）

```gherkin
# ❌ 一个 Scenario 覆盖完整用户旅程，有 3 个 When
Scenario: 完整任务操作流程
  Given 用户已登录系统
  When  用户创建任务"测试任务"
  And   用户编辑任务名称为"已修改任务"
  And   用户将任务标记为完成
  Then  任务在已完成列表中显示
```

**修正**：拆分为三个独立 Scenario，各自验证一个业务结果。

---

### 反例 2：UI 操作步骤泄漏（过细）

```gherkin
# ❌ 步骤描述了 UI 控件和操作细节
Scenario: 创建任务
  Given 用户在任务列表页面
  When  用户点击右上角的蓝色"+"按钮
  And   用户在弹出对话框的第一个输入框填写"测试任务"
  And   用户点击对话框底部的"确认"按钮
  Then  页面顶部出现绿色提示条显示"创建成功"
```

**修正**：

```gherkin
# ✅ 业务语言，不涉及控件细节
Scenario: 有效任务名称提交后创建成功
  Given 用户在任务列表页
  When  用户创建任务"测试任务"
  Then  系统提示任务创建成功
```

---

### 反例 3：过度细分（过细）

```gherkin
# ❌ 为每一个输入验证单独建 Feature 文件，导致文件爆炸
# task_name_empty.feature
# task_name_too_long.feature
# task_name_special_chars.feature
# task_due_date_past.feature
# task_due_date_format.feature
```

**修正**：合并为一个文件，使用 Scenario Outline：

```gherkin
# ✅ task_validation.feature
Feature: 任务表单验证

  Scenario Outline: 无效输入被拒绝
    Given 用户在新建任务页面
    When  用户提交 <field> 为 "<value>" 的任务表单
    Then  系统显示错误提示 "<message>"

    Examples:
      | field    | value                     | message          |
      | 任务名称  |                           | 任务名称不能为空  |
      | 任务名称  | <超过100字符的字符串>         | 任务名称过长      |
      | 截止日期  | 2020-01-01                | 截止日期不能是过去 |
```

---

### 反例 4：Background 滥用（前置条件过重）

```gherkin
# ❌ Background 有 8 步，几乎每个 Scenario 还要覆盖不同前置状态
Background:
  Given 用户已登录系统
  And   系统中存在项目"电商平台"
  And   项目下有 10 个任务
  And   其中 5 个任务为待办状态
  And   3 个任务为进行中
  And   2 个任务为已完成
  And   当前用户是项目管理员
  And   系统时间为工作日上午
```

**修正**：Background 最多 4 步，其余前置条件下沉为夹具（fixtures）或 Behave `@fixture`：

```gherkin
# ✅ Background 只保留最核心的共同前置
Background:
  Given 用户已以管理员身份登录
  And   当前项目下存在混合状态的任务列表

# 具体前置条件在各 Scenario 的 Given 中声明
Scenario: 筛选待办任务
  Given 任务列表中有 5 个待办任务
  When  用户按"待办"筛选
  Then  列表只显示 5 个待办任务
```

---

## 7. AI 生成链路的颗粒度约束

本项目使用 `trace→BDD` 和 `bdd-po-gen` 管道进行 AI 辅助生成。AI 生成的输出须在进入代码库前经过颗粒度审查。

### 7.1 `trace→BDD` 生成阶段的约束

`recording.py` 中的 `# 注释` 决定了 Step 标签。编写注释时须遵循：

```python
# ✅ 注释使用业务语言（Step 标签即 Gherkin 步骤候选）
# 用户创建新任务
page.get_by_role("button", name="+").click()
page.get_by_label("任务名称").fill("修复登录问题")
page.get_by_role("button", name="确认").click()

# ❌ 注释使用 UI 操作语言
# 点击右上角加号按钮
# 在 TaskNameInput 输入框填写内容
# 点击确认按钮
```

**一个注释块对应一个 When 步骤**。若一个注释块内的操作实际触发了两个独立的业务决策，须拆分注释：

```python
# ✅ 拆分为两个注释块
# 用户登录系统
page.get_by_label("账号").fill("admin")
page.get_by_label("密码").fill("123456")
page.get_by_role("button", name="登录").click()

# 用户创建任务
page.get_by_role("button", name="+").click()
...
```

### 7.2 AI 生成 Scenario 后的颗粒度审查清单

在 `confirmed_binding.md` 用户确认阶段，同时审查颗粒度：

```markdown
颗粒度审查（在 confirmed_binding.md 确认前完成）：

- [ ] 每个 Step 标签是否为业务语言（无控件名、无 ID、无 API 路径）
- [ ] 是否存在可合并的语义相同步骤（检查 Step Catalog）
- [ ] 单个 Scenario 是否只有 1 个 When
- [ ] Then 断言数是否 ≤ 3 个
- [ ] 若步骤 > 7 步，是否已评估拆分必要性
```

### 7.3 UIA 树特有约束

基于 UIA AccessibilityTree 生成定位器时，`automationId` 只允许出现在 **Page Object** 方法体内，绝不允许出现在 Step Definitions 的正则表达式或 Feature 文件中：

```python
# ✅ automationId 封装在 PO 内
class TaskPage:
    def create_task(self, name: str):
        self.page.locator('[AutomationId="TaskNameInput"]').fill(name)
        self.page.locator('[AutomationId="SubmitButton"]').click()

# Step Definition 只调用业务方法
@when('用户创建任务"{task_name}"')
def step_create_task(context, task_name):
    context.task_page.create_task(task_name)
```

---

## 8. 自动化检查工具

### 8.1 Feature Lint 脚本

将以下脚本放入项目根目录 `tools/feature_lint.py`，在 CI 或 pre-commit 中执行：

```python
#!/usr/bin/env python3
"""
BDD Feature 文件颗粒度检查工具
用法：python tools/feature_lint.py [features目录]
"""
import sys
import re
from pathlib import Path

try:
    from gherkin.parser import Parser
    from gherkin.token_scanner import TokenScanner
except ImportError:
    print("请安装依赖：pip install gherkin-official")
    sys.exit(1)

# ── 配置（可按项目调整） ─────────────────────────────────────────
RULES = {
    "max_scenarios_per_feature": 15,
    "min_scenarios_per_feature": 2,
    "max_steps_per_scenario": 10,
    "warn_steps_per_scenario": 7,
    "max_when_per_scenario": 1,
    "max_then_per_scenario": 3,
    "max_lines_per_feature": 200,
}

# 禁止出现在 Feature 文件中的实现细节模式
UI_DETAIL_PATTERNS = [
    (r'AutomationId\s*=\s*["\']', "automationId 不应出现在 Feature 文件"),
    (r'data-testid\s*=', "testid 属性不应出现在 Feature 文件"),
    (r'\bxpath\s*=', "XPath 不应出现在 Feature 文件"),
    (r'#[a-zA-Z][\w-]+\b', "CSS ID 选择器疑似出现在 Feature 文件"),
    (r'/api/[a-zA-Z]', "API 路径不应直接出现在 Feature 文件"),
    (r'http://|https://', "URL 不应直接出现在 Feature 文件（前置条件中的环境地址除外）"),
]

CHINESE_WHEN_KEYWORDS = {"当", "如果"}
CHINESE_THEN_KEYWORDS = {"那么", "则", "应该"}

# ─────────────────────────────────────────────────────────────────

def count_keyword(steps, keywords_en, keywords_zh):
    count = 0
    for step in steps:
        kw = step.keyword.strip()
        if kw in keywords_en or kw in keywords_zh:
            count += 1
    return count

def check_feature(path: Path) -> list[dict]:
    issues = []
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # 行数检查
    if len(lines) > RULES["max_lines_per_feature"]:
        issues.append({
            "level": "warn",
            "location": f"{path}",
            "message": f"文件行数 {len(lines)} 超过建议值 {RULES['max_lines_per_feature']}，考虑拆分"
        })

    # 实现细节模式检查
    for lineno, line in enumerate(lines, 1):
        # 跳过注释行
        if line.strip().startswith("#"):
            continue
        for pattern, message in UI_DETAIL_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append({
                    "level": "error",
                    "location": f"{path}:{lineno}",
                    "message": f"{message} → {line.strip()[:80]}"
                })

    # Gherkin 结构解析
    try:
        parser = Parser()
        doc = parser.parse(TokenScanner(content))
    except Exception as e:
        issues.append({
            "level": "error",
            "location": str(path),
            "message": f"Gherkin 解析失败：{e}"
        })
        return issues

    feature = doc.feature
    if not feature:
        return issues

    # 收集所有 Scenario（包括 Rule 内部的）
    scenarios = []

    def collect_scenarios(children):
        for child in children:
            if hasattr(child, "scenario") and child.scenario:
                scenarios.append(child.scenario)
            if hasattr(child, "rule") and child.rule:
                collect_scenarios(child.rule.children)

    collect_scenarios(feature.children)

    # Feature 级别检查
    if len(scenarios) < RULES["min_scenarios_per_feature"]:
        issues.append({
            "level": "info",
            "location": str(path),
            "message": f"Scenario 数量 {len(scenarios)} 较少，考虑与相关 Feature 合并"
        })

    if len(scenarios) > RULES["max_scenarios_per_feature"]:
        issues.append({
            "level": "warn",
            "location": str(path),
            "message": f"Scenario 数量 {len(scenarios)} 超过建议值 {RULES['max_scenarios_per_feature']}，考虑拆分"
        })

    # Feature 描述检查（是否有用户故事）
    description = (feature.description or "").strip()
    if "作为" not in description and "As a" not in description:
        issues.append({
            "level": "info",
            "location": str(path),
            "message": "Feature 描述缺少用户故事（作为/As a）"
        })

    # Scenario 级别检查
    for sc in scenarios:
        steps = sc.steps
        total = len(steps)
        name = sc.name or "(未命名)"
        location = f"{path}:{sc.location.line}"

        when_count = count_keyword(
            steps, {"When"}, CHINESE_WHEN_KEYWORDS
        )
        then_count = count_keyword(
            steps, {"Then"}, CHINESE_THEN_KEYWORDS
        )

        if when_count > RULES["max_when_per_scenario"]:
            issues.append({
                "level": "error",
                "location": location,
                "message": f"[{name}] When 步骤有 {when_count} 个（上限 1），必须拆分 Scenario"
            })

        if then_count > RULES["max_then_per_scenario"]:
            issues.append({
                "level": "warn",
                "location": location,
                "message": f"[{name}] Then 断言有 {then_count} 个（建议 ≤ 3），考虑是否验证了多个结果"
            })

        if total > RULES["max_steps_per_scenario"]:
            issues.append({
                "level": "error",
                "location": location,
                "message": f"[{name}] 步骤数 {total} 超过上限 {RULES['max_steps_per_scenario']}"
            })
        elif total > RULES["warn_steps_per_scenario"]:
            issues.append({
                "level": "warn",
                "location": location,
                "message": f"[{name}] 步骤数 {total} 偏多（建议 ≤ {RULES['warn_steps_per_scenario']}），请确认是否可拆分"
            })

        # Scenario 命名检查
        bad_name_patterns = [
            (r"^测试", "命名以"测试"开头，建议使用业务结果描述"),
            (r"^test_", "命名使用代码风格，建议使用自然语言"),
            (r"验证.*行为$", "命名使用"验证...行为"模式，建议直接描述业务结果"),
        ]
        for pattern, msg in bad_name_patterns:
            if re.search(pattern, name):
                issues.append({
                    "level": "info",
                    "location": location,
                    "message": f"[{name}] 命名建议：{msg}"
                })

    return issues


def main():
    features_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("features")
    if not features_dir.exists():
        print(f"目录不存在：{features_dir}")
        sys.exit(1)

    all_issues = []
    for feat_file in sorted(features_dir.rglob("*.feature")):
        issues = check_feature(feat_file)
        all_issues.extend(issues)

    if not all_issues:
        print("✅ 所有 Feature 文件通过颗粒度检查")
        sys.exit(0)

    # 分级输出
    errors   = [i for i in all_issues if i["level"] == "error"]
    warnings = [i for i in all_issues if i["level"] == "warn"]
    infos    = [i for i in all_issues if i["level"] == "info"]

    for issue in errors:
        print(f"❌ ERROR   {issue['location']}")
        print(f"          {issue['message']}")

    for issue in warnings:
        print(f"⚠️  WARN    {issue['location']}")
        print(f"          {issue['message']}")

    for issue in infos:
        print(f"ℹ️  INFO    {issue['location']}")
        print(f"          {issue['message']}")

    print(f"\n共 {len(errors)} 个错误，{len(warnings)} 个警告，{len(infos)} 个建议")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
```

### 8.2 pre-commit 集成

在 `.pre-commit-config.yaml` 中添加：

```yaml
- repo: local
  hooks:
    - id: bdd-granularity-lint
      name: BDD Feature 颗粒度检查
      entry: python tools/feature_lint.py features/
      language: system
      files: \.feature$
      pass_filenames: false
```

### 8.3 CI 集成（GitHub Actions / GitLab CI）

```yaml
# GitHub Actions 示例
- name: BDD Feature Lint
  run: |
    pip install gherkin-official
    python tools/feature_lint.py features/
```

---

## 9. Code Review Checklist

在 PR 描述模板中加入以下检查项（涉及 `.feature` 文件变更时必填）：

```markdown
## BDD Feature 颗粒度审查

### Feature 文件层级
- [ ] 文件名使用 `{业务对象}_{核心动词}.feature` 格式
- [ ] Feature 描述包含用户故事（作为/我希望/以便）
- [ ] Scenario 总数在 5–15 个之间（若超出，已在 PR 说明中解释原因）
- [ ] 文件行数 ≤ 200 行

### Scenario 原子性
- [ ] 每个 Scenario 只有 1 个 When 步骤
- [ ] 每个 Scenario 的 Then 断言 ≤ 3 个
- [ ] 每个 Scenario 总步骤数 ≤ 10 步（建议 ≤ 7 步）
- [ ] Given 中无"依赖上一个场景"的隐式假设

### 步骤语言
- [ ] Feature 文件中无 automationId / testId / XPath / CSS 选择器
- [ ] Feature 文件中无 API 路径（/api/xxx）
- [ ] Feature 文件中无数据库字段名
- [ ] Step 表达式已检查 Step Catalog，无语义重复

### AI 生成内容（如适用）
- [ ] trace→BDD 产出的 Step 标签已替换为业务语言
- [ ] confirmed_binding.md 确认前已完成颗粒度审查
```

---

## 10. 快速判断卡片

当拿到一个 Scenario 不确定是否符合规范时，按以下顺序自检：

```
Q1: 这个 Scenario 有几个 When？
    → > 1 个：必须拆分，每个 When 对应一个独立 Scenario

Q2: 这个 Scenario 有几个 Then？
    → > 3 个：检查是否在验证多个不同业务结果，是则拆分

Q3: 步骤总数是多少？
    → > 10 步：强制审查是否可拆分
    → 7–10 步：建议审查

Q4: 任意步骤中是否出现了控件名、ID、选择器、API 路径？
    → 是：下沉到 Step Definitions 或 PO，Feature 改为业务语言表达

Q5: 这个 Scenario 的 Given 是否引用了"上一步"的结果？
    → 是：补充完整的前置状态描述，使其可独立执行

Q6: Scenario 命名能否让非技术干系人（产品/业务）理解意图？
    → 不能：重新命名，使用业务结果描述
```

---

*本文档是活文档，随项目演进更新。如有边界情况或规则争议，以测试架构组评审结论为准。*
