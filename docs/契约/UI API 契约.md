# UI API 契约

> 状态：已确认（2026-08-17）；字段在实现时按 OpenAPI 定稿，本文固定端点、语义与响应形状。
> 关联：[模块边界设计](../架构/模块边界设计.md)、[前端工程规范](../工程/前端工程规范.md)、[模拟输入契约](./模拟输入契约.md)、[工作流定义契约](./工作流定义契约.md)、[项目决策记录](../决策/项目决策记录.md) 2.29。

## 1. 总则

- 前端与后端同源：`server/` 托管 `frontend/` 构建产物并提供 API，生产环境不出现跨域。
- API 前缀 `/api/v1`；契约变更走版本升级，不静默破坏旧版本。
- 请求/响应使用 JSON，`Content-Type: application/json`。
- DTO 用 pydantic 定义在 `server/`，领域层保持 dataclass。
- OpenAPI 文档作为契约来源，前端通过 `openapi-typescript` 生成 TypeScript 类型。
- 时间字段为 UTC ISO-8601，精确到秒（与现有任务模型一致）。
- 错误响应统一为：

```json
{
  "code": "validation_failed",
  "message": "面向用户的短说明",
  "details": []
}
```

- `details` 只用于 `SimulationInput` 与请求字段诊断，不承载工作流图诊断。图诊断只存在于前端。
- 诊断项形状：

```json
{
  "severity": "error",
  "code": "CONFIG_INVALID",
  "message": "team[0].character.asset_key 无效",
  "item_id": "e-1",
  "path": "team[0].character.asset_key"
}
```

- `item_id` / `path` 可空；`item_id` 在批次校验与提交中指向对应成员。
- API 不返回内部文件系统路径、数据库路径或 `handler_key`。

## 2. MVP 端点一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/workspace` | 初始化状态与资产库版本 |
| GET | `/api/v1/settings` | 读取界面偏好设置（config.toml `ui` 节） |
| PUT | `/api/v1/settings` | 保存界面偏好设置 |
| GET | `/api/v1/workflows` | 工作流存档列表 |
| POST | `/api/v1/workflows` | 创建空工作流存档 |
| GET | `/api/v1/workflows/{id}` | 读取工作流 JSON |
| PUT | `/api/v1/workflows/{id}` | 整份替换保存 |
| DELETE | `/api/v1/workflows/{id}` | 删除存档 |
| POST | `/api/v1/inputs/validate` | 校验已展开成员，不跑仿真 |
| POST | `/api/v1/runs` | 提交已展开成员，启动批次 |
| GET | `/api/v1/runs/{run_id}` | 批次状态（含全部成员，供轮询） |
| POST | `/api/v1/runs/{run_id}/cancel` | 取消整批 |
| GET | `/api/v1/results` | 历史运行列表 |
| GET | `/api/v1/results/{session_id}` | 运行详情（不含事件流） |
| GET | `/api/v1/results/{session_id}/metrics` | 摘要指标 |
| GET | `/api/v1/results/{session_id}/events` | 事件分页（摘要面板不依赖） |
| GET | `/api/v1/assets/{asset_type}` | 按类型搜索/列表 |
| GET | `/api/v1/assets/{asset_type}/{source_id}` | 资产详情 |

不提供：`/workflows/{id}/validate`、`/node-types`、`/runs/{run_id}/members`、按工作流 ID 或内联图提交运行。

## 3. 工作区

### `GET /api/v1/workspace`

```json
{
  "initialized": true,
  "asset_db_version": "2026.08.17",
  "name": "Genshin Simulation Lab"
}
```

- `initialized` 为 false 时 `asset_db_version` 为空字符串。
- 不返回 `data_dir` 或数据库路径。
- 未初始化时，除本端点外的 MVP 端点返回 `409` / `workspace_not_initialized`。

## 4. 界面偏好设置

设置持久化在项目配置（`config.toml` 的 `ui` 节，见[项目决策记录](../决策/项目决策记录.md) 2.34 修订），不落在浏览器存储；字段语义由前端定义，后端只做类型校验。未初始化时与其它端点一致返回 `409`。

