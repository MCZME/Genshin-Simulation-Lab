import { useEffect, useMemo, useRef, useState } from "react";
import {
  createWorkflow,
  deleteWorkflow,
  getAnalysisSchema,
  getWorkflow,
  getWorkspace,
  listWorkflows,
  saveWorkflow,
  searchAssets,
} from "../api/client";
import type { WorkflowListItem } from "../api/client";
import { CanvasView } from "../components/canvas/CanvasView";
import {
  AnalysisStageSelectionContext,
  AnalysisResultsContext,
  AnalysisSchemaCatalogContext,
  AnalysisSelectionContext,
} from "../components/analysis_context";
import { createAnalysisSchemaCatalog } from "../workflow/templates";
import type { AnalysisSchemaCatalog } from "../workflow/templates";
import { ObjectPanel } from "../components/panels/ObjectPanel";
import { ProblemPanel } from "../components/panels/ProblemPanel";
import { RegionSummaryBar } from "../components/panels/RegionSummaryBar";
import { ResultsPanel } from "../components/panels/ResultsPanel";
import { RunStateContext } from "../components/run_state_context";
import { TopBar } from "../components/shell/TopBar";
import { Close, Settings } from "../components/common/icons";
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
  planFetchNodes,
} from "../workflow/analysis_runner";
import { compileConfigurationRegion } from "../workflow/compiler";
import {
  hasRunnableBatch,
  planAnalysisInputRun,
  planRegionRun,
  planWorkflowRun,
  scopedDiagnostics,
} from "../workflow/runner";
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
import { toMessage } from "./errors";
import { useAnalysisRuntime } from "./useAnalysisRuntime";
import { planErrorDiagnostic, useRunOrchestration } from "./useRunOrchestration";

type Tool = "objects" | "problems" | "results" | null;

