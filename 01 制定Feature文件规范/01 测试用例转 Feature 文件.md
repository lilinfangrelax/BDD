将 模块 的某一个测试用例导出为 markdown 文档，然后交给AI生成对应的 BDD feature 文件，再将 feature 通过AI去进行浏览器录制，生成测试代码  --> 难点是什么？

## Markdown → AI 生成 Feature 文件  ⭐ 核心难点

Step 复用 vs 新增的边界判断


- AI 不知道已有 Step Definition 库的内容
- 很容易生成"新步骤"，实际上已有语义相同的 Step，导致重复定义爆炸
- 解决方向：需要把现有 Step Catalog 作为上下文注入 Prompt


业务语言 vs 技术实现的分层

- Feature 文件应该是纯业务语言，但 AI 往往倾向于写出带技术细节的步骤
  - ❌ When 我向 /api/v1/login 发送 POST 请求
  - ✅ When 我以有效凭证登录系统
- 需要严格的 Prompt 约束 + 后处理校验

参数化与 Scenario Outline 的判断

- AI 很难自动判断何时应该用 Scenario Outline + Examples
- 手工测试用例里的多组数据往往散落在步骤描述里

## Feature → AI 驱动浏览器录制 ⭐⭐ 最大难点

Feature 步骤 → 具体操作的映射鸿沟
```
Given 用户已登录系统
  ↓ AI 需要知道：
  - 登录页 URL 是什么？
  - 用户名/密码从哪里取？
  - 登录成功的判断标准是什么？
```
业务语言到 UI 操作之间存在语义跳跃，没有 ground truth 的情况下 AI 只能猜。

UI 定位的脆弱性
- AI 生成的 locator 往往基于文本或结构推断
- 与真实 DOM 不匹配率极高


状态依赖与环境问题

- 某些步骤依赖特定的数据状态（账号有余额、订单存在等）
- Browser Agent 很难自动构造这些前置状态
- 失败时的回溯/重试策略复杂

动态内容与异步等待
- AI 生成的代码缺乏对 loading 状态、动态渲染的感知
- waitForSelector 的时机需要人工经验

阶段四：测试代码的可用性问题
即使前三步都通过了，生成的代码还面临：

可维护性差：缺乏 Page Object 封装，定位器硬编码
Step Definition 孤岛：新生成的 steps 与现有框架风格不统一
没有断言：AI 容易只生成操作步骤，缺少有效的 assertion
没有数据隔离：测试之间的数据污染
