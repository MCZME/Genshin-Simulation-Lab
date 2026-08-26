import { useEffect, useRef, useState } from "react";
import { Handle, Position, useReactFlow, useStore } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import { COLORS } from "../../theme/tokens";
import {
  REGION_BOUNDARY_IN_PORT,
  REGION_BOUNDARY_OUT_PORT,
  type WorkflowRegion,
} from "../../workflow/types";
import { InputOrderPopover } from "./InputOrderPopover";
import type { IncomingOrderGroup } from "./InputOrderPopover";

const MIN_REGION_WIDTH = 400;
const MIN_REGION_HEIGHT = 240;

/** 分析区域运行阶段（2026-08-26 定案：获取输入 → 查询 → 视图加载）。 */
export interface AnalysisRunPhase {
  regionId: string;
  phase: "input" | "query" | "view";
}

export type RegionNodeData = {
  region: WorkflowRegion;
  onDeleteRegion: (regionId: string) => void;
  onRenameRegion: (regionId: string, name: string) => void;
  onResizeRegion: (
    regionId: string,
    rect: { x: number; y: number; width: number; height: number },
  ) => void;
  onMoveEdgeOrder: (
    targetNodeId: string,
    targetPortId: string,
    edgeId: string,
    direction: "up" | "down",
  ) => void;
  /** 区域校验入口（决策 2.40 修订）：区域运行的子集，构建 + 批次校验，不提交模拟。 */
  onValidateRegion: (regionId: string) => void;
  /** 区域运行入口（决策 2.40）：区域范围运行复用全部运行编排。 */
  onRunRegion: (regionId: string) => void;
  /** 分析区域运行入口（2026-08-26 定案）：获取输入 → 查询 → 视图加载。 */
  onRunAnalysis: (regionId: string) => void;
  /** 正在运行分析的区域及其阶段；未运行时为 null。 */
  analysisRunPhase: AnalysisRunPhase | null;
  /** 运行期间锁定破坏性交互。 */
  interactionLocked: boolean;
  incomingGroups: IncomingOrderGroup[];
  dropTarget: boolean;
  /** 新创建区域的一次性命名请求；处理后通过回调清除。 */
  renameRequested: boolean;
  onRenameRequestHandled: () => void;
} & Record<string, unknown>;

