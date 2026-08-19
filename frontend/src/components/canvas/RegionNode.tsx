import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import { COLORS } from "../../theme/tokens";
import type { WorkflowRegion } from "../../workflow/types";

export type RegionNodeData = {
  region: WorkflowRegion;
} & Record<string, unknown>;

export function RegionNode({ data, selected, width, height }: NodeProps) {
  const region = (data as RegionNodeData).region;
  const borderColor =
    region.kind === "configuration" ? COLORS.region.configuration : COLORS.region.analysis;

  return (
    <div
      className={`region-node ${selected ? "selected" : ""}`}
      style={{
        width: width ?? region.rect.width,
        height: height ?? region.rect.height,
        borderColor,
      }}
    >
      <header className="region-header" style={{ borderColor }}>
        <span className="region-kind">
          {region.kind === "configuration" ? "配置区域" : "分析区域"}
        </span>
        <span className="region-name">{region.name}</span>
      </header>
      <Handle
        type="target"
        position={Position.Left}
        id="in"
        className="region-handle"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="out"
        className="region-handle"
      />
    </div>
  );
}
