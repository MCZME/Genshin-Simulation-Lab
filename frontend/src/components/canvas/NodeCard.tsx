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
    <div className={`node-card ${selected ? "selected" : ""} ${isDraft ? "draft" : ""}`}>
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
        <PathEditor
          node={node}
          editable={spec !== null && spec.kind !== "enum" && spec.kind !== "range"}
          onChange={(params) => onParamsChange(node.id, params)}
        />
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

function PathEditor({
  node,
  editable,
  onChange,
}: {
  node: WorkflowNode;
  editable: boolean;
  onChange: (params: Record<string, unknown>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  if (!editable) {
    return <span className="node-path">{pathLabel(node)}</span>;
  }
  if (editing) {
    function commit() {
      const value = draft.trim();
      const next = { ...node.params };
      if (value === "") {
        delete next.path;
      } else {
        next.path = value;
      }
      onChange(next);
      setEditing(false);
    }
    return (
      <input
        className="node-path field field-mono"
        autoFocus
        value={draft}
        spellCheck={false}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            commit();
          } else if (event.key === "Escape") {
            setEditing(false);
          }
        }}
      />
    );
  }
  return (
    <span
      className="node-path editable"
      title="点击编辑路径"
      onClick={() => {
        setDraft(pathLabel(node));
        setEditing(true);
      }}
    >
      {pathLabel(node)}
    </span>
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
