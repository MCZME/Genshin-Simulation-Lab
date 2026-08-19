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
  node: {
    root: "#64748b",
    meta: "#0ea5e9",
    character: "#f59e0b",
    weapon: "#ef4444",
    artifact: "#a855f7",
    target: "#22c55e",
    input_trace: "#14b8a6",
    run_options: "#eab308",
    enum: "#f97316",
    range: "#f43f5e",
    simulation: "#6366f1",
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
