import { useCallback, useEffect, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import type {
  Connection,
  Edge,
  Node,
  NodeTypes,
  OnConnect,
  OnEdgesDelete,
  OnNodesDelete,
  OnNodeDrag,
  OnSelectionChangeParams,
  ReactFlowInstance,
} from "@xyflow/react";
import type { EditorSelection } from "../../state/editor_state";
import {
  getNodeKindSpec,
  groupFragments,
  memberItemIds,
  singleFragment,
} from "../../workflow/registry";
import type { Diagnostic, EnumValue, WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import type { IncomingOrderGroup } from "./InputOrderPopover";
import { nodeKindColor } from "../nodes/registry";
import { NodeCard } from "./NodeCard";
import type { MemberPortInfo, WorkflowNodeData } from "./NodeCard";
import { RegionNode } from "./RegionNode";
import type { RegionNodeData } from "./RegionNode";

export interface CanvasViewProps {
  definition: WorkflowDefinition;
  selection: EditorSelection;
  diagnostics: Diagnostic[];
  dragKind: string | null;
  selectionEpoch: number;
  viewportCommand: "zoom-in" | "zoom-out" | "fit" | null;
  renameRegionRequestId: string | null;
  /** 运行进行中不在执行路径上的节点，置灰显示（决策 2.34）。 */
  dimmedNodeIds: string[];
  /** 构建限速推进中当前应用中的节点，画布高亮（决策 2.34 修订）。 */
  runningMethodNodeIds: string[];
  /** 运行期间锁定破坏性交互。 */
  interactionLocked: boolean;
  onViewportCommandHandled: () => void;
  onRenameRegionRequestHandled: () => void;
  onMoveNode: (
    nodeId: string,
    position: { x: number; y: number },
    regionId: string | null,
  ) => void;
  onMoveRegion: (regionId: string, position: { x: number; y: number }) => void;
  onResizeRegion: (
    regionId: string,
    rect: { x: number; y: number; width: number; height: number },
  ) => void;
  onRenameRegion: (regionId: string, name: string) => void;
  onValidateRegion: (regionId: string) => void;
  onRunRegion: (regionId: string) => void;
  onConnectEdge: (connection: {
    source_node_id: string;
    source_port_id: string;
    target_node_id: string;
    target_port_id: string;
  }) => void;
  onSelect: (selection: EditorSelection) => void;
  onParamsChange: (nodeId: string, params: Record<string, unknown>) => void;
  onDeleteNode: (nodeId: string) => void;
  onDeleteEdge: (edgeId: string) => void;
  onDeleteRegion: (regionId: string) => void;
  onDropObject: (
    kind: string,
    position: { x: number; y: number },
    regionId: string | null,
  ) => void;
  onMoveEdgeOrder: (
    targetNodeId: string,
    targetPortId: string,
    edgeId: string,
    direction: "up" | "down",
  ) => void;
}

interface DragPreview {
  kind: string;
  x: number;
  y: number;
  regionId: string | null;
}

interface CallbackSnapshot {
  definition: WorkflowDefinition;
  onViewportCommandHandled: CanvasViewProps["onViewportCommandHandled"];
  onRenameRegionRequestHandled: CanvasViewProps["onRenameRegionRequestHandled"];
  onMoveNode: CanvasViewProps["onMoveNode"];
  onMoveRegion: CanvasViewProps["onMoveRegion"];
  onResizeRegion: CanvasViewProps["onResizeRegion"];
  onRenameRegion: CanvasViewProps["onRenameRegion"];
  onValidateRegion: CanvasViewProps["onValidateRegion"];
  onRunRegion: CanvasViewProps["onRunRegion"];
  onConnectEdge: CanvasViewProps["onConnectEdge"];
  onSelect: CanvasViewProps["onSelect"];
  onParamsChange: CanvasViewProps["onParamsChange"];
  onDeleteNode: CanvasViewProps["onDeleteNode"];
  onDeleteEdge: CanvasViewProps["onDeleteEdge"];
  onDeleteRegion: CanvasViewProps["onDeleteRegion"];
  onMoveEdgeOrder: CanvasViewProps["onMoveEdgeOrder"];
}

const nodeTypes: NodeTypes = {
  region: RegionNode,
  workflowNode: NodeCard,
};

export function CanvasView({
  definition,
  selection,
  diagnostics,
  dragKind,
  selectionEpoch,
  viewportCommand,
  renameRegionRequestId,
  dimmedNodeIds,
  runningMethodNodeIds,
  interactionLocked,
  onViewportCommandHandled,
  onRenameRegionRequestHandled,
  onMoveNode,
  onMoveRegion,
  onResizeRegion,
  onRenameRegion,
  onValidateRegion,
  onRunRegion,
  onConnectEdge,
  onSelect,
  onParamsChange,
  onDeleteNode,
  onDeleteEdge,
  onDeleteRegion,
  onDropObject,
  onMoveEdgeOrder,
}: CanvasViewProps) {
  const latestRef = useRef<CallbackSnapshot>({
    definition,
    onViewportCommandHandled,
    onRenameRegionRequestHandled,
    onMoveNode,
    onMoveRegion,
    onResizeRegion,
    onRenameRegion,
    onValidateRegion,
    onRunRegion,
    onConnectEdge,
    onSelect,
    onParamsChange,
    onDeleteNode,
    onDeleteEdge,
    onDeleteRegion,
    onMoveEdgeOrder,
  });
  useEffect(() => {
    latestRef.current = {
      definition,
      onViewportCommandHandled,
      onRenameRegionRequestHandled,
      onMoveNode,
      onMoveRegion,
      onResizeRegion,
      onRenameRegion,
      onValidateRegion,
      onRunRegion,
      onConnectEdge,
      onSelect,
      onParamsChange,
      onDeleteNode,
      onDeleteEdge,
      onDeleteRegion,
      onMoveEdgeOrder,
    };
  });

  const rfRef = useRef<ReactFlowInstance | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [preview, setPreview] = useState<DragPreview | null>(null);
  const [highlightRegionId, setHighlightRegionId] = useState<string | null>(null);

  const visiblePreview = dragKind === null ? null : preview;
  const visibleHighlight = dragKind === null ? null : highlightRegionId;

  useEffect(() => {
    setNodes((current) =>
      mergeNodeState(
        buildNodes(
          definition,
          diagnostics,
          visibleHighlight,
          latestRef.current,
          renameRegionRequestId,
          dimmedNodeIds,
          runningMethodNodeIds,
          interactionLocked,
        ),
        current,
      ),
    );
    setEdges(buildEdges(definition));
  }, [
    definition,
    diagnostics,
    visibleHighlight,
    renameRegionRequestId,
    dimmedNodeIds,
    runningMethodNodeIds,
    interactionLocked,
    setNodes,
    setEdges,
  ]);

  useEffect(() => {
    setNodes((current) => {
      const next = current.map((node) => {
        const selected =
          selection.regions.includes(node.id) || selection.nodes.includes(node.id);
        return node.selected === selected ? node : { ...node, selected };
      });
      return next.some((node, index) => node !== current[index]) ? next : current;
    });
    setEdges((current) => {
      const next = current.map((edge) => {
        const selected = selection.edges.includes(edge.id);
        return edge.selected === selected ? edge : { ...edge, selected };
      });
      return next.some((edge, index) => edge !== current[index]) ? next : current;
    });
  }, [selection, setNodes, setEdges]);

  useEffect(() => {
    if (selectionEpoch === 0) {
      return;
    }
    setNodes((current) => {
      if (!current.some((node) => node.selected)) {
        return current;
      }
      return current.map((node) => ({ ...node, selected: false }));
    });
    setEdges((current) => {
      if (!current.some((edge) => edge.selected)) {
        return current;
      }
      return current.map((edge) => ({ ...edge, selected: false }));
    });
  }, [selectionEpoch, setNodes, setEdges]);

  useEffect(() => {
    if (viewportCommand === null) {
      return;
    }
    const instance = rfRef.current;
    if (instance === null) {
      return;
    }
    if (viewportCommand === "zoom-in") {
      instance.zoomIn();
    } else if (viewportCommand === "zoom-out") {
      instance.zoomOut();
    } else {
      instance.fitView();
    }
    latestRef.current.onViewportCommandHandled();
  }, [viewportCommand]);

  const handleInit = useCallback((instance: ReactFlowInstance) => {
    rfRef.current = instance;
  }, []);

  const handleNodeDragStop = useCallback((_: unknown, node: Node) => {
    const latest = latestRef.current;
    if (node.type === "region") {
      latest.onMoveRegion(node.id, { x: node.position.x, y: node.position.y });
      return;
    }
    const workflowNode = (node.data as WorkflowNodeData).node;
    const spec = getNodeKindSpec(workflowNode.kind);
    const parent = node.parentId === null
      ? null
      : latest.definition.regions.find((region) => region.id === node.parentId);
    const absolute = {
      x: node.position.x + (parent?.rect.x ?? 0),
      y: node.position.y + (parent?.rect.y ?? 0),
    };
    const center = {
      x: absolute.x + (node.measured?.width ?? 260) / 2,
      y: absolute.y + (node.measured?.height ?? 80) / 2,
    };
    const regionId =
      spec === null || spec.region === null
        ? null
        : compatibleRegionId(latest.definition, workflowNode.kind, center);
    latest.onMoveNode(node.id, absolute, regionId);
  }, []);

  const handleConnect: OnConnect = useCallback((connection: Connection) => {
    if (connection.source === null || connection.target === null) {
      return;
    }
    latestRef.current.onConnectEdge({
      source_node_id: connection.source,
      source_port_id: connection.sourceHandle ?? "out",
      target_node_id: connection.target,
      target_port_id: connection.targetHandle ?? "in",
    });
  }, []);

  const handleSelectionChange = useCallback((params: OnSelectionChangeParams) => {
    latestRef.current.onSelect({
      regions: params.nodes.filter((node) => node.type === "region").map((node) => node.id),
      nodes: params.nodes.filter((node) => node.type !== "region").map((node) => node.id),
      edges: params.edges.map((edge) => edge.id),
    });
  }, []);

  const handleNodesDelete: OnNodesDelete = useCallback((deleted) => {
    const { onDeleteRegion, onDeleteNode } = latestRef.current;
    for (const node of deleted) {
      if (node.type === "region") {
        onDeleteRegion(node.id);
      } else {
        onDeleteNode(node.id);
      }
    }
  }, []);

  const handleEdgesDelete: OnEdgesDelete = useCallback((deleted) => {
    const onDeleteEdge = latestRef.current.onDeleteEdge;
    for (const edge of deleted) {
      onDeleteEdge(edge.id);
    }
  }, []);

  function handleDragOver(event: React.DragEvent<HTMLDivElement>) {
    if (dragKind === null) {
      return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    const point = rfRef.current?.screenToFlowPosition({ x: event.clientX, y: event.clientY }) ?? {
      x: event.clientX,
      y: event.clientY,
    };
    const regionId = compatibleRegionId(definition, dragKind, point);
    setPreview({ kind: dragKind, x: event.clientX, y: event.clientY, regionId });
    setHighlightRegionId(regionId);
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    if (dragKind === null) {
      return;
    }
    event.preventDefault();
    const point = rfRef.current?.screenToFlowPosition({ x: event.clientX, y: event.clientY }) ?? {
      x: event.clientX,
      y: event.clientY,
    };
    onDropObject(dragKind, point, compatibleRegionId(definition, dragKind, point));
    setPreview(null);
    setHighlightRegionId(null);
  }

  function handleDragEnd() {
    setPreview(null);
    setHighlightRegionId(null);
  }

  return (
    <div
      className="canvas-viewport"
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onDragEnd={handleDragEnd}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onInit={handleInit}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={handleNodeDragStop as OnNodeDrag}
        onConnect={handleConnect}
        onSelectionChange={handleSelectionChange}
        onNodesDelete={handleNodesDelete}
        onEdgesDelete={handleEdgesDelete}
        deleteKeyCode={null}
        fitView
        minZoom={0.25}
        maxZoom={4}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1.5} />
        <Controls
          position="bottom-right"
          showInteractive={false}
          style={{ right: 220 }}
        />
        <MiniMap
          position="bottom-right"
          pannable
          zoomable
          nodeColor={(node) =>
            node.type === "region" ? "#2563eb" : "#64748b"
          }
        />
      </ReactFlow>
      {visiblePreview !== null && (
        <div
          className={`drag-ghost ${visiblePreview.kind !== "region" && visiblePreview.regionId === null ? "draft" : ""}`}
          style={{ left: visiblePreview.x - 12, top: visiblePreview.y - 12 }}
        >
          <span
            className="node-dot"
            style={{ background: nodeKindColor(visiblePreview.kind) }}
          />
          <span className="drag-ghost-label">
            {visiblePreview.kind === "region"
              ? "配置区域"
              : (getNodeKindSpec(visiblePreview.kind)?.displayName ?? visiblePreview.kind)}
          </span>
          {visiblePreview.kind !== "region" && visiblePreview.regionId === null && (
            <span className="draft-badge">草稿</span>
          )}
        </div>
      )}
    </div>
  );
}

function buildNodes(
  definition: WorkflowDefinition,
  diagnostics: Diagnostic[],
  highlightRegionId: string | null,
  callbacks: CallbackSnapshot,
  renameRegionRequestId: string | null,
  dimmedNodeIds: string[],
  runningMethodNodeIds: string[],
  interactionLocked: boolean,
): Node[] {
  const incoming = incomingGroupsByTarget(definition);
  const dimmed = new Set(dimmedNodeIds);
  const running = new Set(runningMethodNodeIds);
  const nodes: Node[] = [];
  for (const region of definition.regions) {
    const data: RegionNodeData = {
      region,
      onDeleteRegion: callbacks.onDeleteRegion,
      onRenameRegion: callbacks.onRenameRegion,
      onResizeRegion: callbacks.onResizeRegion,
      onMoveEdgeOrder: callbacks.onMoveEdgeOrder,
      onValidateRegion: callbacks.onValidateRegion,
      onRunRegion: callbacks.onRunRegion,
      interactionLocked,
      incomingGroups: incoming.get(region.id) ?? [],
      dropTarget: highlightRegionId === region.id,
      renameRequested: region.id === renameRegionRequestId,
      onRenameRequestHandled: callbacks.onRenameRegionRequestHandled,
    };
    nodes.push({
      id: region.id,
      type: "region",
      position: { x: region.rect.x, y: region.rect.y },
      width: region.rect.width,
      height: region.rect.height,
      data,
      zIndex: 0,
      draggable: true,
      selected: false,
    });
  }
  for (const node of definition.nodes) {
    const parent =
      node.region_id === null
        ? null
        : definition.regions.find((region) => region.id === node.region_id);
    const position =
      parent == null
        ? node.position
        : {
            x: node.position.x - parent.rect.x,
            y: node.position.y - parent.rect.y,
          };
    const data: WorkflowNodeData = {
      node,
      onParamsChange: callbacks.onParamsChange,
      onDeleteNode: callbacks.onDeleteNode,
      onMoveEdgeOrder: callbacks.onMoveEdgeOrder,
      incomingGroups: incoming.get(node.id) ?? [],
      memberPorts: buildMemberPorts(node, definition),
      groupCount:
        node.kind === "enum" || node.kind === "range" ? memberItemIds(node).length : 0,
      diagnostics,
      dimmed: dimmed.has(node.id),
      stepRunning: running.has(node.id),
      interactionLocked,
    };
    nodes.push({
      id: node.id,
      type: "workflowNode",
      position,
      parentId: parent?.id,
      data,
      zIndex: 1,
      selected: false,
    });
  }
  return nodes;
}

/**
 * 定义同步时保留 React Flow 已测量的尺寸与当前选中/拖拽状态，
 * 避免重建节点数组后重新测量并触发受控节点同步循环。
 */
function mergeNodeState(next: Node[], current: Node[]): Node[] {
  const currentById = new Map(current.map((node) => [node.id, node]));
  return next.map((node) => {
    const existing = currentById.get(node.id);
    if (existing === undefined) {
      return node;
    }
    const measured =
      node.width !== undefined && node.height !== undefined
        ? { width: node.width, height: node.height }
        : existing.measured;
    return {
      ...node,
      measured,
      selected: existing.selected,
      dragging: existing.dragging,
    };
  });
}

function buildEdges(definition: WorkflowDefinition): Edge[] {
  return definition.edges.map((edge) => {
    const sourceNode = definition.nodes.find((node) => node.id === edge.source_node_id);
    const groupCount =
      sourceNode !== undefined &&
      (sourceNode.kind === "enum" || sourceNode.kind === "range") &&
      edge.source_port_id === "out"
        ? memberItemIds(sourceNode).length
        : 0;
    return {
      id: edge.id,
      source: edge.source_node_id,
      sourceHandle: edge.source_port_id,
      target: edge.target_node_id,
      targetHandle: edge.target_port_id,
      markerEnd: { type: MarkerType.ArrowClosed },
      selected: false,
      label: groupCount > 0 ? `×${groupCount}` : undefined,
      labelStyle:
        groupCount > 0
          ? { fill: "#94a3b8", fontSize: 10, fontFamily: "ui-monospace, Consolas, monospace" }
          : undefined,
    };
  });
}

function buildMemberPorts(node: WorkflowNode, definition: WorkflowDefinition): MemberPortInfo[] {
  if (node.kind !== "enum" && node.kind !== "range") {
    return [];
  }
  const connectedPorts = new Set(
    definition.edges
      .filter((edge) => edge.source_node_id === node.id)
      .map((edge) => edge.source_port_id),
  );
  if (node.kind === "enum") {
    const values = Array.isArray(node.params.values) ? (node.params.values as EnumValue[]) : [];
    return values.map((item) => ({
      portId: `out:${item.item_id}`,
      itemId: item.item_id,
      label: item.label ?? item.item_id,
      connected: connectedPorts.has(`out:${item.item_id}`),
    }));
  }
  return groupFragments(node).map((fragment) => ({
    portId: `out:${fragment.item_id}`,
    itemId: fragment.item_id,
    label: String(fragment.value),
    connected: connectedPorts.has(`out:${fragment.item_id}`),
  }));
}

function incomingGroupsByTarget(definition: WorkflowDefinition): Map<string, IncomingOrderGroup[]> {
  const nodeById = new Map(definition.nodes.map((node) => [node.id, node]));
  const result = new Map<string, IncomingOrderGroup[]>();
  for (const edge of definition.edges) {
    const source = nodeById.get(edge.source_node_id);
    if (source === undefined) {
      continue;
    }
    const groups = result.get(edge.target_node_id) ?? [];
    let group = groups.find((item) => item.portId === edge.target_port_id);
    if (group === undefined) {
      group = { portId: edge.target_port_id, items: [] };
      groups.push(group);
      result.set(edge.target_node_id, groups);
    }
    group.items.push({
      edgeId: edge.id,
      label: getNodeKindSpec(source.kind)?.displayName ?? source.kind,
      path: fragmentPath(source, definition),
    });
  }
  return result;
}

function fragmentPath(
  node: WorkflowNode,
  definition: WorkflowDefinition,
): string | null {
  const spec = getNodeKindSpec(node.kind);
  if (spec === null) {
    return null;
  }
  const variants = groupFragments(node);
  if (variants.length > 0) {
    return variants[0].path;
  }
  return singleFragment(node, definition)?.path ?? null;
}

function compatibleRegionId(
  definition: WorkflowDefinition,
  kind: string,
  point: { x: number; y: number },
): string | null {
  if (kind === "region") {
    return null;
  }
  const spec = getNodeKindSpec(kind);
  if (spec === null || spec.region === null) {
    return null;
  }
  let match: string | null = null;
  for (const region of definition.regions) {
    if (region.kind !== spec.region) {
      continue;
    }
    const inside =
      point.x >= region.rect.x &&
      point.x <= region.rect.x + region.rect.width &&
      point.y >= region.rect.y &&
      point.y <= region.rect.y + region.rect.height;
    if (inside) {
      match = region.id;
    }
  }
  return match;
}
