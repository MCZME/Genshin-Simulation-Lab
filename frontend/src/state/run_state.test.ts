import { describe, expect, it } from "vitest";
import type { RunStatusResponse } from "../api/client";
import { applyRunView, createEmptyRunState, isRunTerminal, recordMemberMetrics } from "./run_state";

function runView(
  state: string,
  members: Array<{ item_id: string; state: string; session_id: string | null }>,
): RunStatusResponse {
  return {
    run_id: "run-1",
    name: "批次",
    state,
    concurrency: 2,
    cancel_requested: false,
    member_count: members.length,
    members: members.map((member) => ({
      item_id: member.item_id,
      state: member.state,
      session_id: member.session_id,
      error_code: null,
      error_message: null,
      created_at: "2026-08-19T00:00:00+00:00",
      started_at: null,
      finished_at: null,
    })),
  } as RunStatusResponse;
}

describe("run state", () => {
  it("创建空运行状态", () => {
    const state = createEmptyRunState();
    expect(state.runId).toBeNull();
    expect(state.members).toEqual([]);
    expect(state.metrics).toEqual({});
  });

  it("应用批次视图并保留指标", () => {
    let state = createEmptyRunState();
    state = applyRunView(
      state,
      runView("running", [
        { item_id: "a", state: "running", session_id: null },
        { item_id: "b", state: "queued", session_id: null },
      ]),
    );
    expect(state.runId).toBe("run-1");
    expect(state.state).toBe("running");
    expect(state.members.map((member) => member.item_id)).toEqual(["a", "b"]);

    state = recordMemberMetrics(state, "a", {
      frames_run: 10,
      total_damage: { key: "total_damage", value: 100 },
    } as never);
    state = applyRunView(
      state,
      runView("completed", [{ item_id: "a", state: "completed", session_id: "s-1" }]),
    );
    expect(state.state).toBe("completed");
    expect(state.members[0].session_id).toBe("s-1");
    expect(state.metrics.a.total_damage.value).toBe(100);
  });

  it("判断终态", () => {
    expect(isRunTerminal("completed")).toBe(true);
    expect(isRunTerminal("partial")).toBe(true);
    expect(isRunTerminal("failed")).toBe(true);
    expect(isRunTerminal("cancelled")).toBe(true);
    expect(isRunTerminal("running")).toBe(false);
    expect(isRunTerminal(null)).toBe(false);
  });
});
