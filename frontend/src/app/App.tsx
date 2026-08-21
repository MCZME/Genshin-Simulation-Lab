import { useEffect, useMemo, useRef, useState } from "react";
import {
  cancelRun,
  createWorkflow,
  deleteWorkflow,
  getResultMetrics,
  getRun,
  getWorkflow,
  getWorkspace,
  listWorkflows,
  saveWorkflow,
  submitRun,
} from "../api/client";
import type { BatchMemberPayload, WorkflowListItem } from "../api/client";
import { isRunTerminal, pollRun } from "../api/runtime_subscription";
import { CanvasView } from "../components/canvas/CanvasView";
import { ObjectPanel } from "../components/panels/ObjectPanel";
import { ProblemPanel } from "../components/panels/ProblemPanel";
import { RegionSummaryBar } from "../components/panels/RegionSummaryBar";
import { ResultPanel } from "../components/panels/ResultPanel";
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
import { applyRunView, createEmptyRunState, recordMemberMetrics } from "../state/run_state";
import type { RunState } from "../state/run_state";
import { compileConfigurationRegion } from "../workflow/compiler";
import type { CompileResult, Diagnostic, WorkflowDefinition } from "../workflow/types";
import { validateWorkflow } from "../workflow/validator";
import { getNodeKindSpec } from "../workflow/registry";

type Tool = "objects" | "problems" | null;

export function App() {
  const [appState, setAppState] = useState(() => createAppState());
  const [editorState, setEditorState] = useState<EditorState | null>(null);
  const [workflowList, setWorkflowList] = useState<WorkflowListItem[]>([]);
  const [runState, setRunState] = useState<RunState>(() => createEmptyRunState());
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<Tool>("objects");
  const [dragKind, setDragKind] = useState<string | null>(null);
  const [selectionEpoch, setSelectionEpoch] = useState(0);
  const [renameRegionRequestId, setRenameRegionRequestId] = useState<string | null>(null);
  const [viewportCommand, setViewportCommand] = useState<
    "zoom-in" | "zoom-out" | "fit" | null
  >(null);
  const initializedRef = useRef(false);
  const pollControllerRef = useRef<AbortController | null>(null);

  async function initialize() {
    try {
      const workspace = await getWorkspace();
      setAppState((current) => withWorkspace(current, workspace));

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
      !running &&
      !diagnostics.some((item) => item.severity === "error") &&
      compiles.some((result) => result.ok)
    );
  }, [editorState, running, diagnostics, compiles]);

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
      const targetRegionId = spec.region === "bridge" ? null : regionId;
      const next = addNode(state, kind, position, targetRegionId);
      const createdNodeId = next.definition.nodes[next.definition.nodes.length - 1].id;
      return setSelection(next, { nodes: [createdNodeId], regions: [], edges: [] });
    });
    setDragKind(null);
  }

  function handleUndo() {
    if (running) {
      return;
    }
    updateEditor((state) => setSelection(undo(state), { regions: [], nodes: [], edges: [] }));
    setSelectionEpoch((epoch) => epoch + 1);
  }

  function handleRedo() {
    if (running) {
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
        if (editable || running || editorState === null) {
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
        if (editable || running || editorState === null) {
          return;
        }
        const step = event.shiftKey ? 10 : 1;
        const dx =
          key === "ArrowLeft" ? -step : key === "ArrowRight" ? step : 0;
        const dy = key === "ArrowUp" ? -step : key === "ArrowDown" ? step : 0;
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
    if (editorState === null || running) {
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
    if (editorState === null || running) {
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
    if (running) {
      return;
    }
    try {
      await handleSwitchTo(workflowId);
    } catch (error) {
      setErrorMessage(toMessage(error));
    }
  }

  async function handleSaveAndSwitch(workflowId: string): Promise<void> {
    if (editorState === null || running) {
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
    if (running) {
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
    if (editorState === null || running) {
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
    if (running) {
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

  async function handleRun() {
    if (editorState === null || running) {
      return;
    }
    const definition = editorStateToDefinition(editorState);
    const members: BatchMemberPayload[] = [];
    for (const region of definition.regions) {
      if (region.kind !== "configuration") {
        continue;
      }
      const result = compileConfigurationRegion(definition, region.id);
      if (!result.ok) {
        setErrorMessage(`区域 ${region.id} 无法编译，请先修复问题`);
        return;
      }
      members.push(...result.members);
    }
    if (members.length === 0) {
      setErrorMessage("没有可运行的配置区域");
      return;
    }
    if (
      members.some((member) => {
        const meta = member.input.meta as Record<string, unknown> | undefined;
        return (
          meta === undefined ||
          typeof meta.name !== "string" ||
          meta.name.trim() === ""
        );
      })
    ) {
      setErrorMessage("配置区域缺少元信息节点，请配置名称后运行");
      return;
    }
    const firstMeta = members[0].input.meta as Record<string, unknown> | undefined;
    const runName =
      firstMeta !== undefined && typeof firstMeta.name === "string"
        ? firstMeta.name
        : definition.meta.name;

    setRunning(true);
    setErrorMessage(null);
    setRunState(createEmptyRunState());
    try {
      const submitted = await submitRun(members, { name: runName });
      setRunState((current) => applyRunView(current, submitted));
      const controller = new AbortController();
      pollControllerRef.current = controller;
      const finalView = await pollRun(
        submitted.run_id,
        (view) => setRunState((current) => applyRunView(current, view)),
        { signal: controller.signal, intervalMs: 1000, getRun },
      );
      for (const member of finalView.members) {
        const sessionId = member.session_id;
        if (member.state === "completed" && sessionId != null) {
          try {
            const metrics = await getResultMetrics(sessionId);
            setRunState((current) => recordMemberMetrics(current, member.item_id, metrics));
          } catch {
            // 单成员指标失败不阻断结果面板
          }
        }
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setErrorMessage(toMessage(error));
      }
    } finally {
      setRunning(false);
      pollControllerRef.current = null;
    }
  }

  async function handleCancelRun() {
    const runId = runState.runId;
    if (runId === null) {
      return;
    }
    pollControllerRef.current?.abort();
    try {
      const view = await cancelRun(runId);
      setRunState((current) => applyRunView(current, view));
      if (!isRunTerminal(view.state)) {
        const controller = new AbortController();
        pollControllerRef.current = controller;
        const finalView = await pollRun(
          runId,
          (next) => setRunState((current) => applyRunView(current, next)),
          { signal: controller.signal, intervalMs: 1000, getRun },
        );
        setRunState((current) => applyRunView(current, finalView));
      }
    } catch (error) {
      setErrorMessage(toMessage(error));
    }
  }

  const runContextValue = { runState, onCancelRun: handleCancelRun };

  return (
    <RunStateContext.Provider value={runContextValue}>
      <div className="app-shell">
        <TopBar
          name={editorState?.definition.meta.name ?? appState.workflowName}
          dirty={editorState?.dirty ?? false}
          saving={saving}
          running={running}
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
          <main className="canvas-area">
            {editorState !== null && (
              <CanvasView
                definition={editorState.definition}
                selection={editorState.selection}
                diagnostics={diagnostics}
                dragKind={dragKind}
                selectionEpoch={selectionEpoch}
                viewportCommand={viewportCommand}
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
              />
            )}
            <RegionSummaryBar compiles={compiles} />
          </main>
          {runState.runId !== null && <ResultPanel runState={runState} />}
        </div>
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
  return left.length === right.length && left.every((value, index) => value === right[index]);
}
