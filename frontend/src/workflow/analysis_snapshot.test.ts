import { expect, it } from "vitest";
import type { WorkflowDefinition, WorkflowEdge, WorkflowNode, WorkflowRegion } from "./types";
import { regionAnalysisSnapshot } from "./analysis_snapshot";
import { expectedInputFingerprint } from "./runner";

function buildDefinition(
  fetchParams: Record<string, unknown>,
  configParams: Record<string, unknown>,
  metaName = "主配队",
): WorkflowDefinition {
  const regions: WorkflowRegion[] = [
    {
      id: "region-1",
      kind: "configuration",
      name: "主配置",
      rect: { x: 0, y: 0, width: 800, height: 600 },
    },
    {
      id: "analysis-1",
      kind: "analysis",
      name: "分析",
      rect: { x: 0, y: 0, width: 800, height: 600 },
    },
  ];
  const nodes: WorkflowNode[] = [
    { id: "root-1", kind: "root", region_id: "region-1", position: { x: 0, y: 0 }, params: {} },
    {
      id: "meta-1",
      kind: "meta",
      region_id: "region-1",
      position: { x: 100, y: 0 },
      params: { name: metaName, description: "" },
    },
    { id: "sim-1", kind: "simulation", region_id: null, position: { x: 0, y: 300 }, params: {} },
    {
      id: "fetch-1",
      kind: "fetch",
      region_id: "analysis-1",
      position: { x: 0, y: 0 },
      params: fetchParams,
    },
    {
      id: "view-1",
      kind: "member_table",
      region_id: "analysis-1",
      position: { x: 300, y: 0 },
      params: {},
    },
    {
      id: "config-1",
      kind: "table_config",
      region_id: "analysis-1",
      position: { x: 300, y: 300 },
      params: configParams,
    },
  ];
  const edges: WorkflowEdge[] = [
    { id: "b1", source_node_id: "root-1", source_port_id: "out", target_node_id: "region-1", target_port_id: "out" },
    { id: "b2", source_node_id: "meta-1", source_port_id: "out", target_node_id: "region-1", target_port_id: "out" },
    { id: "l1", source_node_id: "region-1", source_port_id: "out", target_node_id: "sim-1", target_port_id: "in" },
    { id: "a1", source_node_id: "sim-1", source_port_id: "out", target_node_id: "analysis-1", target_port_id: "in" },
    { id: "a2", source_node_id: "analysis-1", source_port_id: "in", target_node_id: "fetch-1", target_port_id: "in" },
    { id: "a3", source_node_id: "fetch-1", source_port_id: "out", target_node_id: "config-1", target_port_id: "in" },
    { id: "a4", source_node_id: "config-1", source_port_id: "out", target_node_id: "view-1", target_port_id: "in" },
  ];
  const definition: WorkflowDefinition = {
    schema_version: 1,
    meta: { name: "t" },
    regions,
    nodes,
    edges,
    layout: {},
  };
  const fingerprint = expectedInputFingerprint(definition, "sim-1");
  return {
    ...definition,
    nodes: definition.nodes.map((node) =>
      node.id === "sim-1"
        ? {
            ...node,
            params: {
              last_sessions: ["run:1"],
              last_input_fingerprint: fingerprint,
            },
          }
        : node,
    ),
  };
}

it("相同定义产生相同快照，相关变化均改变快照", () => {
  const fetchParams = { source: "runs" };
  const configParams = { condition_columns: ["weapon"], data_columns: ["dps"] };
  const base = buildDefinition(fetchParams, configParams);

  expect(regionAnalysisSnapshot(base, "analysis-1")).toBe(
    regionAnalysisSnapshot(base, "analysis-1"),
  );

  const fetchChanged = buildDefinition({ source: "events", event_types: ["DAMAGE_RESOLVED"] }, configParams);
  expect(regionAnalysisSnapshot(fetchChanged, "analysis-1")).not.toBe(
    regionAnalysisSnapshot(base, "analysis-1"),
  );

  const configChanged = buildDefinition(fetchParams, {
    condition_columns: ["weapon"],
    data_columns: ["total_damage"],
  });
  expect(regionAnalysisSnapshot(configChanged, "analysis-1")).not.toBe(
    regionAnalysisSnapshot(base, "analysis-1"),
  );

  // 真实过期场景：配置区域已改，但模拟节点仍保留旧批次的输入指纹。
  const inputChanged: WorkflowDefinition = {
    ...base,
    nodes: base.nodes.map((node) =>
      node.id === "meta-1"
        ? { ...node, params: { ...node.params, name: "改名后的配置" } }
        : node,
    ),
  };
  expect(regionAnalysisSnapshot(inputChanged, "analysis-1")).not.toBe(
    regionAnalysisSnapshot(base, "analysis-1"),
  );
});
