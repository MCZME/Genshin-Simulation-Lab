import { describe, expect, it } from "vitest";
import type { RunStatusResponse } from "../api/client";
import type { RunState } from "./run_state";
import { isRunTerminal } from "../api/runtime_subscription";
import {
  applyBatchView,
  BATCH_STATUS_LABELS,
  batchStatusFromRunState,
  createEmptyRunState,
  createRunView,
  PHASE_LABELS,
  setBatchStatus,
  setMethodStatus,
  setRunPhase,
} from "./run_state";

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

const PLAN = {
  participating: [
    {
      regionId: "region-1",
      regionName: "主配置",
      methods: [
        { nodeId: "n-root", label: "根节点", paths: [], variants: 0, overridden: false },
        { nodeId: "n-meta", label: "元信息", paths: ["meta"], variants: 1, overridden: false },
      ],
      memberCount: 2,
    },
  ],
  batches: [
    {
      nodeId: "sim-1",
      name: "主配置",
      concurrency: null,
      sourceRegionIds: ["region-1"],
      members: [
        { item_id: "a", input: {} },
        { item_id: "b", input: {} },
      ],
    },
  ],
};

describe("run state", () => {
  it("创建空运行状态", () => {
    const state = createEmptyRunState();
    expect(state.run).toBeNull();
  });

  it("从运行计划创建批次视图", () => {
    const state = { ...createEmptyRunState(), run: createRunView(PLAN) };
    expect(state.run?.phase).toBe("building");
    expect(state.run?.batches).toHaveLength(1);
    expect(state.run?.batches[0].status).toBe("pending");
    expect(state.run?.batches[0].members.map((member) => member.item_id)).toEqual(["a", "b"]);
  });

  it("应用批次视图", () => {
    let state: RunState = { ...createEmptyRunState(), run: createRunView(PLAN) };
    state = applyBatchView(
      state,
      "sim-1",
      runView("running", [
        { item_id: "a", state: "running", session_id: null },
        { item_id: "b", state: "queued", session_id: null },
      ]),
    );
    expect(state.run?.batches[0].runId).toBe("run-1");
    expect(state.run?.batches[0].state).toBe("running");
    expect(state.run?.batches[0].members.map((member) => member.item_id)).toEqual(["a", "b"]);

    state = applyBatchView(
      state,
      "sim-1",
      runView("completed", [{ item_id: "a", state: "completed", session_id: "s-1" }]),
    );
    expect(state.run?.batches[0].members[0].session_id).toBe("s-1");
  });

  it("阶段与批次状态更新", () => {
    let state: RunState = { ...createEmptyRunState(), run: createRunView(PLAN) };
    state = setRunPhase(state, "simulating");
    state = setBatchStatus(state, "sim-1", "failed", "提交失败");
    expect(state.run?.phase).toBe("simulating");
    expect(state.run?.batches[0].status).toBe("failed");
    expect(state.run?.batches[0].error).toBe("提交失败");
  });

  it("后端批次终态映射到批次步骤状态", () => {
    expect(batchStatusFromRunState("completed")).toBe("completed");
    expect(batchStatusFromRunState("partial")).toBe("completed");
    expect(batchStatusFromRunState("failed")).toBe("failed");
    // 用户取消的批次标记已取消，与整次取消跳过的批次区分（决策 2.38）。
    expect(batchStatusFromRunState("cancelled")).toBe("cancelled");
    expect(batchStatusFromRunState("running")).toBe("running");
    expect(batchStatusFromRunState(null)).toBe("running");
  });

  it("批次提交前标记校验中（决策 2.40）", () => {
    let state: RunState = { ...createEmptyRunState(), run: createRunView(PLAN) };
    state = setBatchStatus(state, "sim-1", "validating");
    expect(state.run?.batches[0].status).toBe("validating");
  });

  it("区域校验入口使用校验完成阶段与校验通过批次状态", () => {
    let state: RunState = { ...createEmptyRunState(), run: createRunView(PLAN) };
    state = setRunPhase(state, "validating");
    state = setBatchStatus(state, "sim-1", "validated");
    expect(PHASE_LABELS.validating).toBe("校验中");
    expect(PHASE_LABELS.validated).toBe("校验完成");
    expect(BATCH_STATUS_LABELS.validated).toBe("校验通过");
    expect(state.run?.phase).toBe("validating");
    expect(state.run?.batches[0].status).toBe("validated");
  });

  it("判断终态", () => {
    expect(isRunTerminal("completed")).toBe(true);
    expect(isRunTerminal("partial")).toBe(true);
    expect(isRunTerminal("failed")).toBe(true);
    expect(isRunTerminal("cancelled")).toBe(true);
    expect(isRunTerminal("running")).toBe(false);
  });
});

describe("构建步骤状态", () => {
  it("创建运行视图时方法步骤为等待，逐步更新状态", () => {
    let state: RunState = { ...createEmptyRunState(), run: createRunView(PLAN) };
    const method = state.run?.build[0].methods[0];
    expect(method?.status).toBe("pending");
    expect(method?.label).toBe("根节点");

    state = setMethodStatus(state, "region-1", "n-root", "running");
    expect(state.run?.build[0].methods[0].status).toBe("running");
    state = setMethodStatus(state, "region-1", "n-root", "done");
    expect(state.run?.build[0].methods[0].status).toBe("done");
    expect(state.run?.build[0].methods[1].status).toBe("pending");
  });
});
