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

当前为目录与工具链骨架，`src/` 下尚无实现文件；`pnpm typecheck` 在源文件就位前会报告无输入。
