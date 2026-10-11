/**
 * 运行编排（从 App 拆出的状态域）：构建 → 校验/提交/轮询 → 终态，
 * 以及运行锁、取消与批次会话回写。App 只消费返回值并接线入口 handler。
 */
import { useEffect, useRef, useState } from "react";
import { cancelRun, getRun, submitRun, validateInputs } from "../api/client";
import type { ValidateInputsResponse } from "../api/client";
import { pollRun } from "../api/runtime_subscription";
import type { EditorState } from "../state/editor_state";
import { setNodeParams } from "../state/editor_state";
import {
  applyBatchView,
  batchStatusFromRunState,
  createEmptyRunState,
  createRunView,
  setBatchStatus,
  setMethodStatus,
  setRunPhase,
} from "../state/run_state";
import type { RunState } from "../state/run_state";
import type { AppSettings } from "../state/settings";
import type { BatchPlan, RunPlan } from "../workflow/runner";
import {
  batchInputFingerprint,
  paceBuildSteps,
  validationErrorMessage,
  withAutoBatchSeed,
} from "../workflow/runner";
import type { Diagnostic, WorkflowDefinition } from "../workflow/types";
import { isAbortError, toMessage } from "./errors";

/** 构建阶段计划错误 → 问题面板诊断（决策 2.40 修订）。 */
export function planErrorDiagnostic(message: string, plan: RunPlan): Diagnostic {
  return {
    severity: "error",
    code: "BUILD_FAILED",
    message,
    node_id: null,
    edge_id: null,
    region_id: plan.participating[0]?.regionId ?? null,
    path: null,
  };
}

/** 批次区域校验失败的成员级诊断 → 问题面板（决策 2.40 修订）。 */
function validationFailureDiagnostics(
  validation: ValidateInputsResponse,
  batch: BatchPlan,
): Diagnostic[] {
  return validation.members
    .filter((member) => !member.ok)
    .map((member) => {
      const detail = member.details?.[0];
      return {
        severity: "error",
        code: detail?.code ?? "INPUT_INVALID",
        message: detail?.message ?? `${member.item_id} 校验未通过`,
        node_id: batch.nodeId,
        edge_id: null,
        region_id: batch.sourceRegionIds[0] ?? null,
        path: detail?.path ?? null,
      };
    });
}

/** 运行编排完成后的分析联动：刷新结果表并同步自动重算快照。 */
export interface RunAnalysisApi {
  refreshAnalysis: (
    definition: WorkflowDefinition,
    onlyRegionId?: string,
    signal?: AbortSignal,
  ) => Promise<void>;
  syncAnalysisSnapshotRef: (definition: WorkflowDefinition) => void;
}

export interface RunOrchestrationOptions {
  settings: AppSettings;
  /** 构建/运行期诊断（决策 2.40）：完整校验 + 资产预检，按区域范围过滤。 */
  runScopeDiagnostics: (
    definition: WorkflowDefinition,
    scopeRegionIds?: Set<string>,
  ) => Diagnostic[];
  updateEditor: (update: (state: EditorState) => EditorState) => void;
  analysis: RunAnalysisApi;
  /** 操作类错误的顶部横幅（构建/校验失败走问题面板，决策 2.40 修订）。 */
  setErrorMessage: (message: string | null) => void;
  /** 打开问题面板（构建/校验失败自动联动）。 */
  openProblems: () => void;
  /** 运行结束打开结果面板并定位记录（决策 2.37）。 */
  openResultAt: (sessionId: string | null) => void;
}

