import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import { useState } from "react";
import { InputOrderPopover } from "./InputOrderPopover";
import type { IncomingOrderGroup } from "./InputOrderPopover";
import { nodeKindColor } from "../nodes/registry";
import { NodeEditorHost } from "../nodes/registry";
import { getNodeKindSpec } from "../../workflow/registry";
import type { WorkflowNode } from "../../workflow/types";
import type { Diagnostic } from "../../workflow/types";

export type WorkflowNodeData = {
  node: WorkflowNode;
  onParamsChange: (nodeId: string, params: Record<string, unknown>) => void;
  onDeleteNode: (nodeId: string) => void;
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
    onParamsChange,
    onDeleteNode,
    onMoveEdgeOrder,
    incomingGroups,
    memberPorts,
    groupCount,
    diagnostics,
  } = data as WorkflowNodeData;
  const spec = getNodeKindSpec(node.kind);
  const isDraft = node.region_id === null && spec?.region !== "bridge";
  const fieldErrors = collectFieldErrors(diagnostics, node.id);
  const [membersOpen, setMembersOpen] = useState(false);
  const hasMemberPorts = memberPorts.length > 0;
  const connectedMembers = memberPorts.filter((port) => port.connected);

  return (
    <div
      className={`node-card ${node.kind === "input_trace" ? "node-card-trace" : ""} ${selected ? "selected" : ""} ${isDraft ? "draft" : ""}`}
    >
      <header className="node-card-header">
        <span className="node-dot" style={{ background: nodeKindColor(node.kind) }} />
        <span className="node-title">{spec?.displayName ?? node.kind}</span>
        {isDraft && <span className="draft-badge">草稿</span>}
        <button
          type="button"
          className="icon-button danger"
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
          fieldErrors={fieldErrors}
          onChange={(params) => onParamsChange(node.id, params)}
        />
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
    </div>
  );
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