响应同时携带 `workspace.data_dir` 供配置面板只读展示（用户自配项，不视为内部路径泄漏；`/workspace` 端点仍不返回它）。

### `GET /api/v1/settings`

```json
{ "run_animation": true, "workspace": { "data_dir": "data" } }
```

### `PUT /api/v1/settings`

请求体只含界面偏好字段：`run_animation` 必填布尔值，非法值 `400` / `validation_failed`；工作区节不可经此修改。响应为保存后的完整设置视图。写入经 tomlkit 保留 config.toml 用户注释。

## 5. 工作流存档

后端把文件当作不透明 JSON 读写，不解析图语义，不校验节点/连线。`id` 由服务端生成，文件系统安全，不使用显示名。

空骨架：

```json
{
  "schema_version": 1,
  "meta": { "name": "未命名工作流" },
  "regions": [],
  "nodes": [],
  "edges": [],
  "layout": {}
}
```

### `GET /api/v1/workflows`

```json
{
  "items": [
    { "id": "wf_ab12cd34", "name": "主配队", "updated_at": "2026-08-17T12:00:00+00:00" }
  ]
}
```

列表按 `updated_at` 降序。不返回完整定义。

### `POST /api/v1/workflows`

请求：`{ "name": "未命名工作流" }`。`name` 缺省时用 `未命名工作流`。

响应 `201`：

```json
{
  "id": "wf_ab12cd34",
  "name": "未命名工作流",
  "updated_at": "2026-08-17T12:00:00+00:00",
  "definition": {}
}
```

`definition` 为写入后的空骨架，`meta.name` 与 `name` 一致。

### `GET /api/v1/workflows/{id}`

响应形状同创建。`404` / `not_found`。

### `PUT /api/v1/workflows/{id}`

请求体为完整 `definition`（工作流 JSON）。服务端不校验图；只要求是 JSON 对象。`name` 取 `definition.meta.name`，缺省则保留原名。

响应形状同 GET。不存在则 `404`，不隐式创建。重命名也走本端点。

### `DELETE /api/v1/workflows/{id}`

成功 `204`。不存在 `404`。

## 6. 输入校验

### `POST /api/v1/inputs/validate`

给配置区域边界预览用：校验已展开成员，不创建任务、不写结果库。

请求：

```json
{
  "members": [
    { "item_id": "e-1", "input": { "schema_version": 2, "kind": "simulation_input" } }
  ]
}
```

- `members` 必填，有序，长度 1–200。
- `item_id` 批次内唯一；`input` 为完整 [SimulationInput](./模拟输入契约.md) 文档。
- 超限 `400` / `batch_too_large`；`item_id` 重复 `400` / `duplicate_item_id`。

响应始终 `200`（请求本身合法时），由每条 `ok` 表达成败，方便一次展示全部成员问题：

```json
{
  "ok": false,
  "members": [
    { "item_id": "e-1", "ok": true, "details": [] },
    {
      "item_id": "e-2",
      "ok": false,
      "details": [
        {
          "severity": "error",
          "code": "CONFIG_INVALID",
          "message": "缺少可用角色实现",
          "item_id": "e-2",
          "path": "team[0].character.asset_key"
        }
      ]
    }
  ]
}
```

顶层 `ok` 为全部成员都通过。校验覆盖输入结构、资产存在性与 handler 可运行性；不暴露 `handler_key`。

## 7. 批次运行

后端只认已展开成员，不解析工作流图。

成员状态：`queued` / `running` / `stopping` / `completed` / `failed` / `cancelled`。

- `stopping`：整批取消已发出，该成员仍在跑，跑完后标 `cancelled`。
- 终态：`completed` / `failed` / `cancelled`。

批次状态由成员派生：

