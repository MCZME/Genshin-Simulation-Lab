import { useEffect, useMemo, useRef, useState } from "react";
import {
  cancelRun,
  closeAnalysisContext,
  createWorkflow,
  deleteWorkflow,
  getAnalysisSchema,
  getRun,
  getWorkflow,
  getWorkspace,
  listWorkflows,
  saveWorkflow,
  searchAssets,
  selectAnalysisStage,
  submitRun,
  validateInputs,
} from "../api/client";
import type { ValidateInputsResponse, WorkflowListItem } from "../api/client";
import { pollRun } from "../api/runtime_subscription";
import { CanvasView } from "../components/canvas/CanvasView";
import {
  AnalysisStageSelectionContext,
  AnalysisResultsContext,
  AnalysisSchemaCatalogContext,
  AnalysisSelectionContext,
  type AnalysisSelectionStore,
  type AnalysisStageSelectionRecord,
  type AnalysisStageSelectionStore,
} from "../components/analysis_context";
import { createAnalysisSchemaCatalog } from "../workflow/templates";
import type { AnalysisSchemaCatalog } from "../workflow/templates";
import { ObjectPanel } from "../components/panels/ObjectPanel";
import { ProblemPanel } from "../components/panels/ProblemPanel";
import { RegionSummaryBar } from "../components/panels/RegionSummaryBar";
import { ResultsPanel } from "../components/panels/ResultsPanel";
import { RunStateContext } from "../components/run_state_context";
import { TopBar } from "../components/shell/TopBar";
import {
  addEdge,
  addNode,
  addRegion,
  canRedo,
  canUndo,
  createEmptyEditorState,
  deleteEdge,
  deleteSelection,
  deleteNode,
  deleteRegion,
  moveRegionWithChildren,
  moveNodeWithRegion,
  moveEdgeIncomingOrder,
  nudgeSelection,
  redo,
  renameRegion,
  renameWorkflow,
  resizeNode,
  resizeRegion,
  setNodeParams,
  setSelection,
  undo,
} from "../state/editor_state";
import type { EditorSelection, EditorState } from "../state/editor_state";
import { markSaved } from "../state/editor_state";
import {
  createAppState,
  readLastWorkflowId,
  rememberLastWorkflowId,
  withCurrentWorkflow,
  withWorkspace,
} from "../state/app_state";
import {
  backfillPayloadEventTypes,
  definitionToEditorState,
  editorStateToDefinition,
  migrateWorkflowDefinition,
} from "../state/converters";
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
import {
  applyViewSelectionSingles,
  directSelectionSingleIds,
  executeAnalysisSelectionBranch,
  planFetchNodes,
  populateAnalysisTerminalResults,
  runAnalysisRegionStages,
} from "../workflow/analysis_runner";
import type { AnalysisNodeResult } from "../workflow/analysis_runner";
import { compileConfigurationRegion } from "../workflow/compiler";
import {
  analysisInputStatus,
  batchInputFingerprint,
  hasRunnableBatch,
  paceBuildSteps,
  planAnalysisInputRun,
  planRegionRun,
  planWorkflowRun,
  scopedDiagnostics,
  validationErrorMessage,
} from "../workflow/runner";
import type { BatchPlan, RunPlan } from "../workflow/runner";
import { regionAnalysisSnapshot } from "../workflow/analysis_snapshot";
import type { AnalysisRunPhase } from "../components/canvas/RegionNode";
import {
  assetMissingDiagnostics,
  collectAssetReferences,
  preflightAssetReferences,
} from "../workflow/asset_preflight";
import type { CompileResult, Diagnostic, WorkflowDefinition } from "../workflow/types";
import { validateWorkflow, validateWorkflowNodes } from "../workflow/validator";
import { getNodeKindSpec } from "../workflow/registry";
import { createAppSettings, loadAppSettingsFromApi, saveAppSettingsToApi } from "../state/settings";
import type { AppSettings } from "../state/settings";
import { SettingsModal } from "../components/shell/SettingsModal";

type Tool = "objects" | "problems" | "results" | null;

