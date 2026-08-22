import { useEffect, useMemo, useRef, useState } from "react";
import {
  cancelRun,
  createWorkflow,
  deleteWorkflow,
  getRun,
  getWorkflow,
  getWorkspace,
  listWorkflows,
  saveWorkflow,
  submitRun,
  validateInputs,
} from "../api/client";
import type { WorkflowListItem } from "../api/client";
import { pollRun } from "../api/runtime_subscription";
import { CanvasView } from "../components/canvas/CanvasView";
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
import { definitionToEditorState, editorStateToDefinition } from "../state/converters";
import {
  applyBatchView,
  batchStatusFromRunState,
  createEmptyRunState,
  createRunView,
  setBatchStatus,
  setMethodStatus,
  setRegionCheck,
  setRunPhase,
} from "../state/run_state";
import type { RunState } from "../state/run_state";
import { compileConfigurationRegion } from "../workflow/compiler";
import {
  hasRunnableBatch,
  paceBuildSteps,
  planRegionCheck,
  planWorkflowRun,
} from "../workflow/runner";
import type { CompileResult, Diagnostic, WorkflowDefinition } from "../workflow/types";
import { validateWorkflow } from "../workflow/validator";
import { getNodeKindSpec } from "../workflow/registry";
import { createAppSettings, loadAppSettingsFromApi, saveAppSettingsToApi } from "../state/settings";
import type { AppSettings } from "../state/settings";
import { SettingsModal } from "../components/shell/SettingsModal";

type Tool = "objects" | "problems" | "results" | null;