export function useRunOrchestration(options: RunOrchestrationOptions) {
  const { settings, runScopeDiagnostics, updateEditor, analysis } = options;
  const { setErrorMessage, openProblems, openResultAt } = options;
  const [running, setRunning] = useState(false);
  const [runState, setRunState] = useState<RunState>(() => createEmptyRunState());
  /** 最近一次运行/校验的区域校验失败诊断：进问题面板而非顶部横幅（决策 2.40 修订）。 */
  const [validationDiagnostics, setValidationDiagnostics] = useState<Diagnostic[]>([]);
  /** 运行编排内部信号：取消整次工作流运行（当前批取消 + 剩余批次跳过）。 */
  const cancelRequestedRef = useRef(false);
  /** 当前运行的请求取消源：卸载时中断在途的校验/提交/轮询请求。 */
  const runAbortRef = useRef<AbortController | null>(null);
  /** 当前在跑批次：模拟节点 id 与后端 run_id，供「取消整批」定位。 */
  const currentBatchRef = useRef<{ nodeId: string; runId: string | null } | null>(null);

  useEffect(() => {
    return () => {
      runAbortRef.current?.abort();
    };
  }, []);

  /**
   * 构建失败（零提交）呈现：run 视图进入 build_failed，诊断进问题面板并自动
   * 打开；顶部横幅只保留操作类错误（决策 2.40 修订）。运行与分析入口共用。
   */
  function reportBuildFailure(
    plan: RunPlan,
    buildErrors: string[],
    diagnostics: Diagnostic[],
    fallbackMessage: string,
  ): void {
    setRunState((current) => {
      const started = {
        ...current,
        run: createRunView({
          participating: plan.participating,
          batches: [],
          buildErrors,
        }),
      };
      return setRunPhase(started, "build_failed");
    });
    const failureDiagnostics: Diagnostic[] = [...diagnostics];
    if (failureDiagnostics.length === 0) {
      failureDiagnostics.push(planErrorDiagnostic(fallbackMessage, plan));
    }
    setValidationDiagnostics(failureDiagnostics);
    openProblems();
  }

  /**
   * 共用运行/校验编排（决策 2.40 修订）：全部运行与区域运行走同一条链路——
   * 构建（前端编译与图校验，失败零提交，限速动画）→ 模拟（每批提交前先做
   * 区域校验，再提交并轮询，按画布顺序串行，决策 2.32）→ 终态；
   * 区域校验入口以 check 模式复用同一条链路，在批次校验后终止、不提交。
   */
  async function executeRunPlan(
    definition: WorkflowDefinition,
    plan: RunPlan,
    scopeRegionIds?: Set<string>,
    mode: "run" | "check" = "run",
    onCompleted?: (updatedDefinition: WorkflowDefinition) => Promise<void>,
  ) {
    setValidationDiagnostics([]);
    setErrorMessage(null);
    cancelRequestedRef.current = false;
    const runDiagnostics = runScopeDiagnostics(definition, scopeRegionIds);
    const buildErrors = [
      ...runDiagnostics
        .filter((item) => item.severity === "error")
        .map((item) => item.message),
      ...plan.errors,
    ];
    if (buildErrors.length > 0 || plan.batches.length === 0) {
      reportBuildFailure(
        plan,
        buildErrors.length > 0
          ? buildErrors
          : ["没有可运行的批次：配置区域未连接模拟节点"],
        [
          ...runDiagnostics.filter((item) => item.severity === "error"),
          ...plan.errors.map((message) => planErrorDiagnostic(message, plan)),
        ],
        "没有可运行的批次：配置区域未连接模拟节点",
      );
      return;
    }

    const controller = new AbortController();
    runAbortRef.current = controller;
    setRunning(true);
    try {
      await runBatches(definition, plan, mode, onCompleted, controller.signal);
    } catch (error) {
      // 批次内错误已在 runBatches 逐批处理；这里兜底编排本身的未预期异常，
      // 保证运行锁一定释放（否则 busy 永真，保存/运行/切换全部禁用）。
      setErrorMessage(`运行编排异常：${toMessage(error)}`);
    } finally {
      runAbortRef.current = null;
      setRunning(false);
    }
  }

  /** 构建校验通过后的批次执行段：限速动画 → 取消检查 → 校验/提交/轮询 → 终态。 */
  async function runBatches(
    definition: WorkflowDefinition,
    plan: RunPlan,
    mode: "run" | "check",
    onCompleted: ((updatedDefinition: WorkflowDefinition) => Promise<void>) | undefined,
    signal: AbortSignal,
  ): Promise<void> {
    setRunState((current) => ({
      ...current,
      run: createRunView(plan),
    }));

    // 构建阶段逐节点限速推进（决策 2.34 修订）：每个方法步骤保留最小执行时长，
    // 运行过程按节点顺序真实推进；取消时剩余步骤立即跳过。
    await paceBuildSteps(plan.participating, {
      enabled: settings.runAnimation,
      shouldStop: () => cancelRequestedRef.current,
      onMethodStatus: (regionId, nodeId, status) =>
        setRunState((current) => setMethodStatus(current, regionId, nodeId, status)),
    });

    // 构建期间请求取消：全部批次跳过，不进入校验/提交。
    if (cancelRequestedRef.current) {
      setRunState((current) => {
        const skipped = plan.batches.reduce(
          (state, batch) => setBatchStatus(state, batch.nodeId, "skipped"),
          current,
        );
        return setRunPhase(skipped, "cancelled");
      });
      return;
    }

    if (mode === "check") {
      setRunState((current) => setRunPhase(current, "validating"));
      let cancelled = false;
      for (const batch of plan.batches) {
        if (cancelRequestedRef.current) {
          setRunState((current) => setBatchStatus(current, batch.nodeId, "skipped"));
          cancelled = true;
          continue;
        }
        setRunState((current) => setBatchStatus(current, batch.nodeId, "validating"));
        try {
          const validation = await validateInputs(batch.members, { signal });
          if (cancelRequestedRef.current) {
            setRunState((current) => setBatchStatus(current, batch.nodeId, "skipped"));
            cancelled = true;
            continue;
          }
          if (!validation.ok) {
            setValidationDiagnostics((current) => [
              ...current,
              ...validationFailureDiagnostics(validation, batch),
            ]);
            openProblems();
          }
          setRunState((current) =>
            setBatchStatus(
              current,
              batch.nodeId,
              validation.ok ? "validated" : "failed",
              validation.ok ? null : validationErrorMessage(validation),
            ),
          );
        } catch (error) {
          setRunState((current) =>
            setBatchStatus(
              current,
              batch.nodeId,
              isAbortError(error) ? "cancelled" : "failed",
              toMessage(error),
            ),
          );
        }
      }
      setRunState((current) => setRunPhase(current, cancelled ? "cancelled" : "validated"));
      return;
    }

    setRunState((current) => setRunPhase(current, "simulating"));

    const fingerprintByNode = new Map(
      plan.batches.map((batch) => [batch.nodeId, batchInputFingerprint(batch)]),
    );
    let cancelled = false;
    let validationFailed = false;
    const completedSessions: Array<{
      nodeId: string;
      itemId: string;
      sessionId: string;
    }> = [];

    for (const batch of plan.batches) {
      if (cancelRequestedRef.current) {
        setRunState((current) => setBatchStatus(current, batch.nodeId, "skipped"));
        cancelled = true;
        continue;
      }
      setRunState((current) => setBatchStatus(current, batch.nodeId, "validating"));
      // 区域校验（决策 2.40）：提交前对批次成员做后端统一校验；
      // 失败该批标失败并附成员级诊断，其余批次照跑（对齐 2.32）。
      // 随机种子未设置时提交前自动随机生成（同批共用），校验与提交使用同一份成员。
      const seededMembers = withAutoBatchSeed(batch.members);
      try {
        const validation = await validateInputs(seededMembers, { signal });
        if (cancelRequestedRef.current) {
          setRunState((current) => setBatchStatus(current, batch.nodeId, "skipped"));
          cancelled = true;
          continue;
        }
        if (!validation.ok) {
          validationFailed = true;
          setValidationDiagnostics((current) => [
            ...current,
            ...validationFailureDiagnostics(validation, batch),
          ]);
          openProblems();
          setRunState((current) =>
            setBatchStatus(current, batch.nodeId, "failed", validationErrorMessage(validation)),
          );
          continue;
        }
      } catch (error) {
        setRunState((current) =>
          setBatchStatus(
            current,
            batch.nodeId,
            isAbortError(error) ? "cancelled" : "failed",
            toMessage(error),
          ),
        );
        continue;
      }
      setRunState((current) => setBatchStatus(current, batch.nodeId, "submitting"));
      currentBatchRef.current = { nodeId: batch.nodeId, runId: null };
      try {
        const submitted = await submitRun(seededMembers, {
          name: batch.name,
          concurrency: batch.concurrency ?? undefined,
          signal,
        });
        if (cancelRequestedRef.current) {
          const view = await cancelRun(submitted.run_id);
          setRunState((current) => applyBatchView(current, batch.nodeId, view));
        }
        currentBatchRef.current = { nodeId: batch.nodeId, runId: submitted.run_id };
        setRunState((current) => {
          const applied = applyBatchView(current, batch.nodeId, submitted);
          return setBatchStatus(applied, batch.nodeId, "running");
        });
        const finalView = await pollRun(
          submitted.run_id,
          (view) => setRunState((current) => applyBatchView(current, batch.nodeId, view)),
          {
            intervalMs: 1000,
            signal,
            getRun: (runId) => getRun(runId, { signal }),
          },
        );
        setRunState((current) =>
          setBatchStatus(current, batch.nodeId, batchStatusFromRunState(finalView.state)),
        );
        for (const member of finalView.members) {
          if (member.state === "completed" && member.session_id != null) {
            completedSessions.push({
              nodeId: batch.nodeId,
              itemId: member.item_id,
              sessionId: member.session_id,
            });
          }
        }
      } catch (error) {
        // 某批失败不中断后续批次（决策 2.32）。
        setRunState((current) =>
          setBatchStatus(
            current,
            batch.nodeId,
            isAbortError(error) ? "cancelled" : "failed",
            toMessage(error),
          ),
        );
      } finally {
        currentBatchRef.current = null;
      }
    }

    if (cancelled) {
      setRunState((current) => setRunPhase(current, "cancelled"));
    } else {
      setRunState((current) => setRunPhase(current, "completed"));
      const updatedDefinition = persistSimulationSessions(
        definition,
        completedSessions,
        fingerprintByNode,
      );
      if (onCompleted !== undefined) {
        await onCompleted(updatedDefinition);
      } else {
        await analysis.refreshAnalysis(updatedDefinition, undefined, signal);
        analysis.syncAnalysisSnapshotRef(updatedDefinition);
        // 运行结束联动（决策 2.37）：自动打开结果面板并定位最新记录；
        // 存在区域校验失败时保留问题面板，不再切到结果面板（决策 2.40 修订）。
        if (!validationFailed) {
          openResultAt(completedSessions[0]?.sessionId ?? null);
        }
      }
    }
  }

  /** 模拟节点保存最近一次批次会话 ID（决策：随工作流持久化）。 */
  function persistSimulationSessions(
    definition: WorkflowDefinition,
    completedSessions: Array<{ nodeId: string; sessionId: string }>,
    fingerprintByNode?: Map<string, string>,
  ): WorkflowDefinition {
    const byNode = new Map<string, string[]>();
    for (const item of completedSessions) {
      const list = byNode.get(item.nodeId) ?? [];
      list.push(item.sessionId);
      byNode.set(item.nodeId, list);
    }
    if (byNode.size === 0) {
      return definition;
    }
    const updated: WorkflowDefinition = {
      ...definition,
      nodes: definition.nodes.map((node) =>
        node.kind === "simulation" && byNode.has(node.id)
          ? {
              ...node,
              params: {
                ...node.params,
                last_sessions: byNode.get(node.id),
                ...(fingerprintByNode?.get(node.id) !== undefined
                  ? { last_input_fingerprint: fingerprintByNode.get(node.id) }
                  : {}),
              },
            }
          : node,
      ),
    };
    for (const [nodeId, sessions] of byNode) {
      const target = definition.nodes.find((node) => node.id === nodeId);
      if (target !== undefined) {
        updateEditor((state) =>
          setNodeParams(state, nodeId, {
            ...target.params,
            last_sessions: sessions,
            ...(fingerprintByNode?.get(nodeId) !== undefined
              ? { last_input_fingerprint: fingerprintByNode.get(nodeId) }
              : {}),
          }),
        );
      }
    }
    return updated;
  }

  /** 取消整次工作流运行：取消当前批次，剩余批次由编排循环跳过（决策 2.32）；顶栏双击触发。 */
  async function handleCancelRun() {
    if (!running) {
      return;
    }
    cancelRequestedRef.current = true;
    const current = currentBatchRef.current;
    if (current?.runId == null) {
      return;
    }
    try {
      const view = await cancelRun(current.runId);
      setRunState((state) => applyBatchView(state, current.nodeId, view));
    } catch (error) {
      setErrorMessage(toMessage(error));
    }
  }

  /** 取消本批（决策 2.38）：仅取消当前批次，该批终态后后续批次照常继续。 */
  async function handleCancelBatch(nodeId: string) {
    const current = currentBatchRef.current;
    if (current === null || current.nodeId !== nodeId || current.runId === null) {
      return;
    }
    try {
      const view = await cancelRun(current.runId);
      setRunState((state) => applyBatchView(state, nodeId, view));
    } catch (error) {
      setErrorMessage(toMessage(error));
    }
  }

  return {
    running,
    runState,
    validationDiagnostics,
    setValidationDiagnostics,
    executeRunPlan,
    reportBuildFailure,
    handleCancelRun,
    handleCancelBatch,
  };
}
