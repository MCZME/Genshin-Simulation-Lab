import { useEffect, useMemo, useRef, useState } from "react";
import {
  cancelRun,
  createWorkflow,
  getResultMetrics,
  getRun,
  getWorkflow,
  getWorkspace,
  listWorkflows,
  saveWorkflow,
  submitRun,
} from "../api/client";
import type { BatchMemberPayload } from "../api/client";
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
  deleteEdge,
  deleteNode,
  deleteRegion,
  moveNode,
  renameWorkflow,
  setNodeParams,
  setSelection,
  updateRegionRect,
} from "../state/editor_state";
import type { EditorSelection, EditorState } from "../state/editor_state";
import { markSaved } from "../state/editor_state";
import { createAppState, withCurrentWorkflow, withWorkspace } from "../state/app_state";
import { definitionToEditorState, editorStateToDefinition } from "../state/converters";
import { createExampleDefinition } from "../state/example_workflow";
import { applyRunView, createEmptyRunState, recordMemberMetrics } from "../state/run_state";
import type { RunState } from "../state/run_state";
import { compileConfigurationRegion } from "../workflow/compiler";
import type { CompileResult, Diagnostic, WorkflowDefinition } from "../workflow/types";
import { validateWorkflow } from "../workflow/validator";

type Tool = "objects" | "problems" | null;

export function App() {
  const [appState, setAppState] = useState(() => createAppState());
  const [editorState, setEditorState] = useState<EditorState | null>(null);
  const [runState, setRunState] = useState<RunState>(() => createEmptyRunState());
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<Tool>("objects");
  const initializedRef = useRef(false);
  const pollControllerRef = useRef<AbortController | null>(null);

  async function initialize() {
    try {
      const workspace = await getWorkspace();
      setAppState((current) => withWorkspace(current, workspace));

      const workflowList = await listWorkflows();
      const existing = workflowList.items[0];
      let workflowId: string;
      let definition: WorkflowDefinition;
      if (existing !== undefined) {
        workflowId = existing.id;
        const detail = await getWorkflow(workflowId);
        definition = detail.definition as unknown as WorkflowDefinition;
      } else {
        const created = await createWorkflow("示例工作流");
        workflowId = created.id;
        definition = createExampleDefinition();
        await saveWorkflow(workflowId, definition);
      }
      setEditorState(definitionToEditorState(definition));
      setAppState((current) =>
        withCurrentWorkflow(current, { id: workflowId, name: definition.meta.name }),
      );
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

  function handleAddRegion() {
    updateEditor((state) =>
      addRegion(state, "configuration", "配置区域", {
        x: 80 + state.definition.regions.length * 24,
        y: 80 + state.definition.regions.length * 24,
        width: 880,
        height: 440,
      }),
    );
  }

  function handleAddNode(kind: string) {
    updateEditor((state) => {
      const regionId =
        kind === "simulation"
          ? null
          : (state.selection.regions.find((id) =>
              state.definition.regions.some(
                (region) => region.id === id && region.kind === "configuration",
              ),
            ) ??
            state.definition.regions.find((region) => region.kind === "configuration")?.id ??
            null);
      const offset = (state.definition.nodes.length % 6) * 28;
      return addNode(state, kind, { x: 120 + offset, y: 120 + offset }, regionId);
    });
  }

  function handleLoadExample() {
    setEditorState(definitionToEditorState(createExampleDefinition()));
    setRunState(createEmptyRunState());
    setErrorMessage(null);
  }

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
    if (editorState === null || appState.workflowId === null) {
      return;
    }
    setSaving(true);
    setErrorMessage(null);
    try {
      const definition = editorStateToDefinition(editorState);
      await saveWorkflow(appState.workflowId, definition);
      setEditorState((current) => (current === null ? current : markSaved(current)));
      setAppState((current) =>
        withCurrentWorkflow(current, {
          id: appState.workflowId!,
          name: definition.meta.name,
        }),
      );
    } catch (error) {
      setErrorMessage(toMessage(error));
    } finally {
      setSaving(false);
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

    setRunning(true);
    setErrorMessage(null);
    setRunState(createEmptyRunState());
    try {
      const submitted = await submitRun(members, { name: definition.meta.name });
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
          onRename={handleRename}
          onSave={() => void handleSave()}
          onRun={() => void handleRun()}
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
              onAddNode={handleAddNode}
              onAddRegion={handleAddRegion}
              onLoadExample={handleLoadExample}
            />
          )}
          {activeTool === "problems" && editorState !== null && (
            <ProblemPanel diagnostics={diagnostics} onLocate={handleLocate} />
          )}
          <main className="canvas-area">
            <RegionSummaryBar compiles={compiles} />
            {editorState !== null && (
              <CanvasView
                definition={editorState.definition}
                onMoveNode={(nodeId, position) =>
                  updateEditor((state) => moveNode(state, nodeId, position))
                }
                onMoveRegion={(regionId, position) =>
                  updateEditor((state) =>
                    updateRegionRect(state, regionId, {
                      x: position.x,
                      y: position.y,
                      width:
                        state.definition.regions.find((region) => region.id === regionId)?.rect
                          .width ?? 880,
                      height:
                        state.definition.regions.find((region) => region.id === regionId)?.rect
                          .height ?? 440,
                    }),
                  )
                }
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
              />
            )}
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
