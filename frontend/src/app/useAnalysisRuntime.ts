/**
 * 分析区域运行时（从 App 拆出的状态域）：结果表、选择派生、阶段上下文、
 * 显式刷新与自动重算。App 只消费返回值并接线 UI。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { closeAnalysisContext, selectAnalysisStage } from "../api/client";
import type { AnalysisRunPhase } from "../components/canvas/RegionNode";
import type { AnalysisSelectionStore, AnalysisStageSelectionRecord, AnalysisStageSelectionStore } from "../components/analysis_context";
import {
  executeAnalysisSelectionBranch,
  planFetchNodes,
  populateAnalysisTerminalResults,
  runAnalysisRegionStages,
  selectionBranchNodeIds,
} from "../workflow/analysis_runner";
import type { AnalysisNodeResult } from "../workflow/analysis_runner";
import { regionAnalysisSnapshot } from "../workflow/analysis_snapshot";
import { analysisInputStatus } from "../workflow/runner";
import type { AnalysisSchemaCatalog, AnalysisTableResult } from "../workflow/templates";
import type { Diagnostic, WorkflowDefinition } from "../workflow/types";
import { toMessage } from "./errors";

export interface AnalysisRuntimeOptions {
  definition: WorkflowDefinition | null;
  schemaCatalog: AnalysisSchemaCatalog | null;
  /** 构建/运行期诊断（决策 2.40）：自动重算前做区域级错误检查。 */
  runScopeDiagnostics: (
    definition: WorkflowDefinition,
    scopeRegionIds?: Set<string>,
  ) => Diagnostic[];
}

function isAnalysisViewKind(kind: string): boolean {
  return (
    kind === "member_table" || kind === "pie" || kind === "bar" || kind === "interval"
  );
}

