import { useEffect, useRef } from "react";
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
} from "@xyflow/react";
import type { EditorSelection } from "../../state/editor_state";
import type { WorkflowDefinition } from "../../workflow/types";
import { NodeCard } from "./NodeCard";
import type { WorkflowNodeData } from "./NodeCard";
import { RegionNode } from "./RegionNode";
import type { RegionNodeData } from "./RegionNode";

export interface CanvasViewProps {
  definition: WorkflowDefinition;
  onMoveNode: (nodeId: string, position: { x: number; y: number }) => void;
  onMoveRegion: (regionId: string, position: { x: number; y: number }) => void;
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
}

const nodeTypes: NodeTypes = {
  region: RegionNode,
  workflowNode: NodeCard,
};

export function CanvasView({
  definition,
  onMoveNode,
  onMoveRegion,
  onConnectEdge,
  onSelect,
  onParamsChange,
  onDeleteNode,
  onDeleteEdge,
  onDeleteRegion,
}: CanvasViewProps) {
  const callbacksRef = useRef({
    onMoveNode,
    onMoveRegion,
    onConnectEdge,
    onParamsChange,
    onDeleteNode,
  });
  useEffect(() => {
    callbacksRef.current = {
      onMoveNode,
      onMoveRegion,
      onConnectEdge,
      onParamsChange,
      onDeleteNode,
    };
  });

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    setNodes(buildNodes(definition, callbacksRef.current));
    setEdges(buildEdges(definition));
  }, [definition, setNodes, setEdges]);

  function handleNodeDragStop(_: unknown, node: Node) {
    if (node.type === "region") {
      onMoveRegion(node.id, { x: node.position.x, y: node.position.y });
      return;
    }
    onMoveNode(node.id, { x: node.position.x, y: node.position.y });
  }

  const handleConnect: OnConnect = (connection: Connection) => {
    if (connection.source === null || connection.target === null) {
      return;
    }
    onConnectEdge({
      source_node_id: connection.source,
      source_port_id: connection.sourceHandle ?? "out",
      target_node_id: connection.target,
      target_port_id: connection.targetHandle ?? "in",
    });
  };

  function handleSelectionChange(params: OnSelectionChangeParams) {
    onSelect({
      regions: params.nodes.filter((node) => node.type === "region").map((node) => node.id),
      nodes: params.nodes.filter((node) => node.type !== "region").map((node) => node.id),
      edges: params.edges.map((edge) => edge.id),
    });
  }

  const handleNodesDelete: OnNodesDelete = (deleted) => {
    for (const node of deleted) {
      if (node.type === "region") {
        onDeleteRegion(node.id);
      } else {
        onDeleteNode(node.id);
      }
    }
  };

  const handleEdgesDelete: OnEdgesDelete = (deleted) => {
    for (const edge of deleted) {
      onDeleteEdge(edge.id);
    }
  };

  return (
    <div className="canvas-viewport">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={handleNodeDragStop as OnNodeDrag}
        onConnect={handleConnect}
        onSelectionChange={handleSelectionChange}
        onNodesDelete={handleNodesDelete}
        onEdgesDelete={handleEdgesDelete}
        deleteKeyCode={["Backspace", "Delete"]}
        fitView
        minZoom={0.25}
        maxZoom={4}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1.5} />
        <Controls position="bottom-right" />
        <MiniMap
          position="bottom-right"
          pannable
          zoomable
          nodeColor={(node) =>
            node.type === "region" ? "#2563eb" : "#64748b"
          }
        />
      </ReactFlow>
    </div>
  );
}

function buildNodes(
  definition: WorkflowDefinition,
  callbacks: {
    onMoveNode: CanvasViewProps["onMoveNode"];
    onMoveRegion: CanvasViewProps["onMoveRegion"];
    onConnectEdge: CanvasViewProps["onConnectEdge"];
    onParamsChange: CanvasViewProps["onParamsChange"];
    onDeleteNode: CanvasViewProps["onDeleteNode"];
  },
): Node[] {
  const nodes: Node[] = [];
  for (const region of definition.regions) {
    const data: RegionNodeData = {
      region,
    };
    nodes.push({
      id: region.id,
      type: "region",
      position: { x: region.rect.x, y: region.rect.y },
      width: region.rect.width,
      height: region.rect.height,
      data,
      zIndex: 0,
    });
  }
  for (const node of definition.nodes) {
    const data: WorkflowNodeData = {
      node,
      onParamsChange: callbacks.onParamsChange,
      onDeleteNode: callbacks.onDeleteNode,
    };
    nodes.push({
      id: node.id,
      type: "workflowNode",
      position: { x: node.position.x, y: node.position.y },
      data,
      zIndex: 1,
    });
  }
  return nodes;
}

function buildEdges(
  definition: WorkflowDefinition,
): Edge[] {
  return definition.edges.map((edge) => ({
    id: edge.id,
    source: edge.source_node_id,
    sourceHandle: edge.source_port_id,
    target: edge.target_node_id,
    targetHandle: edge.target_port_id,
    markerEnd: { type: MarkerType.ArrowClosed },
  }));
}