| state | 含义 |
| --- | --- |
| `queued` | 全部 `queued` |
| `running` | 未取消，且存在未终态成员 |
| `stopping` | 已请求取消，且仍有未终态成员 |
| `completed` | 全部 `completed` |
| `partial` | 全部终态，含成功与失败，且未请求取消 |
| `failed` | 全部 `failed` |
| `cancelled` | 已请求取消，且全部终态 |

部分失败是正常结果。轮询只使用 `GET /api/v1/runs/{run_id}`，不拆成员子资源。

### `POST /api/v1/runs`

```json
{
  "name": "可选批次名",
  "concurrency": 4,
  "members": [
    { "item_id": "e-1", "input": { "schema_version": 2, "kind": "simulation_input" } }
  ]
}
```

- `members` 规则与校验端点相同。
- `concurrency` 可选，整数 1–16；缺省 `min(4, CPU)`。
- 先按校验端点同一套规则检查全部成员；任一条失败则整批不提交，响应 `400` / `validation_failed`，`details` 带齐所有失败项。
- 成功 `202`，响应为批次视图（见下）。不接受工作流 ID 或内联图定义。

### `GET /api/v1/runs/{run_id}`

```json
{
  "run_id": "run_01hxyz",
  "name": "主配队扫描",
  "state": "running",
  "concurrency": 4,
  "cancel_requested": false,
  "member_count": 2,
  "members": [
    {
      "item_id": "e-1",
      "state": "completed",
      "session_id": "a1b2c3",
      "error_code": null,
      "error_message": null,
      "created_at": "2026-08-17T12:00:00+00:00",
      "started_at": "2026-08-17T12:00:01+00:00",
      "finished_at": "2026-08-17T12:00:08+00:00"
    },
    {
      "item_id": "e-2",
      "state": "running",
      "session_id": null,
      "error_code": null,
      "error_message": null,
      "created_at": "2026-08-17T12:00:00+00:00",
      "started_at": "2026-08-17T12:00:02+00:00",
      "finished_at": null
    }
  ]
}
```

- `members` 顺序与提交顺序一致。
- `session_id` 仅在该成员已写入结果库后出现。
- 不存在 `404` / `not_found`。

### `POST /api/v1/runs/{run_id}/cancel`

- 排队成员立即 `cancelled`；运行中成员改为 `stopping`，跑完后 `cancelled`，结果不进入成功展示。
- 成员的 `error_code` 与 `error_message` 只在失败或取消竞态时出现；成功、排队与取消为空。错误码分类见[批处理调度设计](../架构/批处理调度设计.md)。
- 响应形状同 GET。已终态的批次再次取消仍返回当前视图。
- 不存在 `404`。

## 8. 结果

`session_id` 是结果库身份，与 `run_id` / `item_id` 分离。工作流通过成员映射引用 `session_id`。

### `GET /api/v1/results`

查询：`limit`（默认 50，最大 200）、`offset`（默认 0）、`state`（`completed` / `failed` / `cancelled`，可空）。

```json
{
  "items": [
    {
      "session_id": "a1b2c3",
      "state": "completed",
      "name": "主配队",
      "stop_reason": "INPUT_EXHAUSTED",
      "end_frame": 600,
      "frames_run": 600,
      "created_at": "2026-08-17T12:00:00+00:00",
      "event_count": 128
    }
  ]
}
```

### `GET /api/v1/results/{session_id}`

不含事件流，不含初始快照，不含完整输入文档。

```json
{
  "session_id": "a1b2c3",
  "state": "completed",
  "name": "主配队",
  "summary": {
    "stop_reason": "INPUT_EXHAUSTED",
    "end_frame": 600,
    "frames_run": 600
  },
  "error_code": null,
  "error_message": null,
  "created_at": "2026-08-17T12:00:00+00:00",
  "started_at": "2026-08-17T12:00:01+00:00",
  "finished_at": "2026-08-17T12:00:08+00:00",
  "event_count": 128
}
```

不存在 `404`。

### `GET /api/v1/results/{session_id}/metrics`

响应为现有 `DamageMetrics.to_dict()`：

