export const COLORS = {
  background: "#0f172a",
  panel: "#1e293b",
  panelRaised: "#263449",
  border: "#334155",
  borderStrong: "#475569",
  text: "#e2e8f0",
  textMuted: "#94a3b8",
  region: {
    configuration: "#2563eb",
    analysis: "#7c3aed",
  },
  /** 节点类别色：同类节点共享一个主色（决策 2.34，2026-08-27）。 */
  nodeCategory: {
    runSettings: "#0ea5e9",
    teamConfig: "#f59e0b",
    targetConfig: "#22c55e",
    inputSequence: "#14b8a6",
    variantScan: "#f97316",
    simulation: "#6366f1",
    dataSource: "#3b82f6",
    dataProcessing: "#a855f7",
    displayConfig: "#ec4899",
    displayView: "#ef4444",
  },
  severity: {
    error: "#ef4444",
    warning: "#f59e0b",
    info: "#3b82f6",
  },
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

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
} as const;

export const FONT = {
  body: `"Segoe UI", "Microsoft YaHei", system-ui, sans-serif`,
  mono: `ui-monospace, "Cascadia Mono", Consolas, monospace`,
} as const;