/** 构建阶段计划错误 → 问题面板诊断（决策 2.40 修订）。 */
function planErrorDiagnostic(message: string, plan: RunPlan): Diagnostic {
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

export function App() {
  const [appState, setAppState] = useState(() => createAppState());
  const [editorState, setEditorState] = useState<EditorState | null>(null);
  const [workflowList, setWorkflowList] = useState<WorkflowListItem[]>([]);
  const [runState, setRunState] = useState<RunState>(() => createEmptyRunState());
  const [schemaCatalog, setSchemaCatalog] = useState<AnalysisSchemaCatalog | null>(null);
  const [analysisSelections, setAnalysisSelections] = useState<Map<string, unknown>>(
    new Map(),
  );
  const analysisSelectionStore = useMemo<AnalysisSelectionStore>(
    () => ({
      selections: analysisSelections,
      select: (nodeId, item) => {
        setAnalysisSelections((current) => {
          const next = new Map(current);
          if (item === null || item === undefined) {
            next.delete(nodeId);
          } else {
            next.set(nodeId, item);
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
        const definition = editorState?.definition;
        const viewNode = definition?.nodes.find((item) => item.id === nodeId);
        if (definition === undefined || viewNode === undefined) {
          return;
        }
        if (record === null) {
          setAnalysisResults((current) => {
            const next = new Map(current);
            for (const targetId of directSelectionSingleIds(
              definition,
              viewNode.region_id ?? "",
              nodeId,
            )) {
              next.set(targetId, { status: "idle" });
            }
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
          const selectionStage = await selectAnalysisStage(contextId, viewStageId, {
            kind: "group",
            columns: record.groupColumns,
            values: record.groupValues,
          });
          if (seq !== analysisSelectionBranchSeqRef.current) {
            return;
          }
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
            applyViewSelectionSingles(
              definition,
              regionId,
              nodeId,
              selectionStage,
              next,
            );
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
      editorState,
    ],
  );
  /** 每个分析区域最近一次阶段运行保留的后端上下文（供点击选择派生阶段）。 */
  const analysisStageContextIdsRef = useRef<Map<string, string>>(new Map());
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
  /** 分析区域运行阶段（2026-08-26 定案：获取输入 → 查询 → 视图加载）。 */
  const [analysisRunPhase, setAnalysisRunPhase] = useState<AnalysisRunPhase | null>(null);
  /** 分析区域自动重算快照：只对影响查询/展示的定义变化触发。 */
  const analysisSnapshots = useMemo(() => {
    const map = new Map<string, string>();
    if (editorState === null) {
      return map;
    }
    for (const region of editorState.definition.regions) {
      if (region.kind === "analysis") {
        map.set(region.id, regionAnalysisSnapshot(editorState.definition, region.id));
      }
    }
    return map;
  }, [editorState]);
  /** 最近一次自动重算/显式刷新对应的区域快照；相同则跳过请求。 */
  const lastAutoAnalysisSnapshotsRef = useRef<Map<string, string>>(new Map());
  /** 自动重算竞态序号：过期响应丢弃。 */
  const analysisAutoSeqRef = useRef(0);
  /** 最新工作流定义（自动重算 effect 经 ref 读取，避免依赖函数身份）。 */
  const latestDefinitionRef = useRef<WorkflowDefinition | null>(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  /** 资产预检（决策 2.40 节点校验）：加载/切换工作流时核对的失效资产 key。 */
  const [missingAssetKeys, setMissingAssetKeys] = useState<string[]>([]);
  /** 最近一次运行/校验的区域校验失败诊断：进问题面板而非顶部横幅（决策 2.40 修订）。 */
  const [validationDiagnostics, setValidationDiagnostics] = useState<Diagnostic[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<Tool>("objects");
  /** 结果面板定位请求（决策 2.37）：非空时面板打开并选中该 session，随后清空。 */
  const [resultFocus, setResultFocus] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<AppSettings>(() => createAppSettings());
  const [dragKind, setDragKind] = useState<string | null>(null);
  const [selectionEpoch, setSelectionEpoch] = useState(0);
  const [renameRegionRequestId, setRenameRegionRequestId] = useState<string | null>(null);
  const [viewportCommand, setViewportCommand] = useState<
    "zoom-in" | "zoom-out" | "fit" | { type: "locate"; nodeId: string } | null
  >(null);
  const initializedRef = useRef(false);
  /** 运行编排内部信号：取消整次工作流运行（当前批取消 + 剩余批次跳过）。 */
  const cancelRequestedRef = useRef(false);
  /** 当前在跑批次：模拟节点 id 与后端 run_id，供「取消整批」定位。 */
  const currentBatchRef = useRef<{ nodeId: string; runId: string | null } | null>(null);
  /** 资产预检请求序号：丢弃加载/切换竞态中的过期结果。 */
  const preflightSeqRef = useRef(0);

  /** 运行持有全局编辑锁（决策 2.33）。 */
  const busy = running;

  /** 节点校验的资产预检（决策 2.40）：加载/切换工作流时核对一次，竞态以序号丢弃。 */
  async function runAssetPreflight(definition: WorkflowDefinition): Promise<void> {
    const seq = ++preflightSeqRef.current;
    const references = collectAssetReferences(definition);
    if (references.length === 0) {
      setMissingAssetKeys([]);
      return;
    }
    const missing = await preflightAssetReferences(references, (assetType, sourceId) =>
      searchAssets(assetType, sourceId, 200),
    );
    if (preflightSeqRef.current === seq) {
      setMissingAssetKeys(missing);
    }
  }

  async function initialize() {
    try {
      const workspace = await getWorkspace();
      setAppState((current) => withWorkspace(current, workspace));
      setSettings(await loadAppSettingsFromApi());
      const analysisSchemaCatalog = await loadAnalysisSchema();

      const workflowList = await listWorkflows();
      setWorkflowList(workflowList.items);
      const remembered = readLastWorkflowId();
      const target =
        workflowList.items.find((item) => item.id === remembered) ??
        workflowList.items[0];
      let workflowId: string | null;
      let definition: WorkflowDefinition;
      if (target !== undefined) {
        workflowId = target.id;
        const detail = await getWorkflow(workflowId);
        definition = detail.definition as unknown as WorkflowDefinition;
      } else {
        workflowId = null;
        definition = createEmptyEditorState("未命名工作流").definition;
      }
      const migrated = migrateWorkflowDefinition(definition);
      const backfilled =
        analysisSchemaCatalog === null
          ? migrated
          : backfillPayloadEventTypes(migrated, analysisSchemaCatalog.eventTypes());
      setEditorState(definitionToEditorState(backfilled));
      setAppState((current) =>
        withCurrentWorkflow(current, { id: workflowId, name: definition.meta.name }),
      );
      rememberLastWorkflowId(workflowId);
      void runAssetPreflight(definition);
    } catch (error) {
      setErrorMessage(toMessage(error));
    }
  }

  /** 分析可读 schema：启动时拉取一次，失败时分析区域降级为不可用。 */
  async function loadAnalysisSchema(): Promise<AnalysisSchemaCatalog | null> {
    try {
      const response = await getAnalysisSchema();
      const catalog = createAnalysisSchemaCatalog();
      catalog.load(response);
      setSchemaCatalog(catalog);
      return catalog;
    } catch {
      setSchemaCatalog(null);
      return null;
    }
  }

  useEffect(() => {
    if (initializedRef.current) {
      return;
    }
    initializedRef.current = true;
    void initialize();
    // initialize 只允许在首帧执行一次，重复执行由 initializedRef 显式守护。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const { diagnostics, compiles } = useMemo(() => {
    if (editorState === null) {
      return { diagnostics: [] as Diagnostic[], compiles: [] as CompileResult[] };
    }
    const definition = editorState.definition;
    return {
      // 节点校验（决策 2.40）：编辑期只保留节点自身参数/路径诊断 + 资产预检；
      // 跨节点/区域校验留到区域校验与运行的构建阶段（executeRunPlan 内完整校验）。
      diagnostics: [
        ...validateWorkflowNodes(definition),
        ...assetMissingDiagnostics(definition, missingAssetKeys),
      ],
      compiles: definition.regions
        .filter((region) => region.kind === "configuration")
        .map((region) => compileConfigurationRegion(definition, region.id)),
    };
  }, [editorState, missingAssetKeys]);

  useEffect(() => {
    latestDefinitionRef.current = editorState?.definition ?? null;
  }, [editorState]);

  const canRun = useMemo(() => {
    return (
      editorState !== null &&
      !busy &&
      !diagnostics.some((item) => item.severity === "error") &&
      hasRunnableBatch(editorState.definition)
    );
  }, [editorState, busy, diagnostics]);

  /** 运行进行中：参与执行路径的节点保持亮度，其余置灰（决策 2.34）。 */
  const dimmedNodeIds = useMemo(() => {
    const run = runState.run;
    if (
      editorState === null ||
      run === null ||
      (run.phase !== "building" && run.phase !== "validating" && run.phase !== "simulating")
    ) {
      return [];
    }
    const participants = new Set<string>();
    for (const slice of run.build) {
      for (const method of slice.methods) {
        participants.add(method.nodeId);
      }
    }
    for (const batch of run.batches) {
      participants.add(batch.nodeId);
    }
    return editorState.definition.nodes
      .filter((node) => !participants.has(node.id))
      .map((node) => node.id);
  }, [editorState, runState.run]);

  /** 构建限速推进时，当前应用中的节点（画布高亮）。 */
  const runningMethodNodeIds = useMemo(() => {
    const run = runState.run;
    if (run === null || run.phase !== "building") {
      return [];
    }
    return run.build
      .flatMap((slice) => slice.methods)
      .filter((method) => method.status === "running")
      .map((method) => method.nodeId);
  }, [runState.run]);

  /** 构建/运行诊断（完整校验 + 资产预检），并按区域运行范围过滤（决策 2.40）。 */
  const runScopeDiagnostics = useMemo(
    () =>
      (definition: WorkflowDefinition, scopeRegionIds?: Set<string>): Diagnostic[] => {
        const fullDiagnostics = [
          ...validateWorkflow(definition),
          ...assetMissingDiagnostics(definition, missingAssetKeys),
        ];
        return scopeRegionIds === undefined
          ? fullDiagnostics
          : scopedDiagnostics(definition, fullDiagnostics, scopeRegionIds);
      },
    [missingAssetKeys],
  );

  /** 问题面板诊断：编辑期节点级诊断；最近一次运行/校验失败时显示校验/构建诊断（决策 2.40 修订）。 */
  const problemDiagnostics = useMemo<Diagnostic[]>(() => {
    if (editorState === null) {
      return [];
    }
    return validationDiagnostics.length > 0 ? validationDiagnostics : diagnostics;
  }, [diagnostics, editorState, validationDiagnostics]);

  function updateSettings(next: AppSettings) {
    setSettings(next);
    void saveAppSettingsToApi(next).catch((error) => {
      setErrorMessage(`设置未保存：${toMessage(error)}`);
    });
  }

  function updateEditor(update: (state: EditorState) => EditorState) {
    setEditorState((current) => (current === null ? current : update(current)));
  }

  function handleRename(name: string) {
    updateEditor((state) => renameWorkflow(state, name));
  }

  function handleRenameRegion(regionId: string, name: string) {
    updateEditor((state) => renameRegion(state, regionId, name));
  }

  function handleDragStart(kind: string) {
    setDragKind(kind === "" ? null : kind);
  }

  function handleDropObject(
    kind: string,
    position: { x: number; y: number },
    regionId: string | null,
  ) {
    updateEditor((state) => {
      if (kind === "region") {
        const next = addRegion(state, "configuration", "配置区域", {
          x: position.x,
          y: position.y,
          width: 880,
          height: 440,
        });
        const createdRegionId = next.definition.regions[next.definition.regions.length - 1].id;
        setRenameRegionRequestId(createdRegionId);
        return setSelection(next, { regions: [createdRegionId], nodes: [], edges: [] });
      }
      if (kind === "analysis_region") {
        const next = addRegion(state, "analysis", "分析区域", {
          x: position.x,
          y: position.y,
          width: 880,
          height: 440,
        });
        const createdRegionId = next.definition.regions[next.definition.regions.length - 1].id;
        setRenameRegionRequestId(createdRegionId);
        return setSelection(next, { regions: [createdRegionId], nodes: [], edges: [] });
      }
      const spec = getNodeKindSpec(kind);
      if (spec === null) {
        return state;
      }
      const targetRegionId = spec.region === null ? null : regionId;
      const next = addNode(state, kind, position, targetRegionId);
      const createdNodeId = next.definition.nodes[next.definition.nodes.length - 1].id;
      return setSelection(next, { nodes: [createdNodeId], regions: [], edges: [] });
    });
    setDragKind(null);
  }

  function handleUndo() {
    if (busy) {
      return;
    }
    updateEditor((state) => setSelection(undo(state), { regions: [], nodes: [], edges: [] }));
    setSelectionEpoch((epoch) => epoch + 1);
  }

  function handleRedo() {
    if (busy) {
      return;
    }
    updateEditor((state) => setSelection(redo(state), { regions: [], nodes: [], edges: [] }));
    setSelectionEpoch((epoch) => epoch + 1);
  }

  function handleMoveEdgeOrder(
    targetNodeId: string,
    targetPortId: string,
    edgeId: string,
    direction: "up" | "down",
  ) {
    updateEditor((state) =>
      moveEdgeIncomingOrder(state, targetNodeId, targetPortId, edgeId, direction),
    );
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const editable =
        target !== null &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);
      const mod = event.ctrlKey || event.metaKey;
      const key = event.key;

      if (mod && (key === "s" || key === "S")) {
        event.preventDefault();
        void handleSave();
        return;
      }
      if (mod && key === "Enter") {
        event.preventDefault();
        void handleRun();
        return;
      }
      if (mod && key === "z" && !event.shiftKey) {
        if (editable) {
          return;
        }
        event.preventDefault();
        handleUndo();
        return;
      }
      if (
        (mod && key === "Z") ||
        (mod && key === "y") ||
        (mod && key === "Y")
      ) {
        if (editable) {
          return;
        }
        event.preventDefault();
        handleRedo();
        return;
      }
      if (key === "Delete" || key === "Backspace") {
        if (editable || busy || editorState === null) {
          return;
        }
        event.preventDefault();
        updateEditor((state) => deleteSelection(state));
        return;
      }
      if (key === "Escape") {
        if (activeTool !== null) {
          setActiveTool(null);
          return;
        }
        if (
          editorState !== null &&
          (editorState.selection.regions.length > 0 ||
            editorState.selection.nodes.length > 0 ||
            editorState.selection.edges.length > 0)
        ) {
          updateEditor((state) =>
            setSelection(state, { regions: [], nodes: [], edges: [] }),
          );
          setSelectionEpoch((epoch) => epoch + 1);
        }
        return;
      }
      if (key.startsWith("Arrow")) {
        if (editable || busy || editorState === null) {
          return;
        }
        const step = event.shiftKey ? 10 : 1;
        const dx =
          key === "ArrowLeft" ? -step : key === "ArrowRight" ? step : 0;
        const dy =
          key === "ArrowUp" ? -step : key === "ArrowDown" ? step : 0;
        event.preventDefault();
        updateEditor((state) => nudgeSelection(state, dx, dy));
        return;
      }
      if (mod && (key === "=" || key === "+")) {
        event.preventDefault();
        setViewportCommand("zoom-in");
        return;
      }
      if (mod && key === "-") {
        event.preventDefault();
        setViewportCommand("zoom-out");
        return;
      }
      if (mod && key === "0") {
        event.preventDefault();
        setViewportCommand("fit");
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  function handleConnect(connection: {
    source_node_id: string;
    source_port_id: string;
    target_node_id: string;
    target_port_id: string;
  }) {
    updateEditor((state) => addEdge(state, connection));
  }

  function handleSelect(selection: EditorSelection) {
    updateEditor((state) => {
      if (sameSelection(state.selection, selection)) {
        return state;
      }
      return setSelection(state, selection);
    });
  }

  function handleLocate(diagnostic: Diagnostic) {
    const nodeId = diagnostic.node_id;
    const edgeId = diagnostic.edge_id;
    const regionId = diagnostic.region_id;
    if (nodeId !== null) {
      updateEditor((state) =>
        setSelection(state, { nodes: [nodeId], regions: [], edges: [] }),
      );
    } else if (edgeId !== null) {
      updateEditor((state) =>
        setSelection(state, { nodes: [], regions: [], edges: [edgeId] }),
      );
    } else if (regionId !== null) {
      updateEditor((state) =>
        setSelection(state, { nodes: [], regions: [regionId], edges: [] }),
      );
    }
  }

  /** 定位到指定节点：选中并平移到节点（视图空态的修复入口）。 */
  function handleLocateNode(nodeId: string) {
    updateEditor((state) =>
      setSelection(state, { nodes: [nodeId], regions: [], edges: [] }),
    );
    setViewportCommand({ type: "locate", nodeId });
  }

  async function handleSave() {
    if (editorState === null || busy) {
      return;
    }
    setSaving(true);
    setErrorMessage(null);
    try {
      await persistCurrentWorkflow();
    } catch (error) {
      setErrorMessage(toMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function persistCurrentWorkflow(): Promise<string | null> {
    if (editorState === null || busy) {
      return null;
    }
    const definition = editorStateToDefinition(editorState);
    let workflowId = appState.workflowId;
    if (workflowId === null) {
      const created = await createWorkflow(definition.meta.name);
      workflowId = created.id;
    }
    await saveWorkflow(workflowId, definition);
    setEditorState((current) => (current === null ? current : markSaved(current)));
    setAppState((current) =>
      withCurrentWorkflow(current, {
        id: workflowId,
        name: definition.meta.name,
      }),
    );
    rememberLastWorkflowId(workflowId);
    await refreshWorkflowList();
    return workflowId;
  }

  async function refreshWorkflowList(): Promise<void> {
    const list = await listWorkflows();
    setWorkflowList(list.items);
  }

  async function handleSwitchTo(workflowId: string): Promise<void> {
    const detail = await getWorkflow(workflowId);
    const definition = detail.definition as unknown as WorkflowDefinition;
    await closeAnalysisContexts();
    setEditorState(definitionToEditorState(definition));
    setAppState((current) =>
      withCurrentWorkflow(current, {
        id: workflowId,
        name: definition.meta.name,
      }),
    );
    rememberLastWorkflowId(workflowId);
    setRenameRegionRequestId(null);
    setSelectionEpoch((epoch) => epoch + 1);
    setValidationDiagnostics([]);
    void runAssetPreflight(definition);
  }

  async function handleSwitchWorkflow(workflowId: string): Promise<void> {
    if (busy) {
      return;
    }
    try {
      await handleSwitchTo(workflowId);
    } catch (error) {
      setErrorMessage(toMessage(error));
    }
  }

  async function handleSaveAndSwitch(workflowId: string): Promise<void> {
    if (editorState === null || busy) {
      return;
    }
    setSaving(true);
    setErrorMessage(null);
    try {
      await persistCurrentWorkflow();
      await handleSwitchTo(workflowId);
    } catch (error) {
      setErrorMessage(toMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function handleCreateWorkflow(): Promise<void> {
    if (busy) {
      return;
    }
    await closeAnalysisContexts();
    setEditorState(createEmptyEditorState("未命名工作流"));
    setAppState((current) =>
      withCurrentWorkflow(current, { id: null, name: "未命名工作流" }),
    );
    rememberLastWorkflowId(null);
    setRenameRegionRequestId(null);
    setSelectionEpoch((epoch) => epoch + 1);
    setMissingAssetKeys([]);
    setValidationDiagnostics([]);
  }

  async function handleSaveAndCreate(): Promise<void> {
    if (editorState === null || busy) {
      return;
    }
    setSaving(true);
    setErrorMessage(null);
    try {
      await persistCurrentWorkflow();
      await handleCreateWorkflow();
    } catch (error) {
      setErrorMessage(toMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteWorkflow(workflowId: string): Promise<void> {
    if (busy) {
      return;
    }
    setErrorMessage(null);
    try {
      await deleteWorkflow(workflowId);
      if (appState.workflowId === workflowId) {
        await closeAnalysisContexts();
        setEditorState(createEmptyEditorState("未命名工作流"));
        setAppState((current) =>
          withCurrentWorkflow(current, { id: null, name: "未命名工作流" }),
        );
        rememberLastWorkflowId(null);
        setRenameRegionRequestId(null);
        setSelectionEpoch((epoch) => epoch + 1);
        setMissingAssetKeys([]);
        setValidationDiagnostics([]);
      }
      await refreshWorkflowList();
    } catch (error) {
      setErrorMessage(toMessage(error));
    }
  }

  async function handleRenameWorkflow(workflowId: string, name: string): Promise<void> {
    try {
      const detail = await getWorkflow(workflowId);
      const definition = detail.definition as unknown as WorkflowDefinition;
      await saveWorkflow(workflowId, {
        ...definition,
        meta: { ...definition.meta, name },
      });
      await refreshWorkflowList();
    } catch (error) {
      setErrorMessage(toMessage(error));
    }
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
    const runDiagnostics = runScopeDiagnostics(definition, scopeRegionIds);
    const buildErrors = [
      ...runDiagnostics
        .filter((item) => item.severity === "error")
        .map((item) => item.message),
      ...plan.errors,
    ];
    if (buildErrors.length > 0 || plan.batches.length === 0) {
      const errors =
        buildErrors.length > 0
          ? buildErrors
          : ["没有可运行的批次：配置区域未连接模拟节点"];
      setRunState((current) => {
        const started = {
          ...current,
          run: createRunView({
            participating: plan.participating,
            batches: [],
            buildErrors: errors,
          }),
        };
        return setRunPhase(started, "build_failed");
      });
      // 构建/校验失败（零提交）进问题面板并自动打开；顶部横幅只保留操作类错误（决策 2.40 修订）。
      const failureDiagnostics: Diagnostic[] = [
        ...runDiagnostics.filter((item) => item.severity === "error"),
        ...plan.errors.map((message) => planErrorDiagnostic(message, plan)),
      ];
      if (failureDiagnostics.length === 0) {
        failureDiagnostics.push(
          planErrorDiagnostic("没有可运行的批次：配置区域未连接模拟节点", plan),
        );
      }
      setValidationDiagnostics(failureDiagnostics);
      setActiveTool("problems");
      return;
    }

    setRunning(true);
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

    if (mode === "check") {
      setRunState((current) => setRunPhase(current, "validating"));
      cancelRequestedRef.current = false;
      let cancelled = false;
      for (const batch of plan.batches) {
        if (cancelRequestedRef.current) {
          setRunState((current) => setBatchStatus(current, batch.nodeId, "skipped"));
          cancelled = true;
          continue;
        }
        setRunState((current) => setBatchStatus(current, batch.nodeId, "validating"));
        try {
          const validation = await validateInputs(batch.members);
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
            setActiveTool("problems");
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
            setBatchStatus(current, batch.nodeId, "failed", toMessage(error)),
          );
        }
      }
      setRunState((current) => setRunPhase(current, cancelled ? "cancelled" : "validated"));
      setRunning(false);
      return;
    }

    setRunState((current) => setRunPhase(current, "simulating"));

    cancelRequestedRef.current = false;
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
      try {
        const validation = await validateInputs(batch.members);
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
          setActiveTool("problems");
          setRunState((current) =>
            setBatchStatus(current, batch.nodeId, "failed", validationErrorMessage(validation)),
          );
          continue;
        }
      } catch (error) {
        setRunState((current) =>
          setBatchStatus(current, batch.nodeId, "failed", toMessage(error)),
        );
        continue;
      }
      setRunState((current) => setBatchStatus(current, batch.nodeId, "submitting"));
      currentBatchRef.current = { nodeId: batch.nodeId, runId: null };
      try {
        const submitted = await submitRun(batch.members, {
          name: batch.name,
          concurrency: batch.concurrency ?? undefined,
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
          { intervalMs: 1000, getRun },
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
          setBatchStatus(current, batch.nodeId, "failed", toMessage(error)),
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
        await refreshAnalysis(updatedDefinition);
        syncAnalysisSnapshotRef(updatedDefinition);
        // 运行结束联动（决策 2.37）：自动打开结果面板并定位最新记录；
        // 存在区域校验失败时保留问题面板，不再切到结果面板（决策 2.40 修订）。
        if (!validationFailed) {
          openResultAt(completedSessions[0]?.sessionId ?? null);
        }
      }
    }
    setRunning(false);
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

  /** 分析区域执行：编译查询计划一次调用，视图节点读终端表；可限定单个区域。 */
  async function refreshAnalysis(
    definition: WorkflowDefinition,
    onlyRegionId?: string,
  ): Promise<void> {
    // 新一轮阶段运行开始：作废尚未完成的选择分支，避免旧上下文写回结果。
    analysisSelectionBranchSeqRef.current += 1;
    if (schemaCatalog === null) {
      return;
    }
    const updates = new Map<string, AnalysisNodeResult>();
    for (const region of definition.regions) {
      if (
        region.kind !== "analysis" ||
        (onlyRegionId !== undefined && region.id !== onlyRegionId)
      ) {
        continue;
      }
      const previousContext = analysisStageContextIdsRef.current.get(region.id);
      const run = await runAnalysisRegionStages(definition, region.id);
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
      const populated = populateAnalysisTerminalResults(definition, region.id, updates);
      for (const [nodeId, result] of populated) {
        updates.set(nodeId, result);
      }
    }
    setAnalysisResults((current) => new Map([...current, ...updates]));
  }

  /** 显式刷新/补跑后记录区域快照，避免自动重算重复发同一请求。 */
  function syncAnalysisSnapshotRef(definition: WorkflowDefinition) {
    const snapshots = new Map<string, string>();
    for (const region of definition.regions) {
      if (region.kind === "analysis") {
        snapshots.set(region.id, regionAnalysisSnapshot(definition, region.id));
      }
    }
    lastAutoAnalysisSnapshotsRef.current = snapshots;
  }

  /** 自动重算触发前：保留旧表并标 stale，无旧表标 loading（不闪空）。 */
  function markAnalysisRegionLoading(definition: WorkflowDefinition, regionId: string) {
    setAnalysisResults((current) => {
      const next = new Map(current);
      for (const node of definition.nodes) {
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
  function markAnalysisInputPending(
    definition: WorkflowDefinition,
    regionId: string,
    message: string,
  ) {
    setAnalysisResults((current) => {
      const next = new Map(current);
      for (const view of definition.nodes) {
        if (view.region_id !== regionId || !isAnalysisViewKind(view.kind)) {
          continue;
        }
        next.set(view.id, { status: "error", error: message });
      }
      return next;
    });
  }

  /** 自动重算：快照变化后防抖执行；缺会话/过期不查询只提示。 */
  async function refreshStaleAnalysisRegions(definition: WorkflowDefinition) {
    const latest = new Map(lastAutoAnalysisSnapshotsRef.current);
    for (const region of definition.regions) {
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
      if (planFetchNodes(definition, region.id).length === 0) {
        latest.set(region.id, snapshot);
        continue;
      }
      const input = analysisInputStatus(definition, region.id);
      if (input.needsRun) {
        const first = input.nodes.find((item) => item.status !== "ready");
        const message =
          first?.status === "missing"
            ? "模拟数据未运行，请点击区域「运行分析」补跑"
            : "配置已变更或输入指纹缺失，会话可能过期，请点击区域「运行分析」刷新";
        markAnalysisInputPending(definition, region.id, message);
        latest.set(region.id, snapshot);
        continue;
      }
      const regionDiagnostics = runScopeDiagnostics(definition, new Set([region.id]));
      if (regionDiagnostics.some((item) => item.severity === "error")) {
        continue;
      }
      const seq = ++analysisAutoSeqRef.current;
      markAnalysisRegionLoading(definition, region.id);
      await refreshAnalysis(definition, region.id);
      if (seq !== analysisAutoSeqRef.current) {
        continue;
      }
      latest.set(region.id, snapshot);
      lastAutoAnalysisSnapshotsRef.current = latest;
    }
  }

  useEffect(() => {
    const definition = latestDefinitionRef.current;
    if (definition === null || schemaCatalog === null) {
      return;
    }
    const timer = window.setTimeout(() => {
      void refreshStaleAnalysisRegions(definition);
    }, 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisSnapshots, schemaCatalog]);

  /** 全部运行：整个工作流的运行计划进入共用编排。 */
  async function handleRun() {
    if (editorState === null || busy) {
      return;
    }
    const definition = editorStateToDefinition(editorState);
    await executeRunPlan(definition, planWorkflowRun(definition));
  }

  /** 区域运行（决策 2.40）：区域范围的运行计划进入共用编排，复用动画、校验与取消。 */
  async function handleRunRegion(regionId: string) {
    if (editorState === null || busy) {
      return;
    }
    const definition = editorStateToDefinition(editorState);
    await executeRunPlan(definition, planRegionRun(definition, regionId), new Set([regionId]));
  }

  /** 区域校验（决策 2.40 修订）：区域运行的子集，构建 + 批次校验，不提交模拟。 */
  async function handleValidateRegion(regionId: string) {
    if (editorState === null || busy) {
      return;
    }
    const definition = editorStateToDefinition(editorState);
    await executeRunPlan(
      definition,
      planRegionRun(definition, regionId),
      new Set([regionId]),
      "check",
    );
  }

  /**
   * 分析区域运行入口（2026-08-26 定案）：三阶段——
   * 获取输入（边界连接的模拟节点缺会话时补跑批次并写回 last_sessions）→
   * 数据处理（区域级查询计划一次执行）→ 视图加载（终端表落入视图节点）。
   * 任一补跑批次失败/取消则整次中止，不进入查询。
   */
  async function handleRunAnalysis(regionId: string) {
    if (editorState === null || busy) {
      return;
    }
    const definition = editorStateToDefinition(editorState);
    setValidationDiagnostics([]);
    setErrorMessage(null);
    const runDiagnostics = runScopeDiagnostics(definition, new Set([regionId]));
    const inputPlan = planAnalysisInputRun(definition, regionId);
    const graphErrors = runDiagnostics.filter((item) => item.severity === "error");
    const errors = [...graphErrors.map((item) => item.message), ...inputPlan.errors];
    const hasFetch = planFetchNodes(definition, regionId).length > 0;
    if (errors.length > 0 || !hasFetch) {
      const finalErrors =
        errors.length > 0 ? errors : ["分析区域没有可运行的取数节点（未连接区域边界输入）"];
      setRunState((current) => {
        const started = {
          ...current,
          run: createRunView({ participating: [], batches: [], buildErrors: finalErrors }),
        };
        return setRunPhase(started, "build_failed");
      });
      const failureDiagnostics: Diagnostic[] = [
        ...graphErrors,
        ...inputPlan.errors.map((message) => planErrorDiagnostic(message, inputPlan)),
      ];
      if (errors.length === 0) {
        failureDiagnostics.push(
          planErrorDiagnostic("分析区域没有可运行的取数节点（未连接区域边界输入）", inputPlan),
        );
      }
      setValidationDiagnostics(failureDiagnostics);
      setActiveTool("problems");
      return;
    }
    const completeAnalysis = async (updated: WorkflowDefinition) => {
      setAnalysisRunPhase({ regionId, phase: "query" });
      await refreshAnalysis(updated, regionId);
      syncAnalysisSnapshotRef(updated);
      setAnalysisRunPhase(null);
    };
    if (inputPlan.batches.length > 0) {
      setAnalysisRunPhase({ regionId, phase: "input" });
      await executeRunPlan(
        definition,
        inputPlan,
        new Set([regionId]),
        "run",
        completeAnalysis,
      );
      setAnalysisRunPhase(null);
    } else {
      await completeAnalysis(definition);
    }
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

  /** 打开结果面板并定位记录（决策 2.37）；sessionId 为空时只刷新列表。 */
  function openResultAt(sessionId: string | null): void {
    setActiveTool("results");
    setResultFocus(sessionId);
  }

  const runContextValue = {
    runState,
    onCancelRun: handleCancelRun,
    onCancelBatch: handleCancelBatch,
  };

  return (
    <RunStateContext.Provider value={runContextValue}>
      <AnalysisSelectionContext.Provider value={analysisSelectionStore}>
      <AnalysisResultsContext.Provider value={analysisResults}>
      <AnalysisSchemaCatalogContext.Provider value={schemaCatalog}>
      <AnalysisStageSelectionContext.Provider value={analysisStageSelectionStore}>
        <div className="app-shell">
        <TopBar
          name={editorState?.definition.meta.name ?? appState.workflowName}
          dirty={editorState?.dirty ?? false}
          saving={saving}
          running={busy}
          canRun={canRun}
          canUndo={editorState !== null && canUndo(editorState)}
          canRedo={editorState !== null && canRedo(editorState)}
          workflows={workflowList}
          workflowId={appState.workflowId}
          onRename={handleRename}
          onUndo={handleUndo}
          onRedo={handleRedo}
          onSave={() => void handleSave()}
          onRun={() => void handleRun()}
          onCancelRun={() => void handleCancelRun()}
          onCreate={() => void handleCreateWorkflow()}
          onSaveAndCreate={() => void handleSaveAndCreate()}
          onSwitch={(workflowId) => void handleSwitchWorkflow(workflowId)}
          onSaveAndSwitch={(workflowId) => void handleSaveAndSwitch(workflowId)}
          onDelete={(workflowId) => void handleDeleteWorkflow(workflowId)}
          onRenameWorkflow={(workflowId, name) =>
            void handleRenameWorkflow(workflowId, name)
          }
        />
        {errorMessage !== null && (
          <div className="error-banner">
            <span>{errorMessage}</span>
            <button type="button" className="icon-button" onClick={() => setErrorMessage(null)}>
              ×
            </button>
          </div>
        )}
        <div className="app-body">
          <aside className="tool-rail">
            <button
              type="button"
              className={`rail-button ${activeTool === "objects" ? "active" : ""}`}
              title="画布对象"
              onClick={() => setActiveTool(activeTool === "objects" ? null : "objects")}
            >
              节点
            </button>
            <button
              type="button"
              className={`rail-button ${activeTool === "problems" ? "active" : ""}`}
              title="问题列表"
              onClick={() => setActiveTool(activeTool === "problems" ? null : "problems")}
            >
               问题
              {problemDiagnostics.filter((item) => item.severity === "error").length > 0 && (
                <span className="rail-badge">
                  {problemDiagnostics.filter((item) => item.severity === "error").length}
                </span>
              )}
            </button>
            <button
              type="button"
              className={`rail-button ${activeTool === "results" ? "active" : ""}`}
              title="运行结果"
              onClick={() => setActiveTool(activeTool === "results" ? null : "results")}
            >
              结果
            </button>
            <button
              type="button"
              className="rail-button rail-settings"
              title="设置"
              aria-label="设置"
              onClick={() => setSettingsOpen(true)}
            >
              ⚙
            </button>
          </aside>
          {activeTool === "objects" && (
            <ObjectPanel
              onDragStart={handleDragStart}
              onCollapse={() => setActiveTool(null)}
            />
          )}
          {activeTool === "problems" && editorState !== null && (
            <ProblemPanel diagnostics={problemDiagnostics} onLocate={handleLocate} />
          )}
          {activeTool === "results" && (
            <ResultsPanel
              focusSessionId={resultFocus}
              onFocusHandled={() => setResultFocus(null)}
              onCollapse={() => setActiveTool(null)}
            />
          )}
          <main className="canvas-area">
            {editorState !== null && (
              <CanvasView
                definition={editorState.definition}
                analysisResults={analysisResults}
                selection={editorState.selection}
                diagnostics={diagnostics}
                dragKind={dragKind}
                selectionEpoch={selectionEpoch}
                viewportCommand={viewportCommand}
                dimmedNodeIds={dimmedNodeIds}
                runningMethodNodeIds={runningMethodNodeIds}
                interactionLocked={busy}
                onViewportCommandHandled={() => setViewportCommand(null)}
                onMoveNode={(nodeId, position, regionId) =>
                  updateEditor((state) => moveNodeWithRegion(state, nodeId, position, regionId))
                }
                onResizeNode={(nodeId, size) =>
                  updateEditor((state) => resizeNode(state, nodeId, size))
                }
                onMoveRegion={(regionId, position) =>
                  updateEditor((state) => moveRegionWithChildren(state, regionId, position))
                }
                onResizeRegion={(regionId, rect) =>
                  updateEditor((state) => resizeRegion(state, regionId, rect))
                }
                onRenameRegion={handleRenameRegion}
                renameRegionRequestId={renameRegionRequestId}
                onRenameRegionRequestHandled={() => setRenameRegionRequestId(null)}
                onConnectEdge={handleConnect}
                onSelect={handleSelect}
                onParamsChange={(nodeId, params) =>
                  updateEditor((state) => setNodeParams(state, nodeId, params))
                }
                onDeleteNode={(nodeId) => updateEditor((state) => deleteNode(state, nodeId))}
                onDeleteEdge={(edgeId) => updateEditor((state) => deleteEdge(state, edgeId))}
                onDeleteRegion={(regionId) =>
                  updateEditor((state) => deleteRegion(state, regionId))
                }
                onLocateNode={handleLocateNode}
                onDropObject={handleDropObject}
                onMoveEdgeOrder={handleMoveEdgeOrder}
                onValidateRegion={(regionId) => void handleValidateRegion(regionId)}
                onRunRegion={(regionId) => void handleRunRegion(regionId)}
                onRunAnalysis={(regionId) => void handleRunAnalysis(regionId)}
                analysisRunPhase={analysisRunPhase}
              />
            )}
            <RegionSummaryBar compiles={compiles} />
          </main>
        </div>
        {settingsOpen && (
          <SettingsModal
            settings={settings}
            onChange={updateSettings}
            onClose={() => setSettingsOpen(false)}
          />
        )}
        </div>
      </AnalysisStageSelectionContext.Provider>
      </AnalysisSchemaCatalogContext.Provider>
      </AnalysisResultsContext.Provider>
      </AnalysisSelectionContext.Provider>
    </RunStateContext.Provider>
  );
}

function toMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function sameSelection(left: EditorSelection, right: EditorSelection): boolean {
  return (
    sameStringList(left.regions, right.regions) &&
    sameStringList(left.nodes, right.nodes) &&
    sameStringList(left.edges, right.edges)
  );
}

function sameStringList(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => right[index] === value);
}

function isAnalysisViewKind(kind: string): boolean {
  return kind === "member_table" || kind === "pie" || kind === "bar";
}