export function App() {
  const [appState, setAppState] = useState(() => createAppState());
  const [editorState, setEditorState] = useState<EditorState | null>(null);
  const [workflowList, setWorkflowList] = useState<WorkflowListItem[]>([]);
  const [runState, setRunState] = useState<RunState>(() => createEmptyRunState());
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [checkingRegion, setCheckingRegion] = useState<string | null>(null);
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
    "zoom-in" | "zoom-out" | "fit" | null
  >(null);
  const initializedRef = useRef(false);
  /** 运行编排内部信号：取消整次工作流运行（当前批取消 + 剩余批次跳过）。 */
  const cancelRequestedRef = useRef(false);
  /** 当前在跑批次：模拟节点 id 与后端 run_id，供「取消整批」定位。 */
  const currentBatchRef = useRef<{ nodeId: string; runId: string | null } | null>(null);

  /** 运行与区域检查都持有全局编辑锁（决策 2.33 / 2.35）。 */
  const busy = running || checkingRegion !== null;

  async function initialize() {
    try {
      const workspace = await getWorkspace();
      setAppState((current) => withWorkspace(current, workspace));
      setSettings(await loadAppSettingsFromApi());

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
      setEditorState(definitionToEditorState(definition));
      setAppState((current) =>
        withCurrentWorkflow(current, { id: workflowId, name: definition.meta.name }),
      );
      rememberLastWorkflowId(workflowId);
    } catch (error) {
      setErrorMessage(toMessage(error));
    }
  }

  useEffect(() => {
    if (initializedRef.current) {
      return;
    }
    initializedRef.current = true;
    void initialize();
  }, []);

  const { diagnostics, compiles } = useMemo(() => {
    if (editorState === null) {
      return { diagnostics: [] as Diagnostic[], compiles: [] as CompileResult[] };
    }
    const definition = editorState.definition;
    return {
      diagnostics: validateWorkflow(definition),
      compiles: definition.regions
        .filter((region) => region.kind === "configuration")
        .map((region) => compileConfigurationRegion(definition, region.id)),
    };
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
      (run.phase !== "building" && run.phase !== "simulating")
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

  function handleCreateWorkflow(): void {
    if (busy) {
      return;
    }
    setEditorState(createEmptyEditorState("未命名工作流"));
    setAppState((current) =>
      withCurrentWorkflow(current, { id: null, name: "未命名工作流" }),
    );
    rememberLastWorkflowId(null);
    setRenameRegionRequestId(null);
    setSelectionEpoch((epoch) => epoch + 1);
  }

  async function handleSaveAndCreate(): Promise<void> {
    if (editorState === null || busy) {
      return;
    }
    setSaving(true);
    setErrorMessage(null);
    try {
      await persistCurrentWorkflow();
      handleCreateWorkflow();
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
        setEditorState(createEmptyEditorState("未命名工作流"));
        setAppState((current) =>
          withCurrentWorkflow(current, { id: null, name: "未命名工作流" }),
        );
        rememberLastWorkflowId(null);
        setRenameRegionRequestId(null);
        setSelectionEpoch((epoch) => epoch + 1);
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
   * 工作流运行（决策 2.33，2.38 修订）：构建（前端编译与图校验，失败零提交）→
   * 模拟（按画布顺序依次串行执行每个模拟节点的批次，决策 2.32）→ 终态。
   */
  async function handleRun() {
    if (editorState === null || busy) {
      return;
    }
    const definition = editorStateToDefinition(editorState);
    const plan = planWorkflowRun(definition);
    const buildErrors = [
      ...diagnostics
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
      // 构建失败（零提交）错误经顶部横幅呈现（决策 2.37）。
      setErrorMessage(`构建失败：${errors.join("；")}`);
      return;
    }

    setErrorMessage(null);
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

    setRunState((current) => setRunPhase(current, "simulating"));

    cancelRequestedRef.current = false;
    let cancelled = false;
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
      openResultAt(null);
    } else {
      setRunState((current) => setRunPhase(current, "completed"));
      // 运行结束联动（决策 2.37）：自动打开结果面板并定位最新记录。
      openResultAt(completedSessions[0]?.sessionId ?? null);
    }
    setRunning(false);
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

  /** 检查区域（决策 2.35）：单区域构建 + 对成员的后端输入校验；不执行模拟。 */
  async function handleCheckRegion(regionId: string) {
    if (editorState === null || busy) {
      return;
    }
    const definition = editorStateToDefinition(editorState);
    const plan = planRegionCheck(definition, regionId);
    setCheckingRegion(regionId);
    setRunState((current) =>
      setRegionCheck(current, {
        regionId,
        status: "checking",
        memberCount: plan.ok ? plan.members.length : 0,
        methods: plan.methods,
        memberResults: [],
        error: plan.error,
      }),
    );
    try {
      if (!plan.ok) {
        setRunState((current) =>
          setRegionCheck(current, {
            regionId,
            status: "failed",
            memberCount: 0,
            methods: [],
            memberResults: [],
            error: plan.error,
          }),
        );
        return;
      }
      const response = await validateInputs(plan.members);
      const memberResults = response.members.map((member) => ({
        item_id: member.item_id,
        ok: member.ok,
        messages: member.ok
          ? []
          : (member.details ?? []).map((detail) => detail.message).filter(Boolean),
      }));
      const failedCount = memberResults.filter((member) => !member.ok).length;
      setRunState((current) =>
        setRegionCheck(current, {
          regionId,
          status: response.ok ? "passed" : "failed",
          memberCount: plan.members.length,
          methods: plan.methods,
          memberResults,
          error: response.ok ? null : `${failedCount} 个成员未通过校验`,
        }),
      );
    } catch (error) {
      setRunState((current) =>
        setRegionCheck(current, {
          regionId,
          status: "failed",
          memberCount: 0,
          methods: [],
          memberResults: [],
          error: toMessage(error),
        }),
      );
    } finally {
      setCheckingRegion(null);
    }
  }

  const runContextValue = {
    runState,
    onCancelRun: handleCancelRun,
    onCancelBatch: handleCancelBatch,
  };

  return (
    <RunStateContext.Provider value={runContextValue}>
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
          onCreate={handleCreateWorkflow}
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
              {diagnostics.filter((item) => item.severity === "error").length > 0 && (
                <span className="rail-badge">
                  {diagnostics.filter((item) => item.severity === "error").length}
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
            <ProblemPanel diagnostics={diagnostics} onLocate={handleLocate} />
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
                selection={editorState.selection}
                diagnostics={diagnostics}
                dragKind={dragKind}
                selectionEpoch={selectionEpoch}
                viewportCommand={viewportCommand}
                dimmedNodeIds={dimmedNodeIds}
                runningMethodNodeIds={runningMethodNodeIds}
                interactionLocked={busy}
                checkingRegionId={checkingRegion}
                onViewportCommandHandled={() => setViewportCommand(null)}
                onMoveNode={(nodeId, position, regionId) =>
                  updateEditor((state) => moveNodeWithRegion(state, nodeId, position, regionId))
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
                onDropObject={handleDropObject}
                onMoveEdgeOrder={handleMoveEdgeOrder}
                onCheckRegion={(regionId) => void handleCheckRegion(regionId)}
              />
            )}
            <RegionSummaryBar
              compiles={compiles}
              regionChecks={runState.regionChecks}
              checkingRegionId={checkingRegion}
            />
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
