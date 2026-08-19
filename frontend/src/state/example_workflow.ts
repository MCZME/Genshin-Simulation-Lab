import type { WorkflowDefinition, WorkflowEdge, WorkflowNode, WorkflowRegion } from "../workflow/types";

/**
 * 第一条纵向链路的示例工作流：
 * 根节点 → 角色 → 目标 → 区间(等级) → 枚举(max_frames) → 按键轨迹 → 模拟桥。
 */
export function createExampleDefinition(): WorkflowDefinition {
  const regions: WorkflowRegion[] = [
    {
      id: "region-1",
      kind: "configuration",
      name: "主配置",
      rect: { x: 40, y: 40, width: 880, height: 440 },
    },
  ];
  const nodes: WorkflowNode[] = [
    {
      id: "node-root",
      kind: "root",
      region_id: "region-1",
      position: { x: 40, y: 60 },
      params: {},
    },
    {
      id: "node-character",
      kind: "character",
      region_id: "region-1",
      position: { x: 40, y: 180 },
      params: {
        slot: 1,
        asset: "character:10000014",
        level: 90,
        constellation: 0,
        talents: { normal_attack: 1, elemental_skill: 1, elemental_burst: 1 },
      },
    },
    {
      id: "node-target",
      kind: "target",
      region_id: "region-1",
      position: { x: 280, y: 60 },
      params: { index: 0, id: "target_0", level: 90 },
    },
    {
      id: "node-range",
      kind: "range",
      region_id: "region-1",
      position: { x: 280, y: 200 },
      params: { path: "scene.targets[0].level", start: 1, end: 10, step: 3, label: null },
    },
    {
      id: "node-enum",
      kind: "enum",
      region_id: "region-1",
      position: { x: 560, y: 60 },
      params: {
        path: "run_options.max_frames",
        value_type: "number",
        values: [
          { item_id: "e-1", value: 60, label: "60 帧" },
          { item_id: "e-2", value: 120, label: "120 帧" },
        ],
      },
    },
    {
      id: "node-input-trace",
      kind: "input_trace",
      region_id: "region-1",
      position: { x: 560, y: 220 },
      params: {
        items: [
          { frame: 1, events: [{ key: "mouse.left", phase: "press" }] },
          { frame: 2, events: [{ key: "mouse.left", phase: "release" }] },
        ],
      },
    },
    {
      id: "node-sim",
      kind: "simulation",
      region_id: null,
      position: { x: 420, y: 560 },
      params: {},
    },
  ];
  const edges: WorkflowEdge[] = [
    { id: "edge-1", source_node_id: "node-root", source_port_id: "out", target_node_id: "region-1", target_port_id: "in" },
    { id: "edge-2", source_node_id: "node-character", source_port_id: "out", target_node_id: "region-1", target_port_id: "in" },
    { id: "edge-3", source_node_id: "node-target", source_port_id: "out", target_node_id: "region-1", target_port_id: "in" },
    { id: "edge-4", source_node_id: "node-range", source_port_id: "out", target_node_id: "region-1", target_port_id: "in" },
    { id: "edge-5", source_node_id: "node-enum", source_port_id: "out", target_node_id: "region-1", target_port_id: "in" },
    { id: "edge-6", source_node_id: "node-input-trace", source_port_id: "out", target_node_id: "region-1", target_port_id: "in" },
    { id: "edge-7", source_node_id: "region-1", source_port_id: "out", target_node_id: "node-sim", target_port_id: "in" },
  ];
  return {
    schema_version: 1,
    meta: { name: "示例工作流" },
    regions,
    nodes,
    edges,
    layout: {},
  };
}
