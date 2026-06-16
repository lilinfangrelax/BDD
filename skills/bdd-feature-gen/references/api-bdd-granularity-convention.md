# API BDD Feature 文件规范

> 适用范围：Python · Behave · Jinja2 模板引擎 · API 自动化测试项目  
> 配套文档：《BDD Feature 文件颗粒度规范》（UI 层）  
> 维护者：测试架构组  
> 最后更新：2026-06

---

## 目录

1. [与 UI 规范的关系和差异](#1-与-ui-规范的关系和差异)
2. [三层结构模型](#2-三层结构模型)
3. [Feature 文件规范](#3-feature-文件规范)
4. [Scenario 原子性规范](#4-scenario-原子性规范)
5. [Step 语言层级规范](#5-step-语言层级规范)
6. [Background 与登录态规范](#6-background-与登录态规范)
7. [从 UI Feature 转换为 API Feature 的规则](#7-从-ui-feature-转换为-api-feature-的规则)
8. [典型反例与修正示例](#8-典型反例与修正示例)
9. [AI 转换链路的约束](#9-ai-转换链路的约束)
10. [Code Review Checklist](#10-code-review-checklist)
11. [快速判断卡片](#11-快速判断卡片)

---

## 1. 与 UI 规范的关系和差异

API Feature 文件和 UI Feature 文件共享同一套业务场景体系，描述的是**相同的业务行为，不同的执行路径**。

### 1.1 相同之处

- 业务语言原则：Step 描述业务意图，不暴露实现细节
- 颗粒度数量约束：Scenario 数量、步骤数量的建议值相同
- Scenario 原子性三原则：单一结果、单一触发、独立执行
- Feature 文件边界：一个文件对应一个业务能力域

### 1.2 核心差异

| 维度 | UI Feature | API Feature |
|------|-----------|-------------|
| Step 前缀 | 无前缀 | 全部使用 `【API】` 前缀 |
| Given 语义 | 页面状态（用户在某页面） | 数据状态（系统中存在某数据） |
| Then 语义 | 视觉反馈（显示提示、元素可见） | 业务结果（操作成功、数据变更） |
| 登录态处理 | UI 操作登录，或 fixture 注入 | Background 中声明，Step Definition 调用登录接口 |
| 参数依赖 | 由 Page Object 封装 | 由 Step Definition + Jinja2 模板封装 |
| 执行层 | Playwright + PO | Jinja2 模板引擎 + HTTP 执行层 |

### 1.3 `【API】` 前缀的含义

`【API】` 前缀是执行路径标识，不是技术实现描述。它告诉读者"这个步骤通过接口调用执行"，但不暴露任何 HTTP 细节（URL、method、状态码、响应结构）。

```gherkin
# ✅ 前缀只标识执行路径，Step 本身是业务语言
When 【API】新增任务，任务名称"修复登录问题"

# ❌ 前缀之后仍然是技术语言
When 【API】POST /api/tasks，body 中 name 为"修复登录问题"
```

---

## 2. 三层结构模型

```
Feature 文件（api/）
└── Rule（可选，用于分组业务规则）
    └── Scenario / Scenario Outline
        └── 【API】Given / When / Then Steps
                    ↓
            Step Definitions（steps/api_steps.py）
                    ↓
            Jinja2 模板（templates/{domain}/{action}.j2）
            ├── method / url / body / params
            ├── checkpoint（断言规则）
            └── variable_extract（响应字段提取）
```

**Feature 文件不感知模板内部结构。** 模板的 checkpoint 和 variable_extract 是实现细节，由 Step Definition 和模板引擎负责，不在 Feature 文件中体现。

---

## 3. Feature 文件规范

### 3.1 文件存放位置

```
features/
├── ui/          ← UI Feature 文件
│   └── task_creation.feature
└── api/         ← API Feature 文件（本规范适用范围）
    └── task_creation.feature
```

API Feature 文件和 UI Feature 文件**文件名保持一致**，通过目录区分。这样能直观看出两者的对应关系，也方便 AI 转换时做对齐。

### 3.2 文件边界：一个文件 = 一个业务能力域

与 UI 规范保持一致：

| 指标 | 建议值 | 说明 |
|------|--------|------|
| Scenario 总数 | **5–15 个** | 少于 5 考虑合并；超过 15 需要拆分 |
| 文件总行数 | **≤ 200 行** | 包含注释和空行 |
| Background 步骤数 | **≤ 3 步** | API 层 Background 通常只需登录态声明 |
| 嵌套 Rule 数 | **≤ 5 个** | 超出说明该功能域过宽 |

### 3.3 文件命名规范

与对应的 UI Feature 文件名保持一致：

```
ui/task_creation.feature   →   api/task_creation.feature
ui/user_auth.feature       →   api/user_auth.feature
```

### 3.4 Feature 描述要求

```gherkin
Feature: 任务创建

  作为一名项目成员
  我希望通过接口创建和管理任务
  以便验证任务管理的核心业务逻辑

  业务规则：
    - 任务名称不能为空
    - 截止日期不能早于今天
    - 仅已登录用户可以创建任务
```

用户故事（作为/我希望/以便）是必填的，业务规则列表是推荐的，与 UI 规范相同。

---

## 4. Scenario 原子性规范

### 4.1 原子性三原则

与 UI 规范完全一致，此处只列出 API 层特有的注意点。

**单一结果原则在 API 层的特殊情况：**

API 调用天然会返回响应，但响应的多个字段断言是否算"多个结果"，判断标准是：

```gherkin
# ✅ 同一业务结果的多个属性断言，允许
When  【API】新增任务，任务名称"修复登录问题"
Then  【API】任务创建成功
And   【API】返回的任务可被后续步骤引用    ← 描述 variable_extract 的业务意义

# ❌ 两个独立的业务结果，必须拆分
When  【API】新增任务，任务名称"修复登录问题"
Then  【API】任务创建成功
And   【API】任务列表数量加一              ← 独立的业务结果，拆分为新 Scenario
```

**独立执行原则在 API 层的数据准备：**

Given 中的数据准备步骤（`【API】已存在任务"xxx"`）通过 Step Definition 调用接口创建，不依赖数据库直接插入，也不依赖其他 Scenario 的执行结果。

### 4.2 步骤数量约束

| 指标 | 建议值 | 警戒值 |
|------|--------|--------|
| 总步骤数（Given + When + Then） | **3–7 步** | > 10 步触发审查 |
| `When` 步骤数（含后续 `And`） | **整组代表 1 个业务决策** | `And` 后出现独立业务动作，必须拆分 |
| `Then` 步骤数（含后续 `And`） | **1–3 步** | > 3 步考虑是否验证了多个不同结果 |
| `Given` 步骤数（含后续 `And`，不含 Background） | **1–3 步** | > 3 步考虑封装为复合数据准备 Step |

> **关于 `And` / `But` 的语义继承**
>
> `And` 和 `But` 没有独立语义，始终继承前一个 `Given` / `When` / `Then` 的角色。不应对 `And` 单独计数，应按其所属语义组归入上表对应行。
>
> When 组判断标准：多个 `And` 若描述同一业务决策的组成步骤则允许；若其中任意一个 `And` 可以独立成为另一个 Scenario 的 `When`，则必须拆分。

### 4.3 Scenario 命名规范

API Feature 的 Scenario 命名应与对应的 UI Feature **保持一致或高度对齐**，便于两套用例的追溯和比对：

```
UI Scenario:  提交有效任务名称后创建成功
API Scenario: 提交有效任务名称后创建成功   ← 名称完全一致，只有执行路径不同

UI Scenario:  任务名称为空时提交被拒绝
API Scenario: 任务名称为空时请求被拒绝     ← 微调措辞（"提交"→"请求"），保持语义一致
```

---

## 5. Step 语言层级规范

### 5.1 API Feature 文件中禁止出现的内容

| 禁止项 | 示例（❌） | 替代写法（✅） |
|--------|----------|-------------|
| HTTP 方法 | `When 【API】POST 新增任务` | `When 【API】新增任务，任务名称"xxx"` |
| URL 路径 | `When 【API】调用 /api/tasks/create` | `When 【API】新增任务，任务名称"xxx"` |
| 响应状态码 | `Then 【API】响应状态码为 201` | `Then 【API】任务创建成功` |
| 响应体字段名 | `Then 【API】响应体 body.id 不为空` | `Then 【API】任务创建成功` |
| 模板文件名 | `When 【API】使用模板 tasks/create.j2` | `When 【API】新增任务，任务名称"xxx"` |
| variable_extract 字段 | `Then 【API】提取 task_id 存入上下文` | （由模板和 Step Definition 处理，Feature 不感知）|
| 请求头细节 | `Given 【API】设置 Authorization header` | `Given 【API】以普通用户身份登录` |

### 5.2 Then 的业务断言写法

Then 的职责是描述**业务结果**，不是描述 HTTP 响应。模板的 checkpoint 负责具体的断言执行，Feature 文件只描述业务意义：

```gherkin
# ✅ 业务结果描述
Then 【API】任务创建成功
Then 【API】操作被拒绝，提示"任务名称不能为空"
Then 【API】任务列表包含"修复登录问题"
Then 【API】该任务名称已更新为"修复注册问题"

# ❌ HTTP 响应描述
Then 【API】响应状态码为 201
Then 【API】响应体包含 "id" 字段
Then 【API】响应时间小于 500ms
```

Then 的措辞应该让非技术干系人（产品、业务）能够理解意图。

### 5.3 Given 的数据状态写法

API 层的 Given 描述**数据状态**，不描述"如何创建这个数据"。数据的创建由 Step Definition 调用接口完成，Feature 不感知调用了哪些接口：

```gherkin
# ✅ 数据状态描述（推荐写法）
Given 【API】系统中存在任务"修复登录问题"
Given 【API】已存在任务"修复登录问题"
Given 【API】项目"电商平台"下有 3 个待办任务

# ⚠️ 动作描述（可接受，但不如状态描述清晰）
Given 【API】已创建任务"修复登录问题"

# ❌ 暴露了接口调用的实现细节
Given 【API】调用 POST /api/tasks 创建任务"修复登录问题"
Given 【API】创建项目，再在项目下创建任务"修复登录问题"
```

### 5.4 参数传递规范

业务参数在 Gherkin 中用引号包裹，数字参数不用引号：

```gherkin
When 【API】新增任务，任务名称"修复登录问题"
When 【API】新增任务，任务名称"修复登录问题"，优先级为 2
When 【API】查询前 10 条任务记录
```

参数名使用业务术语，不使用接口字段名：

```gherkin
# ✅ 业务术语
When 【API】新增任务，任务名称"修复登录问题"

# ❌ 接口字段名
When 【API】新增任务，name 为"修复登录问题"
```

---

## 6. Background 与登录态规范

### 6.1 登录态是 API Feature 的核心前置条件

绝大多数 API 需要认证，登录态放在 Background 中统一处理：

```gherkin
Feature: 任务创建

  Background:
    Given 【API】以普通用户身份登录

  Scenario: 提交有效任务名称后创建成功
    ...
```

### 6.2 Background 的内容边界

Background 只放**所有 Scenario 共用的前置条件**。若某个前置条件只有部分 Scenario 需要，放入各自 Scenario 的 Given，不放 Background：

```gherkin
# ✅ Background 只放登录态（所有 Scenario 都需要）
Background:
  Given 【API】以普通用户身份登录

# ✅ 特定数据前置放在 Scenario 的 Given 中
Scenario: 编辑任务后名称同步更新
  Given 【API】已存在任务"修复登录问题"
  When  【API】编辑任务名称为"修复注册问题"
  Then  【API】该任务名称已更新为"修复注册问题"

# ❌ 将特定数据前置放入 Background，导致与之无关的 Scenario 也执行了数据准备
Background:
  Given 【API】以普通用户身份登录
  And   【API】已存在任务"修复登录问题"   ← 只有部分 Scenario 需要此数据
```

### 6.3 多角色场景

当同一 Feature 中需要验证不同角色的行为时，在 Scenario 的 Given 中覆盖登录态：

```gherkin
Feature: 任务权限管理

  Background:
    Given 【API】以普通用户身份登录    ← 默认角色

  Scenario: 普通用户无法删除他人任务
    # 沿用 Background 的登录态，无需额外声明
    Given 【API】已存在其他用户的任务"公共任务"
    When  【API】删除任务"公共任务"
    Then  【API】操作被拒绝，提示"无权限"

  Scenario: 管理员可以删除任何任务
    Given 【API】切换为管理员身份      ← 覆盖 Background 的登录态
    And   【API】已存在任务"公共任务"
    When  【API】删除任务"公共任务"
    Then  【API】任务删除成功
```

---

## 7. 从 UI Feature 转换为 API Feature 的规则

### 7.1 三类处理规则

转换不是字符串替换，是语义层的重新映射。每个 UI Step 按以下规则处理：

**删除类**：UI 层特有的步骤，API 层没有对应概念，直接删除不转换。

| UI Step 类型 | 示例 | 处理 |
|------------|------|------|
| 页面导航 | `Given 用户在任务列表页` | 删除 |
| 页面等待 | `And 等待列表加载完成` | 删除 |
| UI 元素状态 | `And 提交按钮为可用状态` | 删除 |
| 视觉反馈 | `Then 页面显示绿色成功提示` | 转换（见下） |

**转换类**：保留业务语义，调整措辞，加 `【API】` 前缀。

| UI Step 类型 | UI 写法 | API 写法 |
|------------|---------|---------|
| 业务操作 | `When 用户新增任务，任务名称"xxx"` | `When 【API】新增任务，任务名称"xxx"` |
| 视觉断言 | `Then 页面显示"任务创建成功"` | `Then 【API】任务创建成功` |
| 数据状态断言 | `Then 任务列表包含"xxx"` | `Then 【API】任务列表包含"xxx"` |
| 前置数据状态 | `Given 系统中存在任务"xxx"` | `Given 【API】已存在任务"xxx"` |

**保留类**：业务语义完全一致，仅加 `【API】` 前缀。

```gherkin
# UI
Given 系统中存在任务"修复登录问题"
# API（保留，加前缀）
Given 【API】系统中存在任务"修复登录问题"
```

### 7.2 Background 的转换规则

UI Feature 的 Background 中通常包含页面导航，API Feature 的 Background 只保留登录态：

```gherkin
# UI Background
Background:
  Given 用户已登录系统
  And   用户在任务列表页      ← 删除（页面导航）

# API Background
Background:
  Given 【API】以普通用户身份登录
```

### 7.3 不转换的情况

以下情况的 UI Scenario **不生成对应的 API Scenario**：

| 情况 | 原因 |
|------|------|
| 纯 UI 交互验证（拖拽排序、键盘快捷键） | 无对应接口语义 |
| 纯视觉验证（颜色、布局、动画） | 无对应接口语义 |
| UI 错误提示的具体样式验证 | 接口层只验证错误信息内容，不验证样式 |

### 7.4 转换完整示例

```gherkin
# ── UI Feature（输入）──────────────────────────────────────────

Feature: 任务创建

  Background:
    Given 用户已登录系统
    And   用户在任务列表页

  Scenario: 提交有效任务名称后创建成功
    When  用户新增任务，任务名称"修复登录问题"
    Then  页面显示"任务已创建"的成功提示
    And   任务列表顶部出现"修复登录问题"

  Scenario: 任务名称为空时提交被拒绝
    When  用户提交空任务名称
    Then  输入框下方显示红色错误提示"任务名称不能为空"
    And   提交按钮保持可用状态

  Scenario: 编辑任务后名称同步更新
    Given 系统中存在任务"修复登录问题"
    When  用户将任务名称修改为"修复注册问题"
    And   用户保存修改
    Then  任务名称更新为"修复注册问题"


# ── API Feature（输出）──────────────────────────────────────────

Feature: 任务创建

  作为一名项目成员
  我希望通过接口创建和管理任务
  以便验证任务管理的核心业务逻辑

  Background:
    Given 【API】以普通用户身份登录

  Scenario: 提交有效任务名称后创建成功
    When  【API】新增任务，任务名称"修复登录问题"
    Then  【API】任务创建成功
    And   【API】任务列表顶部为"修复登录问题"

  Scenario: 任务名称为空时请求被拒绝
    When  【API】新增任务，任务名称""
    Then  【API】操作被拒绝，提示"任务名称不能为空"

  Scenario: 编辑任务后名称同步更新
    Given 【API】已存在任务"修复登录问题"
    When  【API】编辑任务名称为"修复注册问题"
    Then  【API】该任务名称已更新为"修复注册问题"
```

转换说明：
- Background 中删除页面导航，保留登录态并转换写法
- Scenario 2 的视觉断言（红色错误提示、按钮状态）删除，只保留业务结果
- Scenario 3 中"用户保存修改"（UI 操作）合并入 When 的业务语义，不单独成行

---

## 8. 典型反例与修正示例

### 反例 1：HTTP 细节泄漏到 Feature 文件

```gherkin
# ❌ Then 描述了 HTTP 响应细节
Scenario: 新增任务成功
  When  【API】新增任务，任务名称"修复登录问题"
  Then  【API】响应状态码为 201
  And   【API】响应体 data.id 不为空
  And   【API】响应体 data.name 等于"修复登录问题"
```

**修正**：HTTP 断言下沉到 Jinja2 模板的 checkpoint，Feature 只写业务结果。

```gherkin
# ✅
Scenario: 新增任务成功
  When  【API】新增任务，任务名称"修复登录问题"
  Then  【API】任务创建成功
```

---

### 反例 2：数据准备暴露接口调用链

```gherkin
# ❌ Given 暴露了数据准备的接口调用顺序
Scenario: 在项目下新增任务
  Given 【API】调用 POST /api/login 获取 token
  And   【API】调用 POST /api/projects 创建项目"电商平台"
  And   【API】从响应中提取 project_id
  When  【API】在项目"电商平台"下新增任务"修复登录问题"
  Then  【API】任务创建成功
```

**修正**：接口调用链封装进 Step Definition，Feature 只描述数据状态。

```gherkin
# ✅
Scenario: 在项目下新增任务
  Given 【API】项目"电商平台"已存在
  When  【API】在项目"电商平台"下新增任务"修复登录问题"
  Then  【API】任务创建成功
```

---

### 反例 3：将 UI 视觉断言直接转换（未做语义转换）

```gherkin
# ❌ 视觉断言直接加了前缀，无法在 API 层执行
Scenario: 新增任务成功
  When  【API】新增任务，任务名称"修复登录问题"
  Then  【API】页面显示绿色成功提示
  And   【API】任务列表顶部出现新任务卡片
```

**修正**：视觉描述转换为业务结果描述。

```gherkin
# ✅
Scenario: 新增任务成功
  When  【API】新增任务，任务名称"修复登录问题"
  Then  【API】任务创建成功
  And   【API】任务列表包含"修复登录问题"
```

---

### 反例 4：Background 堆积特定场景的数据前置

```gherkin
# ❌ Background 里的数据准备只有部分 Scenario 需要
Background:
  Given 【API】以普通用户身份登录
  And   【API】已存在任务"修复登录问题"
  And   【API】已存在项目"电商平台"

# 结果：所有 Scenario 都执行了数据准备，但有些 Scenario 根本不需要这些数据
Scenario: 新增任务成功
  # 这个 Scenario 不需要"修复登录问题"和"电商平台"，但 Background 还是创建了
  When  【API】新增任务，任务名称"新任务"
  Then  【API】任务创建成功
```

**修正**：Background 只保留所有 Scenario 共用的前置，特定数据前置放到各自 Scenario。

```gherkin
# ✅
Background:
  Given 【API】以普通用户身份登录

Scenario: 新增任务成功
  When  【API】新增任务，任务名称"新任务"
  Then  【API】任务创建成功

Scenario: 编辑已有任务
  Given 【API】已存在任务"修复登录问题"
  When  【API】编辑任务名称为"修复注册问题"
  Then  【API】该任务名称已更新为"修复注册问题"
```

---

## 9. AI 转换链路的约束

### 9.1 AI 转换的三个输入

| 输入 | 作用 | 必需 |
|------|------|------|
| UI Feature 文件 | 提供业务场景结构、Scenario 名称、业务参数值 | ✅ |
| 捕获的接口请求（scenario_requests.json） | 辅助确认 UI Step 对应的接口调用粒度 | 推荐 |
| 本规范文档（精简版 System Prompt） | 约束输出格式、语言层级、颗粒度 | ✅ |

接口请求数据不是必需输入，但有它时 AI 可以更准确判断某个 UI Step 背后是否涉及多个接口调用，从而决定 API Step 的粒度。

### 9.2 给 AI 的 System Prompt 精简版

```
## 任务
将 UI Feature 文件转换为 API Feature 文件。

## 硬性规则
1. 所有 Step 加 【API】前缀
2. 删除所有页面导航、UI 等待、UI 元素状态类 Step
3. 将视觉断言转换为业务结果描述（不写状态码、不写响应字段名）
4. Given 描述数据状态，不描述接口调用过程
5. Background 只保留登录态声明
6. 不补充 UI Feature 中没有的 Scenario（不做额外推断）
7. Scenario 名称与 UI Feature 保持一致或微调措辞，不改变语义

## 转换规则速查
删除类：在某页面 / 等待加载 / 按钮状态 / 弹窗出现
转换类：
  "页面显示xxx提示" → "操作成功" 或 "操作被拒绝，提示xxx"
  "用户点击xxx按钮" → 合并入上一个业务动作的 When
  "用户在xxx输入框填写" → 合并入 When 的参数
保留类：数据状态描述、业务操作描述（加前缀即可）

## 输出格式
- 输出完整的 .feature 文件内容
- 对每个删除或转换的 Step，在行末用注释标注处理原因
  例：# [删除] 页面导航，API 层无对应概念
      # [转换] 视觉断言 → 业务结果
- 对无法确定转换方式的 Step，标注 # [待确认]
```

### 9.3 转换后的人工审查清单

AI 输出的 API Feature 文件在提交前须完成以下审查：

```markdown
- [ ] 所有 Step 带有 【API】前缀
- [ ] Feature 文件中无 HTTP 方法、URL、状态码、响应字段名
- [ ] Background 只包含登录态声明，不包含特定场景的数据前置
- [ ] Given 使用数据状态描述，不使用接口调用描述
- [ ] Then 使用业务结果描述，不使用视觉描述
- [ ] Scenario 名称与对应 UI Feature 保持语义一致
- [ ] 标注为 [待确认] 的 Step 已人工处理
- [ ] 文件存放在 features/api/ 目录，文件名与 UI Feature 一致
```

---

## 10. Code Review Checklist

在 PR 描述模板中，涉及 `features/api/` 目录变更时必填：

```markdown
## API Feature 颗粒度审查

### 文件层级
- [ ] 文件名与对应 UI Feature 文件一致
- [ ] Feature 描述包含用户故事（作为/我希望/以便）
- [ ] Scenario 总数在 5–15 个之间

### Step 语言
- [ ] 所有 Step 带 【API】前缀
- [ ] 无 HTTP 方法、URL、状态码、响应字段名
- [ ] 无模板文件名、无 variable_extract 字段名
- [ ] Given 使用数据状态描述
- [ ] Then 使用业务结果描述

### Background
- [ ] Background 只包含登录态，不包含特定 Scenario 的数据前置

### Scenario 原子性
- [ ] 每个 Scenario 只有 1 个 When 语义组
- [ ] Then（含 And）≤ 3 步
- [ ] 总步骤数 ≤ 10 步

### 与 UI Feature 的对齐
- [ ] Scenario 数量和名称与对应 UI Feature 基本一致
- [ ] 新增或删除的 Scenario 已在 PR 说明中注明原因
```

---

## 11. 快速判断卡片

**写 Step 时：**

```
这个 Step 里有没有出现以下词汇？
  HTTP 方法（POST/GET/PUT/DELETE）
  URL 路径（/api/xxx）
  状态码（200/201/400）
  响应字段名（data.id / body.name）
  模板名（tasks/create.j2）
→ 有：重写，下沉到 Step Definition 或模板
→ 没有：✅
```

**写 Given 时：**

```
这个 Given 描述的是"做了什么"还是"存在什么"？
→ 做了什么（调用了哪个接口）：改为数据状态描述
→ 存在什么（系统中有某数据）：✅
```

**写 Then 时：**

```
这个 Then 能让产品经理看懂吗？
→ 看不懂（包含技术术语）：改为业务结果描述
→ 看得懂：✅
```

**转换 UI Feature 时：**

```
对每个 UI Step 问：
Q1: 这是页面导航或 UI 等待类 Step？ → 删除
Q2: 这是视觉断言（显示、出现、可见）？ → 转换为业务结果
Q3: 这是 UI 操作（点击、填写）且可合并入业务动作？ → 合并
Q4: 其余情况 → 保留语义，加 【API】前缀
```

---

*本文档是活文档，随项目演进更新。如有边界情况或规则争议，以测试架构组评审结论为准。*
