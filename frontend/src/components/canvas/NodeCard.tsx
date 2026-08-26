import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import { useState } from "react";
import { InputOrderPopover } from "./InputOrderPopover";
import type { IncomingOrderGroup } from "./InputOrderPopover";
import { nodeKindColor } from "../nodes/registry";
import { NodeEditorHost } from "../nodes/registry";
import { useAnalysisSchemaCatalog } from "../analysis_context";
import { AnalysisViewBody } from "../nodes/views";
import { getNodeKindSpec } from "../../workflow/registry";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
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
  } = data as WorkflowNodeData;
  const spec = getNodeKindSpec(node.kind);
  const isDraft = node.region_id === null && spec?.region !== null;
  const catalog = useAnalysisSchemaCatalog();
  const fieldErrors = collectFieldErrors(diagnostics, node.id);
  const [membersOpen, setMembersOpen] = useState(false);
  const hasMemberPorts = memberPorts.length > 0;
  const connectedMembers = memberPorts.filter((port) => port.connected);

  return (
    <div
      className={`node-card ${isAnalysisView(node.kind) ? "node-card-view" : ""} ${node.kind === "input_trace" ? "node-card-trace" : ""} ${node.kind === "fetch" ? "node-card-fetch" : ""} ${node.kind === "filter" ? "node-card-filter" : ""} ${node.kind === "aggregate" ? "node-card-aggregate" : ""} ${node.kind === "project" ? "node-card-project" : ""} ${node.kind === "sort" ? "node-card-sort" : ""} ${node.kind === "join" ? "node-card-join" : ""} ${selected ? "selected" : ""} ${isDraft ? "draft" : ""} ${dimmed ? "dimmed" : ""} ${stepRunning ? "step-running" : ""}`}
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
          />
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
    </div>
  );
}

function isAnalysisView(kind: string): boolean {
  return kind === "member_table" || kind === "timeline" || kind === "pie" || kind === "bar";
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