export function App() {
  const [appState, setAppState] = useState(() => createAppState());
  const [editorState, setEditorState] = useState<EditorState | null>(null);
  const [workflowList, setWorkflowList] = useState<WorkflowListItem[]>([]);
  const [schemaCatalog, setSchemaCatalog] = useState<AnalysisSchemaCatalog | null>(null);
  const [saving, setSaving] = useState(false);
  /** 资产预检（决策 2.40 节点校验）：加载/切换工作流时核对的失效资产 key。 */
  const [missingAssetKeys, setMissingAssetKeys] = useState<string[]>([]);
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
  /** 资产预检请求序号：丢弃加载/切换竞态中的过期结果。 */
  const preflightSeqRef = useRef(0);

  /** 构建/运行期诊断（完整校验 + 资产预检），并按区域运行范围过滤（决策 2.40）。 */
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

  const analysis = useAnalysisRuntime({
    definition: editorState?.definition ?? null,
    schemaCatalog,
    runScopeDiagnostics,
  });
  const run = useRunOrchestration({
    settings,
    runScopeDiagnostics,
    updateEditor,
    analysis: {
      refreshAnalysis: analysis.refreshAnalysis,
      syncAnalysisSnapshotRef: analysis.syncAnalysisSnapshotRef,
    },
    setErrorMessage,
    openProblems: () => setActiveTool("problems"),
    openResultAt,
  });

  /** 运行持有全局编辑锁（决策 2.33）。 */
  const busy = run.running;

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
    const currentRun = run.runState.run;
    if (
      editorState === null ||
      currentRun === null ||
      (currentRun.phase !== "building" &&
        currentRun.phase !== "validating" &&
        currentRun.phase !== "simulating")
    ) {
      return [];
    }
    const participants = new Set<string>();
    for (const slice of currentRun.build) {
      for (const method of slice.methods) {
        participants.add(method.nodeId);
      }
    }
    for (const batch of currentRun.batches) {
      participants.add(batch.nodeId);
    }
    return editorState.definition.nodes
      .filter((node) => !participants.has(node.id))
      .map((node) => node.id);
  }, [editorState, run.runState.run]);

  /** 构建限速推进时，当前应用中的节点（画布高亮）。 */
  const runningMethodNodeIds = useMemo(() => {
    const currentRun = run.runState.run;
    if (currentRun === null || currentRun.phase !== "building") {
      return [];
    }
    return currentRun.build
      .flatMap((slice) => slice.methods)
      .filter((method) => method.status === "running")
      .map((method) => method.nodeId);
  }, [run.runState.run]);

  /** 问题面板诊断：编辑期节点级诊断；最近一次运行/校验失败时显示校验/构建诊断（决策 2.40 修订）。 */
  const problemDiagnostics = useMemo<Diagnostic[]>(() => {
    if (editorState === null) {
      return [];
    }
    return run.validationDiagnostics.length > 0 ? run.validationDiagnostics : diagnostics;
  }, [diagnostics, editorState, run.validationDiagnostics]);

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
        const createdRegion = next.definition.regions[next.definition.regions.length - 1];
        if (createdRegion === undefined) {
          return state;
        }
        setRenameRegionRequestId(createdRegion.id);
        return setSelection(next, { regions: [createdRegion.id], nodes: [], edges: [] });
      }
      if (kind === "analysis_region") {
        const next = addRegion(state, "analysis", "分析区域", {
          x: position.x,
          y: position.y,
          width: 880,
          height: 440,
        });
        const createdRegion = next.definition.regions[next.definition.regions.length - 1];
        if (createdRegion === undefined) {
          return state;
        }
        setRenameRegionRequestId(createdRegion.id);
        return setSelection(next, { regions: [createdRegion.id], nodes: [], edges: [] });
      }
      const spec = getNodeKindSpec(kind);
      if (spec === null) {
        return state;
      }
      const targetRegionId = spec.region === null ? null : regionId;
      const next = addNode(state, kind, position, targetRegionId);
      const createdNode = next.definition.nodes[next.definition.nodes.length - 1];
      if (createdNode === undefined) {
        return state;
      }
      return setSelection(next, { nodes: [createdNode.id], regions: [], edges: [] });
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
    await analysis.closeAnalysisContexts();
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
    run.setValidationDiagnostics([]);
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
    await analysis.closeAnalysisContexts();
    setEditorState(createEmptyEditorState("未命名工作流"));
    setAppState((current) =>
      withCurrentWorkflow(current, { id: null, name: "未命名工作流" }),
    );
    rememberLastWorkflowId(null);
    setRenameRegionRequestId(null);
    setSelectionEpoch((epoch) => epoch + 1);
    setMissingAssetKeys([]);
    run.setValidationDiagnostics([]);
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
        await analysis.closeAnalysisContexts();
        setEditorState(createEmptyEditorState("未命名工作流"));
        setAppState((current) =>
          withCurrentWorkflow(current, { id: null, name: "未命名工作流" }),
        );
        rememberLastWorkflowId(null);
        setRenameRegionRequestId(null);
        setSelectionEpoch((epoch) => epoch + 1);
        setMissingAssetKeys([]);
        run.setValidationDiagnostics([]);
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


  /** 全部运行：整个工作流的运行计划进入共用编排。 */
  async function handleRun() {
    if (editorState === null || busy) {
      return;
    }
    const definition = editorStateToDefinition(editorState);
    await run.executeRunPlan(definition, planWorkflowRun(definition));
  }

  /** 区域运行（决策 2.40）：区域范围的运行计划进入共用编排，复用动画、校验与取消。 */
  async function handleRunRegion(regionId: string) {
    if (editorState === null || busy) {
      return;
    }
    const definition = editorStateToDefinition(editorState);
    await run.executeRunPlan(definition, planRegionRun(definition, regionId), new Set([regionId]));
  }

  /** 区域校验（决策 2.40 修订）：区域运行的子集，构建 + 批次校验，不提交模拟。 */
  async function handleValidateRegion(regionId: string) {
    if (editorState === null || busy) {
      return;
    }
    const definition = editorStateToDefinition(editorState);
    await run.executeRunPlan(
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
    run.setValidationDiagnostics([]);
    setErrorMessage(null);
    const runDiagnostics = runScopeDiagnostics(definition, new Set([regionId]));
    const inputPlan = planAnalysisInputRun(definition, regionId);
    const graphErrors = runDiagnostics.filter((item) => item.severity === "error");
    const errors = [...graphErrors.map((item) => item.message), ...inputPlan.errors];
    const hasFetch = planFetchNodes(definition, regionId).length > 0;
    if (errors.length > 0 || !hasFetch) {
      run.reportBuildFailure(
        inputPlan,
        errors.length > 0 ? errors : ["分析区域没有可运行的取数节点（未连接区域边界输入）"],
        [
          ...graphErrors,
          ...inputPlan.errors.map((message) => planErrorDiagnostic(message, inputPlan)),
        ],
        "分析区域没有可运行的取数节点（未连接区域边界输入）",
      );
      return;
    }
    const completeAnalysis = async (updated: WorkflowDefinition) => {
      analysis.setAnalysisRunPhase({ regionId, phase: "query" });
      await analysis.refreshAnalysis(updated, regionId);
      analysis.syncAnalysisSnapshotRef(updated);
      analysis.setAnalysisRunPhase(null);
    };
    if (inputPlan.batches.length > 0) {
      analysis.setAnalysisRunPhase({ regionId, phase: "input" });
      await run.executeRunPlan(
        definition,
        inputPlan,
        new Set([regionId]),
        "run",
        completeAnalysis,
      );
      analysis.setAnalysisRunPhase(null);
    } else {
      await completeAnalysis(definition);
    }
  }

  /** 打开结果面板并定位记录（决策 2.37）；sessionId 为空时只刷新列表。 */
  function openResultAt(sessionId: string | null): void {
    setActiveTool("results");
    setResultFocus(sessionId);
  }

  const runContextValue = {
    runState: run.runState,
    onCancelRun: run.handleCancelRun,
    onCancelBatch: run.handleCancelBatch,
  };

  return (
    <RunStateContext.Provider value={runContextValue}>
      <AnalysisSelectionContext.Provider value={analysis.analysisSelectionStore}>
      <AnalysisResultsContext.Provider value={analysis.analysisResults}>
      <AnalysisSchemaCatalogContext.Provider value={schemaCatalog}>
      <AnalysisStageSelectionContext.Provider value={analysis.analysisStageSelectionStore}>
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
          onCancelRun={() => void run.handleCancelRun()}
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
            <button
              type="button"
              className="icon-button"
              aria-label="关闭错误提示"
              onClick={() => setErrorMessage(null)}
            >
              <Close />
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
                <Settings size={20} />
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
                analysisResults={analysis.analysisResults}
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
                analysisRunPhase={analysis.analysisRunPhase}
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
