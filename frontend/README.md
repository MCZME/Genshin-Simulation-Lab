# Genshin Simulation Lab - frontend

Web 前端工程（React + TypeScript + Vite + React Flow）。

结构约定见 `docs/工程/前端工程规范.md` 与 `docs/架构/UI/UI结构与状态设计.md`。

```text
frontend/
├── src/
│   ├── app/               # 应用外壳：导航、全局状态、错误反馈
│   ├── theme/             # 主题 token
│   ├── workflow/          # 定义模型、语义注册表、校验、变体编译
│   ├── state/             # AppState / EditorState / RunState
│   ├── api/               # HTTP API 客户端与类型
│   ├── components/
│   │   ├── canvas/        # 画布、区域、节点卡、连线层、框选、小地图
│   │   ├── nodes/         # 节点编辑器与 registry
│   │   ├── panels/        # 工具栏、对象面板、问题面板、检查器、运行状态栏
│   │   ├── shell/         # 应用壳、设置弹窗、顶部栏、工具轨、状态栏
│   │   └── common/        # 输入框、资产选择器、表格、徽标等原语
│   └── views/             # 非画布页面：项目初始化
├── package.json
├── vite.config.ts
├── vitest.config.ts
└── eslint.config.js
```

常用命令：

```powershell
pnpm install
pnpm dev
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

当前状态（2026-08-20）：切片 4 图语义、校验与变体编译已落地；切片 5 画布纵向链路（配置区域 → 模拟桥 → 运行结果面板）主体已完成，正在收尾画布交互（拖入创建、删除、撤销/重做、入线顺序等）与切片 6 端到端验收。

## API 类型生成

- 后端契约变化后重新生成：先启动后端 `genshin-sim-server`（默认端口 8000），再执行 `pnpm gen:api`。
- 生成的 `src/api/schema.d.ts` 提交进仓库；typecheck 与构建不依赖后端在线。
