import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import { nodeKindColor } from "../nodes/registry";
import { NodeEditorHost } from "../nodes/registry";
import { getNodeKindSpec } from "../../workflow/registry";
import type { WorkflowNode } from "../../workflow/types";

export type WorkflowNodeData = {
  node: WorkflowNode;
  onParamsChange: (nodeId: string, params: Record<string, unknown>) => void;
  onDeleteNode: (nodeId: string) => void;
} & Record<string, unknown>;

export function NodeCard({ data, selected }: NodeProps) {
  const { node, onParamsChange, onDeleteNode } = data as WorkflowNodeData;
  const spec = getNodeKindSpec(node.kind);

  return (
    <div className={`node-card ${selected ? "selected" : ""}`}>
      <header className="node-card-header">
        <span className="node-dot" style={{ background: nodeKindColor(node.kind) }} />
        <span className="node-title">{spec?.displayName ?? node.kind}</span>
        <button
          type="button"
          className="icon-button"
          title="删除节点"
          onClick={() => onDeleteNode(node.id)}
        >
          ×
        </button>
      </header>
      <div className="node-card-body">
        <NodeEditorHost
          kind={node.kind}
          node={node}
          onChange={(params) => onParamsChange(node.id, params)}
        />
      </div>
      <footer className="node-card-footer">
        <span className="node-path">{pathLabel(node)}</span>
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
    </div>
  );
}

function pathLabel(node: WorkflowNode): string {
  const params = node.params;
  if (typeof params.path === "string" && params.path !== "") {
    return params.path;
  }
  switch (node.kind) {
    case "character":
    case "weapon":
      return `team[${asSlot(params.slot) - 1}].${node.kind}`;
    case "artifact":
      return `team[${asSlot(params.slot) - 1}].artifacts`;
    case "target":
      return `scene.targets[${asIndex(params.index)}]`;
    case "meta":
      return "meta";
    case "input_trace":
      return "input_trace";
    case "run_options":
      return "run_options";
    case "root":
      return "根数据";
    case "simulation":
      return "输入文档集合";
    default:
      return "未设置路径";
  }
}

function asSlot(value: unknown): number {
  return typeof value === "number" && Number.isInteger(value) && value >= 1 ? value : 1;
}

function asIndex(value: unknown): number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : 0;
}
