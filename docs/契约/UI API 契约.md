# UI API 契约

> 状态：已确认（2026-08-17）；端点与字段在实现时按 OpenAPI 定稿。
> 关联：[模块边界设计](../架构/模块边界设计.md)、[前端工程规范](../工程/前端工程规范.md)。

## 1. 总则

- 前端与后端同源：`infrastructure/http_api/` 托管 `frontend/` 构建产物并提供 API，生产环境不出现跨域。
- API 前缀 `/api/v1`；契约变更走版本升级，不静默破坏旧版本。
- 请求/响应使用 JSON；DTO 用 pydantic 定义在 `infrastructure/http_api/`，领域层保持 dataclass。
- OpenAPI 文档作为契约来源，前端通过 `openapi-typescript` 生成 TypeScript 类型。
- 错误响应统一为 `{ "code": "...", "message": "...", "details": [...] }`；`details` 使用[工作流定义契约](./工作流定义契约.md)的结构化诊断数组。

## 2. MVP 端点

### 工作区

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/workspace` | 数据目录、资产库版本、初始化状态 |

### 工作流

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/workflows` | 工作流列表 |
| POST | `/api/v1/workflows` | 创建工作流 |
| GET | `/api/v1/workflows/{id}` | 读取工作流定义 |
| PUT | `/api/v1/workflows/{id}` | 保存工作流定义（显式保存动作） |
| DELETE | `/api/v1/workflows/{id}` | 删除工作流 |
| POST | `/api/v1/workflows/{id}/validate` | 校验并返回结构化诊断 |
| GET | `/api/v1/node-types` | 节点类型注册表（语义 spec） |
| GET | `/api/v1/node-types/{kind}` | 单个节点类型 spec |

### 运行

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/runs` | 提交运行（工作流 ID 或内联定义），返回批次 ID 与成员列表 |
| GET | `/api/v1/runs/{run_id}` | 批次整体状态 |
| GET | `/api/v1/runs/{run_id}/members` | 成员状态列表 |
| POST | `/api/v1/runs/{run_id}/cancel` | 取消整批 |

成员状态：`queued / running / completed / failed / cancelled`；运行中被取消的成员在完成前显示“正在停止”。

### 结果

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/results` | 运行列表（分页/状态过滤） |
| GET | `/api/v1/results/{session_id}` | 运行详情 |
| GET | `/api/v1/results/{session_id}/events` | 事件分页查询 |
| GET | `/api/v1/results/{session_id}/metrics` | 结果摘要指标 |

### 资产（只读）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/assets/{asset_type}` | 按类型搜索/列表 |
| GET | `/api/v1/assets/{asset_type}/{asset_key}` | 资产详情 |

## 3. 状态与错误语义

- 提交运行成功返回批次 ID；运行失败、校验失败返回 `details` 诊断。
- 批次状态由成员状态派生：全部终态即批次终态；部分失败是正常状态，界面按成员展示。
- 任务状态第一版通过轮询获取；后续增加 SSE/WebSocket 订阅端点时不改成员状态模型。

## 4. 后置能力

- 分析区域端点（查询/指标/聚合/对比/视图）。
- 文件上传/下载（输入 JSON、结果导出）。
- 账号、多用户、数据隔离。
- 资产库构建/更新端点（初始化与更新走 CLI/安装包流程）。

## 5. 安全

- 本地模式默认绑定 `127.0.0.1`。
- 网页服务模式可绑定 `0.0.0.0`；暴露到公网时必须启用访问令牌（`X-Access-Token` 请求头）或由反向代理负责 TLS 与访问控制。
- API 只暴露白名单能力；不允许任意文件路径访问，不返回内部数据库/文件路径。