```json
{
  "frames_run": 600,
  "frames_per_second": 60,
  "total_damage": { "key": "total_damage", "value": 0, "definition": "..." },
  "dps": { "key": "dps", "value": 0, "definition": "..." },
  "highest_hit": { "key": "highest_hit", "value": 0, "definition": "..." },
  "average_hit": { "key": "average_hit", "value": 0, "definition": "..." },
  "damage_share_by_source": [],
  "damage_share_by_kind": [],
  "total_healing": { "key": "total_healing", "value": 0, "definition": "..." },
  "healing_share_by_source": []
}
```

失败/取消且无事件的运行返回 `409` / `metrics_unavailable`。

### `GET /api/v1/results/{session_id}/events`

查询：`frame_min`、`frame_max`、`event_type`、`offset`（默认 0）、`limit`（默认 100，最大 500）。

```json
{
  "items": [{ "frame": 12, "event_type": "DAMAGE_DEALT", "data": {} }],
  "offset": 0,
  "limit": 100,
  "total": 128
}
```

MVP 摘要面板不依赖本端点；时间轴与分析区域再接。

## 9. 资产

`asset_type`：`characters` / `weapons` / `artifact-sets`。路径使用 `source_id`，避免 `asset_key` 中的冒号；响应里仍给完整 `asset_key`，供写入 `SimulationInput`。

列表与详情都不返回 `handler_key`。`usable` 表示可进入仿真；不可用时 `status` 为面向用户的说明。

### `GET /api/v1/assets/{asset_type}`

查询：`q`（可选，匹配显示名与 `source_id`，不区分大小写）、`limit`（默认 50，最大 200）、`offset`（默认 0）。

```json
{
  "items": [
    {
      "asset_key": "character:barbara",
      "source_id": "barbara",
      "name": "芭芭拉",
      "usable": true,
      "status": null,
      "rarity": 4,
      "element": "Hydro",
      "weapon_type": "catalyst"
    }
  ]
}
```

- 角色：`element`、`weapon_type`、`rarity`。
- 武器：`weapon_type`、`rarity`；`element` 为 `null`。
- 圣遗物套装：`element`、`weapon_type`、`rarity` 为 `null`。
- 未知 `asset_type` 返回 `404` / `not_found`。

### `GET /api/v1/assets/{asset_type}/{source_id}`

响应为单条与列表项相同的对象，不附加内部 payload。不存在 `404`。

## 10. 状态码

| 状态 | 何时 |
| --- | --- |
| 200 | 读取、校验、取消成功 |
| 201 | 创建工作流 |
| 202 | 批次已接受 |
| 204 | 删除工作流 |
| 400 | 请求或 `SimulationInput` 校验失败、成员超限、`item_id` 重复 |
| 401 | 网页服务模式令牌无效 |
| 404 | 工作流 / 批次 / 结果 / 资产不存在 |
| 409 | 工作区未初始化，或结果尚不可计算指标 |
| 500 | 未预期错误；`message` 不泄漏内部路径 |

## 11. 后置能力

- 分析区域端点（查询/指标/聚合/对比/视图）。
- 结果详情中的输入快照与初始快照（含成员/变体标签；前端成员标签链路已随决策 2.39 移除，落地后此处是历史结果变体身份的唯一出口，见[项目决策记录](../决策/项目决策记录.md) 2.37、2.39）。
- 资产图像。
- 文件上传/下载（输入 JSON、结果导出）。
- 账号、多用户、数据隔离。
- 资产库构建/更新（走 CLI/安装包）。
- SSE/WebSocket 任务推送；增加时不改成员状态模型。

不纳入后端：工作流图校验、节点类型注册表、按工作流定义编译成员。

## 12. 安全

- 本地模式默认绑定 `127.0.0.1`。
- 网页服务模式可绑定 `0.0.0.0`；暴露到公网时必须启用访问令牌（`X-Access-Token`）或由反向代理负责 TLS 与访问控制。
- API 只暴露白名单能力；不允许任意文件路径访问。
