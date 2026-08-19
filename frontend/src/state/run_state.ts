import type { MetricsResponse, RunMemberStatus, RunStatusResponse } from "../api/client";

export interface RunState {
  runId: string | null;
  name: string;
  state: string | null;
  cancelRequested: boolean;
  members: RunMemberStatus[];
  metrics: Record<string, MetricsResponse>;
}

export function createEmptyRunState(): RunState {
  return {
    runId: null,
    name: "",
    state: null,
    cancelRequested: false,
    members: [],
    metrics: {},
  };
}

export function applyRunView(state: RunState, view: RunStatusResponse): RunState {
  return {
    runId: view.run_id,
    name: view.name,
    state: view.state,
    cancelRequested: view.cancel_requested,
    members: view.members.map((member) => ({ ...member })),
    metrics: state.metrics,
  };
}

export function recordMemberMetrics(
  state: RunState,
  itemId: string,
  metrics: MetricsResponse,
): RunState {
  return { ...state, metrics: { ...state.metrics, [itemId]: metrics } };
}

export function isRunTerminal(state: string | null): boolean {
  return state === "completed" || state === "partial" || state === "failed" || state === "cancelled";
}
