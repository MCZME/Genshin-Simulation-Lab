/**
 * 设计令牌：前端 UI 视觉的唯一事实源。
 *
 * 规范见 docs/架构/UI/设计系统.md。tokens.css 是本文件的 CSS 自定义属性镜像，
 * 由 theme/tokens.test.ts 锁定两侧一致；组件与样式只允许引用令牌，不新增硬编码色值。
 *
 * 色彩分两个 band：
 * - 过程色（severity / status / selection）：表达严重度与运行状态，
 *   红=失败、琥珀=过渡/注意、绿=完成、蓝=进行/中性提示；
 * - 身份色（nodeCategory / region / element / fallback）：表达对象身份。
 * 两个 band 不共享精确色值（由测试断言）；状态不得只依赖颜色（前端工程规范 6.5）。
 */

export const COLORS = {
  /** 应用底色（画布底、内嵌输入区）。 */
  background: "#0f172a",
  /** 面板与卡片表面（顶栏、侧轨、节点卡、浮层）。 */
  panel: "#1e293b",
  /** 浮层内嵌表面（下拉、悬停高亮、子分区）。 */
  panelRaised: "#263449",
  /** 卡内嵌套块表面（算子行、提取行、目录分区）。 */
  panelInset: "#243147",
  /** 选中/激活的蓝色调表面（激活选项卡、命中项、来源徽标）。 */
  panelSelected: "#1e3a5f",
  /** 默认边框（分隔线、控件描边）。 */
  border: "#334155",
  /** 强边框（悬停、选中描边、分组边框）。 */
  borderStrong: "#475569",
  /** 中性填充（空闲连接端口、默认徽标底、滚动条）；与 text-faint / status-cancelled 同值不同角色。 */
  fillNeutral: "#64748b",
  /** 主文本。 */
  text: "#e2e8f0",
  /** 次文本（标签、说明）。 */
  textMuted: "#94a3b8",
  /** 三级文本（表头、摘要值、等宽内容）。 */
  textTertiary: "#cbd5e1",
  /** 弱文本（时间戳、刻度、占位；对 background 对比度约 3.7:1，仅用于非关键辅助信息）。 */
  textFaint: "#64748b",
  /** 品牌/交互强调色（焦点环、数据端口、品牌标识）。 */
  accent: "#38bdf8",
  /** 主操作按钮底色（与配置区域色一致）。 */
  actionPrimary: "#2563eb",
  /** 选择语义色（selection 端口与徽标、选中高亮文本）。 */
  selection: "#fbbf24",
  /** 未注册/未知节点的回落色（避开过程色）。 */
  fallback: "#475569",
  /** 错误表面（错误横幅、错误边界背景）。 */
  errorSurface: "#450a0a",
  /** 错误边框。 */
  errorBorder: "#7f1d1d",
  /** 错误表面上的文本。 */
  errorText: "#fecaca",
  /** 错误文本（行内错误、错误计数）。 */
  errorTextStrong: "#f87171",
  /** 警告文本（暗底上的琥珀文本变体）。 */
  warningText: "#fbbf24",

  region: {
    configuration: "#2563eb",
    analysis: "#7c3aed",
  },

  /** 节点类别色：同类节点共享一个主色（D-034）。取值避开过程色精确值。 */
  nodeCategory: {
    runSettings: "#0ea5e9",
    teamConfig: "#facc15",
    targetConfig: "#4ade80",
    inputSequence: "#14b8a6",
    paramScan: "#f97316",
    simulation: "#6366f1",
    dataSource: "#60a5fa",
    dataProcessing: "#a855f7",
    displayConfig: "#d946ef",
    displayView: "#f43f5e",
    itemDetail: "#22d3ee",
  },

  severity: {
    error: "#ef4444",
    warning: "#f59e0b",
    info: "#3b82f6",
  },

  /** 元素显示色：仅 UI 装饰（徽标、抗性标识等），不参与仿真数值；取自游戏惯例配色。 */
  element: {
    physical: "#ece5d8",
    pyro: "#ef7938",
    hydro: "#4cc2f1",
    electro: "#af8ec1",
    cryo: "#9fd6e3",
    anemo: "#74c2a8",
    geo: "#fab632",
    dendro: "#a5c83b",
  },

  /** 批次/成员状态色：复用严重度语义（红=失败、琥珀=停止中、绿=完成、蓝=运行中）。 */
  status: {
    queued: "#94a3b8",
    running: "#3b82f6",
    stopping: "#f59e0b",
    completed: "#22c55e",
    failed: "#ef4444",
    cancelled: "#64748b",
  },
} as const;

export type NodeCategory = keyof typeof COLORS.nodeCategory;

/** 间距：4px 基网。卡内 8、卡间 12、面板 16、分区 24。 */
export const SPACING = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
} as const;

/** 字号阶梯（px）：11 为全局下限，仅用于徽标与刻度；数值字段用等宽字体保证对齐。 */
export const TYPOGRAPHY = {
  caption: 11,
  bodySmall: 12,
  body: 13,
  title: 14,
  heading: 16,
  display: 20,
  lineHeight: {
    dense: 1.4,
    body: 1.5,
    prose: 1.6,
  },
} as const;

/** 圆角：控件 4 < 浮层 6 < 卡片 8 < 容器 12。 */
export const RADIUS = {
  control: 4,
  overlay: 6,
  card: 8,
  container: 12,
} as const;

/** 阴影三级：卡片 < 浮层 < 弹窗。 */
export const SHADOW = {
  card: "0 4px 12px rgba(0, 0, 0, 0.35)",
  overlay: "0 8px 24px rgba(0, 0, 0, 0.45)",
  modal: "0 16px 48px rgba(0, 0, 0, 0.5)",
} as const;

/** 层级：工具面板 < 下拉/尺寸手柄 < 浮层 < 拖拽幽灵 < 弹窗。 */
export const Z_INDEX = {
  toolPanel: 20,
  dropdown: 30,
  resizeHandle: 30,
  popover: 40,
  dragGhost: 50,
  modal: 100,
} as const;

export const FONT = {
  body: `"Segoe UI", "Microsoft YaHei", system-ui, sans-serif`,
  mono: `ui-monospace, "Cascadia Mono", Consolas, monospace`,
} as const;
