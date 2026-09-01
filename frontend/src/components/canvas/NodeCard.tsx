import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import { useReactFlow } from "@xyflow/react";
import { useCallback, useRef, useState } from "react";
import { InputOrderPopover } from "./InputOrderPopover";
import type { IncomingOrderGroup } from "./InputOrderPopover";
import { nodeKindColor } from "../nodes/registry";
import { NodeEditorHost } from "../nodes/registry";
import { useAnalysisSchemaCatalog } from "../analysis_context";
import { AnalysisDetailBody, isAnalysisDetailKind, SingleItemBody } from "../nodes/detail";
import { AnalysisViewBody, type ViewFitInfo } from "../nodes/views";
import { getNodeKindSpec } from "../../workflow/registry";
import type { NodeSize, WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import {
  DEFAULT_DETAIL_WIDTH,
  DEFAULT_VIEW_HEIGHT,
  MAX_DETAIL_WIDTH,
  MAX_TRACE_WIDTH,
  MAX_VIEW_HEIGHT,
  MIN_TRACE_WIDTH,
  MIN_DETAIL_WIDTH,
  MIN_VIEW_HEIGHT,
  MIN_VIEW_WIDTH,
  VIEW_SOFT_CAP_WIDTH,
  clamp,
  resolveBarHeight,
  resolveDragMaxWidth,
  resolveManualViewWidth,
  resolveTraceWidth,
  resolveViewHeight,
  resolveViewWidth,
} from "../../workflow/view_size";
import type { Diagnostic } from "../../workflow/types";
import type { AnalysisNodeResult } from "../../workflow/analysis_runner";

export type WorkflowNodeData = {
  node: WorkflowNode;
  definition: WorkflowDefinition;
  onParamsChange: (nodeId: string, params: Record<string, unknown>) => void;
  onDeleteNode: (nodeId: string) => void;
  onLocateNode: (nodeId: string) => void;
  onMoveEdgeOrder: (
    targetNodeId: string,
    targetPortId: string,
    edgeId: string,
    direction: "up" | "down",
  ) => void;
  incomingGroups: IncomingOrderGroup[];
  memberPorts: MemberPortInfo[];
  groupCount: number;
  diagnostics: Diagnostic[];
  /** 运行进行中：不在执行路径上的节点置灰（决策 2.34）。 */
  dimmed: boolean;
  /** 构建限速推进中当前应用中的节点（决策 2.34 修订）。 */
  stepRunning: boolean;
  /** 运行/检查期间锁定破坏性交互。 */
  interactionLocked: boolean;
  /** 分析执行结果（表节点 = 查询结果；视图节点 = 拼接后的输入表）。 */
  analysisResult?: AnalysisNodeResult;
  /** 提交节点画布几何（按轴部分更新，宽高分别持久化）。 */
  onResizeNode: (nodeId: string, size: Partial<NodeSize>) => void;
} & Record<string, unknown>;

export interface MemberPortInfo {
  portId: string;
  itemId: string;
  label: string;
  connected: boolean;
}

export function NodeCard({ data, selected }: NodeProps) {
  const {
    node,
    definition,
    onParamsChange,
    onDeleteNode,
    onLocateNode,
    onMoveEdgeOrder,
    incomingGroups,
    memberPorts,
    groupCount,
    diagnostics,
    dimmed,
    stepRunning,
    interactionLocked,
    analysisResult,
    onResizeNode,
  } = data as WorkflowNodeData;
  const spec = getNodeKindSpec(node.kind);
  const isDraft = node.region_id === null && spec?.region !== null;
  const isView = isAnalysisView(node.kind);
  const isTable = node.kind === "member_table";
  const isPie = node.kind === "pie";
  const isBar = node.kind === "bar";
  // 伤害详情卡支持手动调宽（高度随内容），其余详情节点维持固定宽度。
  const isDetailResizable = node.kind === "damage_detail";
  const isTraceResizable = node.kind === "input_trace";
  const isWidthOnlyResizable = isDetailResizable || isTraceResizable;
  const rf = useReactFlow();
  const catalog = useAnalysisSchemaCatalog();
  const fieldErrors = collectFieldErrors(diagnostics, node.id);
  const [membersOpen, setMembersOpen] = useState(false);
  const [fitInfo, setFitInfo] = useState<ViewFitInfo | null>(null);
  const [previewSize, setPreviewSize] = useState<Partial<NodeSize> | null>(null);
  const resizeDragRef = useRef<{
    axis: "width" | "height";
    startFlow: { x: number; y: number };
    startWidth: number;
    startHeight: number;
  } | null>(null);
  const handleFitChange = useCallback((info: ViewFitInfo) => {
    setFitInfo(info);
  }, []);
  const resolvedWidth =
    isTable || isBar
      ? resolveViewWidth(fitInfo?.fitWidth ?? null, node.size?.width)
      : isPie
        ? resolveManualViewWidth(node.size?.width)
        : isDetailResizable
          ? clamp(
              Math.round(node.size?.width ?? DEFAULT_DETAIL_WIDTH),
              MIN_DETAIL_WIDTH,
              MAX_DETAIL_WIDTH,
            )
          : isTraceResizable
            ? resolveTraceWidth(node.size?.width)
            : undefined;
  const resolvedHeight = isBar
    ? resolveBarHeight(fitInfo?.fitHeight ?? null, node.size?.height)
    : isView
      ? resolveViewHeight(node.size?.height)
      : undefined;
  const dragMaxWidth =
    isTable || isBar
      ? resolveDragMaxWidth(fitInfo?.fitWidth ?? null)
      : isPie
        ? VIEW_SOFT_CAP_WIDTH
        : undefined;
  const dragMaxHeight = isBar
    ? fitInfo?.fitHeight ?? MAX_VIEW_HEIGHT
    : MAX_VIEW_HEIGHT;
  const displayWidth = previewSize?.width ?? resolvedWidth;
  const displayHeight = previewSize?.height ?? resolvedHeight;
  const hasMemberPorts = memberPorts.length > 0;
  const connectedMembers = memberPorts.filter((port) => port.connected);

  function clampDragSize(
    axis: "width" | "height",
    dx: number,
    dy: number,
    startWidth: number,
    startHeight: number,
  ): Partial<NodeSize> {
    if (axis === "width") {
      const [minWidth, maxWidth] = isDetailResizable
        ? [MIN_DETAIL_WIDTH, MAX_DETAIL_WIDTH]
        : isTraceResizable
          ? [MIN_TRACE_WIDTH, MAX_TRACE_WIDTH]
          : [MIN_VIEW_WIDTH, dragMaxWidth ?? VIEW_SOFT_CAP_WIDTH];
      return { width: clamp(Math.round(startWidth + dx), minWidth, maxWidth) };
    }
    return { height: clamp(Math.round(startHeight + dy), MIN_VIEW_HEIGHT, dragMaxHeight) };
  }

  function startResize(
    event: React.PointerEvent<HTMLDivElement>,
    axis: "width" | "height",
  ) {
    if (event.button !== 0 || interactionLocked) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    resizeDragRef.current = {
      axis,
      startFlow: rf.screenToFlowPosition({ x: event.clientX, y: event.clientY }),
      startWidth: displayWidth ?? (isDetailResizable ? DEFAULT_DETAIL_WIDTH : MIN_VIEW_WIDTH),
      startHeight: displayHeight ?? DEFAULT_VIEW_HEIGHT,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handleResizeMove(event: React.PointerEvent<HTMLDivElement>) {
    const drag = resizeDragRef.current;
    if (drag === null) {
      return;
    }
    const current = rf.screenToFlowPosition({ x: event.clientX, y: event.clientY });
    setPreviewSize(
      clampDragSize(
        drag.axis,
        current.x - drag.startFlow.x,
        current.y - drag.startFlow.y,
        drag.startWidth,
        drag.startHeight,
      ),
    );
  }

  function handleResizeUp(event: React.PointerEvent<HTMLDivElement>) {
    const drag = resizeDragRef.current;
    if (drag === null) {
      return;
    }
    resizeDragRef.current = null;
    const current = rf.screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const size = clampDragSize(
      drag.axis,
      current.x - drag.startFlow.x,
      current.y - drag.startFlow.y,
      drag.startWidth,
      drag.startHeight,
    );
    setPreviewSize(null);
    if (drag.axis === "width") {
      onResizeNode(node.id, { width: size.width ?? drag.startWidth });
    } else {
      onResizeNode(node.id, { height: size.height ?? drag.startHeight });
    }
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function cancelResize(event: React.PointerEvent<HTMLDivElement>) {
    resizeDragRef.current = null;
    setPreviewSize(null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return (
    <div
      className={`node-card ${isAnalysisView(node.kind) ? "node-card-view" : ""} ${node.kind === "input_trace" ? "node-card-trace" : ""} ${node.kind === "artifact" ? "node-card-artifact" : ""} ${node.kind === "fetch" ? "node-card-fetch" : ""} ${node.kind === "table_config" ? "node-card-table-config" : ""} ${node.kind === "pie_config" || node.kind === "bar_config" ? "node-card-display-config" : ""} ${node.kind === "filter" ? "node-card-filter" : ""} ${node.kind === "aggregate" ? "node-card-aggregate" : ""} ${node.kind === "project" ? "node-card-project" : ""} ${node.kind === "sort" ? "node-card-sort" : ""} ${node.kind === "join" ? "node-card-join" : ""} ${node.kind === "compute" ? "node-card-compute" : ""} ${selected ? "selected" : ""} ${isDraft ? "draft" : ""} ${dimmed ? "dimmed" : ""} ${stepRunning ? "step-running" : ""}`}
      style={
        isView
          ? { width: displayWidth, height: displayHeight }
          : isWidthOnlyResizable
            ? { width: displayWidth }
            : undefined
      }
    >
      <header className="node-card-header">
        <span className="node-dot" style={{ background: nodeKindColor(node.kind) }} />
        <span className="node-title">{spec?.displayName ?? node.kind}</span>
        {isDraft && <span className="draft-badge">草稿</span>}
        <button
          type="button"
          className="icon-button danger"
          title="删除节点"
          disabled={interactionLocked}
          onClick={() => onDeleteNode(node.id)}
        >
          ×
        </button>
      </header>
      <div className="node-card-body">
        {isAnalysisView(node.kind) ? (
          <AnalysisViewBody
            node={node}
            result={analysisResult}
            definition={definition}
            onLocateNode={onLocateNode}
            viewWidth={isView ? resolvedWidth : undefined}
            onFitChange={node.kind === "member_table" ? handleFitChange : undefined}
          />
        ) : isAnalysisDetailKind(node.kind) ? (
          <AnalysisDetailBody node={node} definition={definition} />
        ) : node.kind === "single" ? (
          <SingleItemBody result={analysisResult} />
        ) : (
          <NodeEditorHost
            kind={node.kind}
            node={node}
            definition={definition}
            catalog={catalog}
            fieldErrors={fieldErrors}
            onChange={(params) => onParamsChange(node.id, params)}
          />
        )}
      </div>
      <footer className="node-card-footer">
        {hasMemberPorts && (
          <button
            type="button"
            className="member-toggle"
            onClick={() => setMembersOpen((current) => !current)}
          >
            {membersOpen ? "收起成员" : `成员 ${memberPorts.length}`}
          </button>
        )}
        {!membersOpen &&
          connectedMembers.map((port) => (
            <span className="member-connection-label" key={port.portId} title={port.label}>
              {port.label}
            </span>
          ))}
        {spec?.ports.outputs.some((port) => port.cardinality === "group") && groupCount > 0 && (
          <span className="group-badge" title="组输出成员数">
            {groupCount}
          </span>
        )}
        {spec?.ports.inputs.map((port) => (
          <Handle
            key={`target-${port.id}`}
            type="target"
            position={Position.Left}
            id={port.id}
            className="node-handle"
          />
        ))}
        {spec?.ports.outputs.map((port) => (
          <Handle
            key={`source-${port.id}`}
            type="source"
            position={Position.Right}
            id={port.id}
            className="node-handle"
          />
        ))}
      </footer>
      {membersOpen && (
        <div className="member-ports">
          {memberPorts.map((port) => (
            <div className="member-port-row" key={port.portId}>
              <span className="member-port-label" title={port.label}>
                {port.label}
              </span>
              <Handle
                type="source"
                position={Position.Right}
                id={port.portId}
                className="node-handle"
              />
            </div>
          ))}
        </div>
      )}
      <InputOrderPopover
        targetNodeId={node.id}
        groups={incomingGroups}
        onMoveEdgeOrder={onMoveEdgeOrder}
      />
      {isWidthOnlyResizable && (
        <div
          className="node-resize-handle node-resize-handle-right nodrag visible"
          title="拖拽调整宽度"
          onPointerDown={(event) => startResize(event, "width")}
          onPointerMove={handleResizeMove}
          onPointerUp={handleResizeUp}
          onPointerCancel={cancelResize}
        />
      )}
      {isView && (
        <>
          <div
            className="node-resize-handle node-resize-handle-bottom nodrag"
            title="拖拽调整高度"
            onPointerDown={(event) => startResize(event, "height")}
            onPointerMove={handleResizeMove}
            onPointerUp={handleResizeUp}
            onPointerCancel={cancelResize}
          />
          <div
            className="node-resize-handle node-resize-handle-right nodrag"
            title={
              isTable && fitInfo !== null && fitInfo.hiddenColumns > 0
                ? `还有 ${fitInfo.hiddenColumns} 列被隐藏，拖宽查看`
                : "拖拽调整宽度"
            }
            onPointerDown={(event) => startResize(event, "width")}
            onPointerMove={handleResizeMove}
            onPointerUp={handleResizeUp}
            onPointerCancel={cancelResize}
          />
        </>
      )}
    </div>
  );
}

function isAnalysisView(kind: string): boolean {
  return kind === "member_table" || kind === "pie" || kind === "bar";
}

function collectFieldErrors(
  diagnostics: Diagnostic[],
  nodeId: string,
): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  for (const item of diagnostics) {
    if (item.node_id !== nodeId || item.path === null) {
      continue;
    }
    const list = result[item.path] ?? [];
    list.push(item.message);
    result[item.path] = list;
  }
  return result;
}