export function useAnalysisRuntime(options: AnalysisRuntimeOptions) {
  const { definition, schemaCatalog, runScopeDiagnostics } = options;

  const [analysisSelections, setAnalysisSelections] = useState<Map<string, AnalysisTableResult>>(
    new Map(),
  );
  const analysisSelectionStore = useMemo<AnalysisSelectionStore>(
    () => ({
      selections: analysisSelections,
      select: (nodeId, table) => {
        setAnalysisSelections((current) => {
          const next = new Map(current);
          if (table === null) {
            next.delete(nodeId);
          } else {
            next.set(nodeId, table);
          }
          return next;
        });
      },
    }),
    [analysisSelections],
  );
  const [analysisStageSelections, setAnalysisStageSelections] = useState<
    Map<string, AnalysisStageSelectionRecord | null>
  >(new Map());
  const [analysisStageContextIds, setAnalysisStageContextIds] = useState<
    ReadonlyMap<string, string>
  >(new Map());
  const [analysisResults, setAnalysisResults] = useState<Map<string, AnalysisNodeResult>>(
    () => new Map(),
  );
  const analysisSelectionBranchSeqRef = useRef(0);
  const analysisStageSelectionStore = useMemo<AnalysisStageSelectionStore>(
    () => ({
      records: analysisStageSelections,
      contextIdFor: (regionId: string) =>
        analysisStageContextIds.get(regionId) ?? null,
      select: (nodeId, record) => {
        setAnalysisStageSelections((current) => {
          const next = new Map(current);
          if (record === null) {
            next.delete(nodeId);
          } else {
            next.set(nodeId, record);
          }
          return next;
        });
        const viewNode = definition?.nodes.find((item) => item.id === nodeId);
        if (definition === undefined || definition === null || viewNode === undefined) {
          return;
        }
        if (record === null) {
          setAnalysisResults((current) => {
            const next = new Map(current);
            for (const targetId of selectionBranchNodeIds(
              definition,
              viewNode.region_id ?? "",
              nodeId,
            )) {
              next.set(targetId, { status: "idle" });
            }
            return next;
          });
          setAnalysisSelections((current) => {
            const next = new Map(current);
            next.delete(nodeId);
            return next;
          });
          return;
        }
        const regionId = viewNode.region_id;
        if (regionId === null) {
          return;
        }
        const contextId = analysisStageContextIds.get(regionId);
        const viewStageId = analysisResults.get(nodeId)?.stage_id;
        if (contextId === undefined || viewStageId === undefined) {
          return;
        }
        const seq = ++analysisSelectionBranchSeqRef.current;
        void (async () => {
          const selectionStage =
            record.kind === "row"
              ? await selectAnalysisStage(contextId, viewStageId, {
                  kind: "row",
                  row_index: record.row_index,
                })
              : await selectAnalysisStage(contextId, viewStageId, {
                  kind: "group",
                  columns: record.groupColumns,
                  values: record.groupValues,
                });
          if (seq !== analysisSelectionBranchSeqRef.current) {
            return;
          }
          const selectionTable: AnalysisTableResult = {
            columns: selectionStage.columns.map((column) => ({
              name: column.name,
              type: column.type,
            })),
            rows: selectionStage.rows,
            truncated: selectionStage.truncated,
          };
          setAnalysisSelections((current) => {
            const next = new Map(current);
            next.set(nodeId, selectionTable);
            return next;
          });
          const existingStages = new Map<string, string>();
          for (const item of definition.nodes) {
            const stageId = analysisResults.get(item.id)?.stage_id;
            if (stageId !== undefined) {
              existingStages.set(item.id, stageId);
            }
          }
          const branchResults = await executeAnalysisSelectionBranch(
            definition,
            regionId,
            nodeId,
            contextId,
            selectionStage.stage_id,
            existingStages,
          );
          if (
            seq !== analysisSelectionBranchSeqRef.current ||
            analysisStageContextIdsRef.current.get(regionId) !== contextId
          ) {
            return;
          }
          setAnalysisResults((current) => {
            const next = new Map(current);
            for (const [branchNodeId, result] of branchResults) {
              next.set(branchNodeId, result);
            }
            return populateAnalysisTerminalResults(definition, regionId, next);
          });
        })().catch(() => {
          // 选择分支失败时保留旧结果；自动重算会在下次定义变化后刷新。
        });
      },
    }),
    [
      analysisStageSelections,
      analysisStageContextIds,
      analysisResults,
      definition,
    ],
  );
  /** 每个分析区域最近一次阶段运行保留的后端上下文（供点击选择派生阶段）。 */
  const analysisStageContextIdsRef = useRef<Map<string, string>>(new Map());
  /** 分析区域运行阶段（2026-08-26 定案：获取输入 → 查询 → 视图加载）。 */
  const [analysisRunPhase, setAnalysisRunPhase] = useState<AnalysisRunPhase | null>(null);
  /** 分析区域自动重算快照：只对影响查询/展示的定义变化触发。 */
  const analysisSnapshots = useMemo(() => {
    const map = new Map<string, string>();
    if (definition === null) {
      return map;
    }
    for (const region of definition.regions) {
      if (region.kind === "analysis") {
        map.set(region.id, regionAnalysisSnapshot(definition, region.id));
      }
    }
    return map;
  }, [definition]);
  /** 最近一次自动重算/显式刷新对应的区域快照；相同则跳过请求。 */
  const lastAutoAnalysisSnapshotsRef = useRef<Map<string, string>>(new Map());
  /** 自动重算竞态序号：过期响应丢弃。 */
  const analysisAutoSeqRef = useRef(0);
  /** 最新工作流定义（自动重算 effect 经 ref 读取，避免依赖函数身份）。 */
  const latestDefinitionRef = useRef<WorkflowDefinition | null>(null);

  useEffect(() => {
    latestDefinitionRef.current = definition;
  }, [definition]);

  /** 关闭全部分析运行时上下文并清空阶段运行态（工作流切换/新建/删除时调用）。 */
  async function closeAnalysisContexts(): Promise<void> {
    analysisSelectionBranchSeqRef.current += 1;
    const contexts = [...analysisStageContextIdsRef.current.values()];
    analysisStageContextIdsRef.current = new Map();
    setAnalysisStageContextIds(new Map());
    setAnalysisResults(new Map());
    setAnalysisStageSelections(new Map());
    setAnalysisSelections(new Map());
    await Promise.all(
      contexts.map((contextId) =>
        closeAnalysisContext(contextId).catch(() => {
          // 旧上下文回收失败不阻断工作流切换。
        }),
      ),
    );
  }

  /** 分析区域执行：编译查询计划一次调用，视图节点读终端表；可限定单个区域。 */
  async function refreshAnalysis(
    target: WorkflowDefinition,
    onlyRegionId?: string,
    signal?: AbortSignal,
  ): Promise<void> {
    // 新一轮阶段运行开始：作废尚未完成的选择分支，避免旧上下文写回结果。
    analysisSelectionBranchSeqRef.current += 1;
    if (schemaCatalog === null) {
      return;
    }
    const updates = new Map<string, AnalysisNodeResult>();
    for (const region of target.regions) {
      if (
        region.kind !== "analysis" ||
        (onlyRegionId !== undefined && region.id !== onlyRegionId)
      ) {
        continue;
      }
      try {
        const previousContext = analysisStageContextIdsRef.current.get(region.id);
        const run = await runAnalysisRegionStages(
          target,
          region.id,
          true,
          undefined,
          undefined,
          undefined,
          undefined,
          { signal },
        );
        const results = run.results;
        if (previousContext !== undefined && previousContext !== run.context_id) {
          void closeAnalysisContext(previousContext).catch(() => {
            // 旧上下文回收失败不阻断新结果。
          });
        }
        const contextIds = new Map(analysisStageContextIdsRef.current);
        if (run.context_id === null) {
          contextIds.delete(region.id);
        } else {
          contextIds.set(region.id, run.context_id);
        }
        analysisStageContextIdsRef.current = contextIds;
        setAnalysisStageContextIds(contextIds);
        for (const [nodeId, result] of results) {
          updates.set(nodeId, result);
        }
        const populated = populateAnalysisTerminalResults(target, region.id, updates);
        for (const [nodeId, result] of populated) {
          updates.set(nodeId, result);
        }
      } catch (error) {
        // 单区域查询失败不中断其他区域；视图落 error 态并保留错误信息。
        markAnalysisRegionError(target, region.id, toMessage(error));
      }
    }
    setAnalysisResults((current) => new Map([...current, ...updates]));
  }

  /** 显式刷新/补跑后记录区域快照，避免自动重算重复发同一请求。 */
  function syncAnalysisSnapshotRef(target: WorkflowDefinition) {
    const snapshots = new Map<string, string>();
    for (const region of target.regions) {
      if (region.kind === "analysis") {
        snapshots.set(region.id, regionAnalysisSnapshot(target, region.id));
      }
    }
    lastAutoAnalysisSnapshotsRef.current = snapshots;
  }

  /** 自动重算触发前：保留旧表并标 stale，无旧表标 loading（不闪空）。 */
  function markAnalysisRegionLoading(target: WorkflowDefinition, regionId: string) {
    setAnalysisResults((current) => {
      const next = new Map(current);
      for (const node of target.nodes) {
        if (node.region_id !== regionId) {
          continue;
        }
        const existing = current.get(node.id);
        next.set(
          node.id,
          existing?.table !== undefined
            ? { status: "stale", table: existing.table }
            : { status: "loading" },
        );
      }
      return next;
    });
  }

  /** 输入未就绪/过期：视图给出可操作提示（缺会话与过期区分文案）。 */
  function markAnalysisInputPending(target: WorkflowDefinition, regionId: string, message: string) {
    setAnalysisResults((current) => {
      const next = new Map(current);
      for (const view of target.nodes) {
        if (view.region_id !== regionId || !isAnalysisViewKind(view.kind)) {
          continue;
        }
        next.set(view.id, { status: "error", error: message });
      }
      return next;
    });
  }

  /** 查询失败：区域视图落 error 态并显示错误信息（区别于 loading/stale）。 */
  function markAnalysisRegionError(target: WorkflowDefinition, regionId: string, message: string) {
    setAnalysisResults((current) => {
      const next = new Map(current);
      for (const view of target.nodes) {
        if (view.region_id !== regionId || !isAnalysisViewKind(view.kind)) {
          continue;
        }
        next.set(view.id, { status: "error", error: message });
      }
      return next;
    });
  }

  /** 自动重算：快照变化后防抖执行；缺会话/过期不查询只提示。 */
  async function refreshStaleAnalysisRegions() {
    const target = latestDefinitionRef.current;
    if (target === null) {
      return;
    }
    const latest = new Map(lastAutoAnalysisSnapshotsRef.current);
    for (const region of target.regions) {
      if (region.kind !== "analysis") {
        continue;
      }
      const snapshot = analysisSnapshots.get(region.id);
      if (snapshot === undefined || latest.get(region.id) === snapshot) {
        continue;
      }
      if (analysisRunPhase?.regionId === region.id) {
        continue;
      }
      if (planFetchNodes(target, region.id).length === 0) {
        latest.set(region.id, snapshot);
        continue;
      }
      const input = analysisInputStatus(target, region.id);
      if (input.needsRun) {
        const first = input.nodes.find((item) => item.status !== "ready");
        const message =
          first?.status === "missing"
            ? "模拟数据未运行，请点击区域「运行分析」补跑"
            : "配置已变更或输入指纹缺失，会话可能过期，请点击区域「运行分析」刷新";
        markAnalysisInputPending(target, region.id, message);
        latest.set(region.id, snapshot);
        continue;
      }
      const regionDiagnostics = runScopeDiagnostics(target, new Set([region.id]));
      if (regionDiagnostics.some((item) => item.severity === "error")) {
        continue;
      }
      const seq = ++analysisAutoSeqRef.current;
      markAnalysisRegionLoading(target, region.id);
      await refreshAnalysis(target, region.id);
      if (seq !== analysisAutoSeqRef.current) {
        continue;
      }
      latest.set(region.id, snapshot);
      lastAutoAnalysisSnapshotsRef.current = latest;
    }
  }

  useEffect(() => {
    if (definition === null || schemaCatalog === null) {
      return;
    }
    const timer = window.setTimeout(() => {
      void refreshStaleAnalysisRegions();
    }, 300);
    return () => window.clearTimeout(timer);
    // 快照变化即触发一次；definition 经 ref 读取，避免依赖函数身份。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisSnapshots, schemaCatalog]);

  useEffect(() => {
    return () => {
      // 应用退出时尽力回收后端阶段上下文；竞态序号同时作废未完成的选择分支。
      analysisSelectionBranchSeqRef.current += 1;
      for (const contextId of analysisStageContextIdsRef.current.values()) {
        void closeAnalysisContext(contextId).catch(() => {
          // 卸载阶段回收失败不影响页面退出。
        });
      }
    };
  }, []);

  return {
    analysisResults,
    analysisSelectionStore,
    analysisStageSelectionStore,
    analysisRunPhase,
    setAnalysisRunPhase,
    closeAnalysisContexts,
    refreshAnalysis,
    syncAnalysisSnapshotRef,
  };
}
