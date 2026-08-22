import type { RunMemberStatus, RunStatusResponse } from "../api/client";
import type { BatchPlan, RegionBuildSlice } from "../workflow/runner";
import { isRunTerminal } from "../api/runtime_subscription";

/** 工作流运行阶段（决策 2.33，2.38 修订：构建 → 模拟 → 终态；区域校验入口使用校验阶段）。 */
export type RunPhase =
  | "building"
  | "validating"
  | "simulating"
  | "completed"
  | "validated"
  | "build_failed"
  | "cancelled";

export const PHASE_LABELS: Record<RunPhase, string> = {
  building: "构建中",
  validating: "校验中",
  simulating: "模拟中",
  completed: "已完成",
  validated: "校验完成",
  build_failed: "构建失败",
  cancelled: "已取消",
};

/** 批次步骤状态（决策 2.34 轨迹中的批次步骤；2.38 增加已取消；2.40 增加校验中/校验通过）。 */
export type BatchStatus =
  | "pending"
  | "validating"
  | "validated"
  | "submitting"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "skipped";

export const BATCH_STATUS_LABELS: Record<BatchStatus, string> = {
  pending: "等待",
  validating: "校验中",
  validated: "校验通过",
  submitting: "提交中",
  running: "运行中",
  completed: "成功",
  failed: "失败",
  cancelled: "已取消",
  skipped: "跳过",
};

/** 构建阶段方法步骤状态（限速推进时逐步变化）。 */
export type BuildStepStatus = "pending" | "running" | "done" | "skipped";

export const BUILD_STEP_LABELS: Record<BuildStepStatus, string> = {
  pending: "等待",
  running: "应用中",
  done: "已应用",
  skipped: "跳过",
};

/** 构建切片中的单个方法步骤：轨迹数据 + 展示标签 + 步骤状态。 */
export interface BuildMethodStep {
  nodeId: string;
  label: string;
  paths: string[];
  variants: number;
  overridden: boolean;
  status: BuildStepStatus;
}

export interface BuildSliceView {
  regionId: string;
  regionName: string;
  methods: BuildMethodStep[];
  memberCount: number;
}

/** 一个模拟节点对应批次的运行视图。 */
export interface BatchView {
  nodeId: string;
  name: string;
  sourceRegionIds: string[];
  status: BatchStatus;
  runId: string | null;
  /** 后端批次状态（queued/running/…/partial 等）。 */
  state: string | null;
  cancelRequested: boolean;
  members: RunMemberStatus[];
  /** 提交或批次级失败信息。 */
  error: string | null;
}

/** 一次工作流运行：阶段 + 步骤轨迹（构建切片 + 批次步骤，决策 2.38 修订）。 */
export interface WorkflowRunView {
  phase: RunPhase;
  build: BuildSliceView[];
  buildErrors: string[];
  batches: BatchView[];
}

export interface RunState {
  /** 当前/最近一次工作流运行；null = 尚未运行。不持久化。 */
  run: WorkflowRunView | null;
}

export function createEmptyRunState(): RunState {
  return { run: null };
}

export function createRunView(plan: {
  participating: RegionBuildSlice[];
  batches: BatchPlan[];
  buildErrors?: string[];
}): WorkflowRunView {
  return {
    phase: "building",
    build: plan.participating.map((slice) => ({
      regionId: slice.regionId,
      regionName: slice.regionName,
      memberCount: slice.memberCount,
      methods: slice.methods.map((method) => ({
        nodeId: method.nodeId,
        label: method.label,
        paths: method.paths,
        variants: method.variants,
        overridden: method.overridden,
        status: "pending",
      })),
    })),
    buildErrors: plan.buildErrors ?? [],
    batches: plan.batches.map((batch) => ({
      nodeId: batch.nodeId,
      name: batch.name,
      sourceRegionIds: batch.sourceRegionIds,
      status: "pending",
      runId: null,
      state: null,
      cancelRequested: false,
      members: batch.members.map((member) => emptyMemberStatus(member.item_id)),
      error: null,
    })),
  };
}

export function setRunPhase(state: RunState, phase: RunPhase): RunState {
  return updateRun(state, (run) => ({ ...run, phase }));
}

export function setMethodStatus(
  state: RunState,
  regionId: string,
  nodeId: string,
  status: BuildStepStatus,
): RunState {
  return updateRun(state, (run) => ({
    ...run,
    build: run.build.map((slice) =>
      slice.regionId !== regionId
        ? slice
        : {
            ...slice,
            methods: slice.methods.map((method) =>
              method.nodeId === nodeId ? { ...method, status } : method,
            ),
          },
    ),
  }));
}

export function updateBatch(
  state: RunState,
  nodeId: string,
  update: (batch: BatchView) => BatchView,
): RunState {
  return updateRun(state, (run) => ({
    ...run,
    batches: run.batches.map((batch) => (batch.nodeId === nodeId ? update(batch) : batch)),
  }));
}

export function applyBatchView(state: RunState, nodeId: string, view: RunStatusResponse): RunState {
  return updateBatch(state, nodeId, (batch) => ({
    ...batch,
    runId: view.run_id,
    state: view.state,
    cancelRequested: view.cancel_requested,
    members: view.members.map((member) => ({ ...member })),
  }));
}

export function setBatchStatus(
  state: RunState,
  nodeId: string,
  status: BatchStatus,
  error: string | null = null,
): RunState {
  return updateBatch(state, nodeId, (batch) => ({ ...batch, status, error }));
}

/** 后端批次终态映射到批次步骤状态。 */
export function batchStatusFromRunState(runState: string | null): BatchStatus {
  switch (runState) {
    case "completed":
      return "completed";
    case "failed":
      return "failed";
    case "cancelled":
      // 用户取消的批次标记已取消；整次取消中被编排跳过的批次由循环直接标 skipped（决策 2.38）。
      return "cancelled";
    case "partial":
      // 部分失败是正常结果（UI API 契约）：步骤层面记为成功，成员明细里看失败。
      return "completed";
    default:
      return "running";
  }
}

export function updateRun(
  state: RunState,
  update: (run: WorkflowRunView) => WorkflowRunView,
): RunState {
  return state.run === null ? state : { ...state, run: update(state.run) };
}

export function emptyMemberStatus(itemId: string): RunMemberStatus {
  return {
    item_id: itemId,
    state: "queued",
    session_id: null,
    error_code: null,
    error_message: null,
    created_at: "",
  };
}

export { isRunTerminal };