export function RegionNode({ data, selected, width, height }: NodeProps) {
  const {
    region,
    onDeleteRegion,
    onRenameRegion,
    onResizeRegion,
    onMoveEdgeOrder,
    onValidateRegion,
    onRunRegion,
    onRunAnalysis,
    analysisRunPhase,
    interactionLocked,
    incomingGroups,
    dropTarget,
    renameRequested,
    onRenameRequestHandled,
  } = data as RegionNodeData;
  const rf = useReactFlow();
  const connectionInProgress = useStore((state) => state.connection.inProgress);
  const resizeDragRef = useRef<{
    startFlow: { x: number; y: number };
    startSize: { width: number; height: number };
  } | null>(null);
  const [previewSize, setPreviewSize] = useState<{ width: number; height: number } | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [draftName, setDraftName] = useState("");
  const editingNameRef = useRef(false);
  const handledRenameRequestRef = useRef(false);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const borderColor =
    region.kind === "configuration" ? COLORS.region.configuration : COLORS.region.analysis;

  useEffect(() => {
    if (!renameRequested || handledRenameRequestRef.current) {
      return;
    }
    handledRenameRequestRef.current = true;
    editingNameRef.current = true;
    setDraftName(region.name);
    setEditingName(true);
    onRenameRequestHandled();
  }, [renameRequested, region.name, onRenameRequestHandled]);

  useEffect(() => {
    if (!editingName) {
      return;
    }
    nameInputRef.current?.focus();
    nameInputRef.current?.select();
  }, [editingName]);

  function startRename() {
    editingNameRef.current = true;
    setDraftName(region.name);
    setEditingName(true);
  }

  function commitRename() {
    if (!editingNameRef.current) {
      return;
    }
    editingNameRef.current = false;
    setEditingName(false);
    const nextName = draftName.trim();
    if (nextName !== "" && nextName !== region.name) {
      onRenameRegion(region.id, nextName);
    }
  }

  function cancelRename() {
    if (!editingNameRef.current) {
      return;
    }
    editingNameRef.current = false;
    setEditingName(false);
  }

  function handleResizePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    resizeDragRef.current = {
      startFlow: rf.screenToFlowPosition({ x: event.clientX, y: event.clientY }),
      startSize: {
        width: width ?? region.rect.width,
        height: height ?? region.rect.height,
      },
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handleResizePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const drag = resizeDragRef.current;
    if (drag === null) {
      return;
    }
    const current = rf.screenToFlowPosition({ x: event.clientX, y: event.clientY });
    setPreviewSize({
      width: Math.max(MIN_REGION_WIDTH, drag.startSize.width + current.x - drag.startFlow.x),
      height: Math.max(MIN_REGION_HEIGHT, drag.startSize.height + current.y - drag.startFlow.y),
    });
  }

  function handleResizePointerUp(event: React.PointerEvent<HTMLDivElement>) {
    const drag = resizeDragRef.current;
    if (drag === null) {
      return;
    }
    resizeDragRef.current = null;
    const current = rf.screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const size = {
      width: Math.max(MIN_REGION_WIDTH, drag.startSize.width + current.x - drag.startFlow.x),
      height: Math.max(MIN_REGION_HEIGHT, drag.startSize.height + current.y - drag.startFlow.y),
    };
    setPreviewSize(size);
    onResizeRegion(region.id, {
      x: region.rect.x,
      y: region.rect.y,
      ...size,
    });
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function handleResizePointerCancel(event: React.PointerEvent<HTMLDivElement>) {
    resizeDragRef.current = null;
    setPreviewSize(null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  const currentWidth = width ?? region.rect.width;
  const currentHeight = height ?? region.rect.height;
  if (
    previewSize !== null &&
    currentWidth === previewSize.width &&
    currentHeight === previewSize.height
  ) {
    setPreviewSize(null);
  }

  return (
    <div
      className={`region-node ${selected ? "selected" : ""} ${dropTarget ? "drop-target" : ""}`}
      style={{
        width: previewSize?.width ?? width ?? region.rect.width,
        height: previewSize?.height ?? height ?? region.rect.height,
        borderColor,
      }}
    >
      <header className="region-header" style={{ borderColor }}>
        <span className="region-kind">
          {region.kind === "configuration" ? "配置区域" : "分析区域"}
        </span>
        {editingName ? (
          <input
            ref={nameInputRef}
            className="region-name-input nodrag"
            value={draftName}
            maxLength={60}
            aria-label="区域名称"
            onChange={(event) => setDraftName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commitRename();
              } else if (event.key === "Escape") {
                event.preventDefault();
                cancelRename();
              }
            }}
            onBlur={commitRename}
          />
        ) : (
          <span
            className="region-name"
            title="双击重命名"
            onDoubleClick={startRename}
          >
            {region.name}
          </span>
        )}
        <div className="region-header-actions">
          {!editingName && region.kind === "configuration" && (
            <>
              <button
                type="button"
                className="text-button region-check nowheel nodrag"
                title="区域校验：构建该区域并校验批次成员，不执行模拟"
                disabled={interactionLocked}
                onClick={() => onValidateRegion(region.id)}
              >
                区域校验
              </button>
              <button
                type="button"
                className="text-button region-run nowheel nodrag"
                title="区域运行：仅运行该区域连接的模拟批次"
                disabled={interactionLocked}
                onClick={() => onRunRegion(region.id)}
              >
                区域运行
              </button>
            </>
          )}
          {!editingName && region.kind === "analysis" && (
            <button
              type="button"
              className="text-button region-analysis-run nowheel nodrag"
              title="运行分析：获取输入（缺会话时补跑模拟）、查询并加载视图"
              disabled={interactionLocked || analysisRunPhase?.regionId === region.id}
              onClick={() => onRunAnalysis(region.id)}
            >
              运行分析
            </button>
          )}
          {analysisRunPhase?.regionId === region.id && (
            <span className="region-analysis-phase">
              {analysisRunPhase.phase === "input"
                ? "获取输入…"
                : analysisRunPhase.phase === "query"
                  ? "查询…"
                  : "加载视图…"}
            </span>
          )}
          {!editingName && (
            <button
              type="button"
              className="icon-button region-rename"
              title="重命名区域"
              aria-label={`重命名区域 ${region.name}`}
              onClick={startRename}
            >
              ✎
            </button>
          )}
          {selected && (
            <button
              type="button"
              className="icon-button danger region-delete"
              title="删除区域"
              aria-label={`删除区域 ${region.name}`}
              disabled={interactionLocked}
              onClick={() => onDeleteRegion(region.id)}
            >
              ×
            </button>
          )}
        </div>
      </header>
      <div
        className="region-resize-handle nodrag"
        title="调整区域大小"
        onPointerDown={handleResizePointerDown}
        onPointerMove={handleResizePointerMove}
        onPointerUp={handleResizePointerUp}
        onPointerCancel={handleResizePointerCancel}
      />
      {region.kind === "configuration" && (
        <>
            <Handle
              type="target"
              position={Position.Left}
              id={REGION_BOUNDARY_OUT_PORT}
              className="region-handle"
              isConnectableStart={false}
            style={{
                left: "auto",
                right: -8,
                pointerEvents: connectionInProgress ? "auto" : "none",
              }}
            />
          <Handle
            type="source"
            position={Position.Right}
            id={REGION_BOUNDARY_OUT_PORT}
            className="region-handle"
            isConnectableEnd={false}
            style={{
              right: 0,
              pointerEvents: connectionInProgress ? "none" : "auto",
            }}
          />
        </>
      )}
      {region.kind === "analysis" && (
        <>
          <Handle
            type="target"
            position={Position.Left}
            id={REGION_BOUNDARY_IN_PORT}
            className="region-handle"
            isConnectableStart={false}
            style={{
              pointerEvents: connectionInProgress ? "auto" : "none",
            }}
          />
          <Handle
            type="source"
            position={Position.Right}
            id={REGION_BOUNDARY_IN_PORT}
            className="region-handle"
            isConnectableEnd={false}
            style={{
              right: "auto",
              left: 0,
              transform: "translate(-50%, -50%)",
              pointerEvents: connectionInProgress ? "none" : "auto",
            }}
          />
        </>
      )}
      <InputOrderPopover
        targetNodeId={region.id}
        groups={incomingGroups}
        onMoveEdgeOrder={onMoveEdgeOrder}
      />
    </div>
  );
}
