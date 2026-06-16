# Step Index Schema

This document describes the JSON format of the step index returned by the teshi daemon's catalog API (`GET /api/v1/steps/catalog`) and the `teshi steps catalog` CLI command.

## Top-Level Structure

The catalog response is a **JSON array** of step entry objects. The array may be returned directly or wrapped in a top-level object with an `"entries"`, `"steps"`, `"catalog"`, or `"data"` key.

### Direct array (preferred)

```json
[
  { "keyword": "Given", "text": "用户已登录系统", "source": "features/login.feature", "reuse_count": 45 },
  { "keyword": "When", "text": "用户点击"<button_text>"", "source": "features/navigation.feature", "reuse_count": 32 }
]
```

### Wrapped form

```json
{
  "entries": [
    { "keyword": "Given", "text": "用户已登录系统", ... }
  ],
  "total": 860,
  "generated_at": "2026-06-15T04:00:00Z"
}
```

## Entry Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | yes | Step text, possibly with `<param>` placeholders |
| `keyword` | string | yes | BDD keyword: Given, When, Then, And, But |
| `source` | string | no | Source file path (relative) where the step is defined |
| `reuse_count` | integer | no | Number of times this step has been reused (default 0) |
| `count` | integer | no | Legacy alias for `reuse_count` |
| `step_type` | string | no | Semantic type: `action`, `assertion`, `setup` |
| `tags` | array of strings | no | Associated tags, e.g. `["smoke", "regression"]` |

### Field details

- **`text`**: The step text after the keyword. May contain `<param>` placeholders in angle brackets. Example: `用户创建任务"<task_name>"`. Placeholder names use snake_case.
- **`keyword`**: One of `Given`, `When`, `Then`, `And`, `But`. Always capitalized.
- **`source`**: Relative file path pointing to the defining `.feature` or step definition file. Useful for traceability. Format: `features/<module>/<feature>.feature`.
- **`reuse_count`** / **`count`**: Integer count of how many times this exact step (or a semantically equivalent one) has been reused across the project. Used to identify high-value steps for reuse optimization.
- **`step_type`**: Optional semantic classification:
  - `setup` — Precondition / context setup (typically paired with `Given`)
  - `action` — User or system action (typically paired with `When`)
  - `assertion` — Expected outcome verification (typically paired with `Then`)
- **`tags`**: Optional list of tag strings inherited from the scenario or feature file. Useful for filtering by test category.

## Example Catalog Response

```json
{
  "entries": [
    {
      "text": "用户已登录系统",
      "keyword": "Given",
      "source": "features/auth/login.feature",
      "reuse_count": 45,
      "step_type": "setup",
      "tags": ["smoke", "auth"]
    },
    {
      "text": "用户点击\"<button_text>\"",
      "keyword": "When",
      "source": "features/navigation/navigate.feature",
      "reuse_count": 32,
      "step_type": "action"
    },
    {
      "text": "系统显示页面\"<page_name>\"",
      "keyword": "Then",
      "source": "features/navigation/verify.feature",
      "reuse_count": 28,
      "step_type": "assertion"
    }
  ],
  "total": 3,
  "generated_at": "2026-06-15T04:00:00Z"
}
```

## Normalization Rules

When comparing step texts for deduplication and reuse detection, the following normalization is applied:

1. **Collapse whitespace**: All runs of whitespace characters are reduced to a single space.
2. **Lowercase**: Text is converted to lowercase.
3. **Strip punctuation**: Characters outside `\w`, whitespace, angle brackets (`< >`), and CJK range (`\u4e00-\u9fff`) are removed.
4. **Parameter placeholders**: `<param>` names are considered equivalent — only the presence of a placeholder matters, not its name. `<button_text>` and `<task_name>` are both treated as `<param>` for comparison purposes.

### Normalization comparison matrix

| Original Text | Normalized |
|---|---|
| `用户已登录系统` | `用户已登录系统` |
| `用户点击"<button_text>"` | `用户点击<param>` |
| `用户 点击 "<task_name>"` | `用户点击<param>` |
| `Given 用户已登录系统` | *(keyword removed before normalization)* |

## Version History

- **1.0** (2026-06-15): Initial schema. Direct array and wrapped response formats. Basic entry fields.
