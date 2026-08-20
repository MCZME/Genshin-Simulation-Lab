import { useRef, useState } from "react";
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

export type RegionNodeData = {
  region: WorkflowRegion;
  onDeleteRegion: (regionId: string) => void;
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
  incomingGroups: IncomingOrderGroup[];
  dropTarget: boolean;
} & Record<string, unknown>;

export function RegionNode({ data, selected, width, height }: NodeProps) {
  const {
    region,
    onDeleteRegion,
    onResizeRegion,
    onMoveEdgeOrder,
    incomingGroups,
    dropTarget,
  } = data as RegionNodeData;
  const rf = useReactFlow();
  const connectionInProgress = useStore((state) => state.connection.inProgress);
  const resizeDragRef = useRef<{
    startFlow: { x: number; y: number };
    startSize: { width: number; height: number };
  } | null>(null);
  const [previewSize, setPreviewSize] = useState<{ width: number; height: number } | null>(null);
  const borderColor =
    region.kind === "configuration" ? COLORS.region.configuration : COLORS.region.analysis;

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
        <span className="region-name">{region.name}</span>
        {selected && (
          <button
            type="button"
            className="icon-button danger region-delete"
            title="删除区域"
            onClick={() => onDeleteRegion(region.id)}
          >
            ×
          </button>
        )}
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
            position={Position.Right}
            id={REGION_BOUNDARY_OUT_PORT}
            className="region-handle"
            isConnectableStart={false}
            style={{ pointerEvents: connectionInProgress ? "auto" : "none" }}
          />
          <Handle
            type="source"
            position={Position.Right}
            id={REGION_BOUNDARY_OUT_PORT}
            className="region-handle"
            isConnectableEnd={false}
            style={{ pointerEvents: connectionInProgress ? "none" : "auto" }}
          />
        </>
      )}
      {region.kind === "analysis" && (
        <Handle
          type="target"
          position={Position.Left}
          id={REGION_BOUNDARY_IN_PORT}
          className="region-handle"
          isConnectableStart={false}
        />
      )}
      <InputOrderPopover
        targetNodeId={region.id}
        groups={incomingGroups}
        onMoveEdgeOrder={onMoveEdgeOrder}
      />
    </div>
  );
}
