import { describe, expect, it } from "vitest";
import type { WorkflowDefinition, WorkflowNode } from "../workflow/types";
import {
  backfillPayloadEventTypes,
  cloneEditorState,
  definitionToEditorState,
  editorStateToDefinition,
} from "./converters";
import { addNode, addRegion } from "./editor_state";

function sampleDefinition(): WorkflowDefinition {
  return {
    schema_version: 1,
    meta: { name: "样本" },
    regions: [],
    nodes: [],
    edges: [],
    layout: {},
  };
}

describe("converters", () => {
  it("definition 与 editor state 双向转换且互不影响", () => {
    const definition = sampleDefinition();
    const state = definitionToEditorState(definition);
    expect(state.dirty).toBe(false);
    expect(state.selection).toEqual({ regions: [], nodes: [], edges: [] });

    definition.meta.name = "外部修改";
    expect(state.definition.meta.name).toBe("样本");

    state.definition.meta.name = "状态修改";
    const roundTrip = editorStateToDefinition(state);
    expect(roundTrip.meta.name).toBe("状态修改");
    expect(state.definition.meta.name).toBe("状态修改");

    roundTrip.meta.name = "回写修改";
    expect(state.definition.meta.name).toBe("状态修改");
  });

  it("clone 隔离编辑状态", () => {
    let state = definitionToEditorState(sampleDefinition());
    state = addRegion(state, "configuration", "主配置", { x: 0, y: 0, width: 800, height: 600 });
    state = addNode(state, "character", { x: 0, y: 0 }, "region-1");

    const clone = cloneEditorState(state);
    clone.definition.nodes[0].params.asset = "character:other";
    clone.selection.nodes.push("node-1");

    expect(state.definition.nodes[0].params.asset).toBe("");
    expect(state.selection.nodes).toEqual([]);
    expect(clone.dirty).toBe(state.dirty);
  });

  it("存量 fetch_runs / fetch_events 迁移为 fetch + source", () => {
    const legacy = (id: string, kind: string, params: Record<string, unknown>): WorkflowNode =>
      ({
        id,
        kind,
        region_id: null,
        position: { x: 0, y: 0 },
        params,
      }) as WorkflowNode;
    const definition: WorkflowDefinition = {
      schema_version: 1,
      meta: { name: "迁移" },
      regions: [],
      nodes: [
        legacy("runs1", "fetch_runs", {
          snapshot_columns: [{ path: "team.0.character.asset_key", name: "char", type: "string" }],
        }),
        legacy("ev1", "fetch_events", { event_types: ["DAMAGE_RESOLVED"] }),
      ],
      edges: [
        {
          id: "e1",
          source_node_id: "runs1",
          source_port_id: "out",
          target_node_id: "ev1",
          target_port_id: "in",
        },
      ],
      layout: {},
    };

    const state = definitionToEditorState(definition);

    expect(state.definition.nodes[0]).toMatchObject({
      kind: "fetch",
      params: {
        source: "runs",
        snapshot_columns: [{ path: "team.0.character.asset_key", name: "char", type: "string" }],
      },
    });
    expect(state.definition.nodes[1]).toMatchObject({
      kind: "fetch",
      params: { source: "events", event_types: ["DAMAGE_RESOLVED"] },
    });
    expect(state.definition.edges).toHaveLength(1);
  });

  it("旧 fetch 的帧范围参数加载时丢弃", () => {
    const definition: WorkflowDefinition = {
      ...sampleDefinition(),
      nodes: [
        {
          id: "ev1",
          kind: "fetch",
          region_id: "analysis-1",
          position: { x: 0, y: 0 },
          params: {
            source: "events",
            event_types: [],
            frame_min: 0,
            frame_max: 18000,
            payload_columns: [],
          },
        },
      ],
    };

    const state = definitionToEditorState(definition);

    expect(state.definition.nodes[0].params).not.toHaveProperty("frame_min");
    expect(state.definition.nodes[0].params).not.toHaveProperty("frame_max");
  });

  it("旧 table_config 的 width_mode 参数加载时丢弃", () => {
    const definition: WorkflowDefinition = {
      ...sampleDefinition(),
      nodes: [
        {
          id: "config-1",
          kind: "table_config",
          region_id: "analysis-1",
          position: { x: 0, y: 0 },
          params: {
            condition_columns: ["char_key"],
            data_columns: [],
            width_mode: "fixed",
          },
        },
      ],
    };

    const state = definitionToEditorState(definition);

    expect(state.definition.nodes[0].params).not.toHaveProperty("width_mode");
    expect(state.definition.nodes[0].params.condition_columns).toEqual(["char_key"]);
  });

  it("旧表格 auto 宽度快照随单模式化丢弃，fixed 宽度保留", () => {
    const definition: WorkflowDefinition = {
      ...sampleDefinition(),
      regions: [
        {
          id: "analysis-1",
          kind: "analysis",
          name: "分析",
          rect: { x: 0, y: 0, width: 800, height: 600 },
        },
      ],
      nodes: [
        {
          id: "auto-config",
          kind: "table_config",
          region_id: "analysis-1",
          position: { x: 0, y: 0 },
          params: { condition_columns: ["c"], data_columns: [], width_mode: "auto" },
        },
        {
          id: "auto-view",
          kind: "member_table",
          region_id: "analysis-1",
          position: { x: 0, y: 0 },
          params: {},
          size: { width: 960, height: 420 },
        },
        {
          id: "fixed-config",
          kind: "table_config",
          region_id: "analysis-1",
          position: { x: 0, y: 0 },
          params: { condition_columns: ["c"], data_columns: [], width_mode: "fixed" },
        },
        {
          id: "fixed-view",
          kind: "member_table",
          region_id: "analysis-1",
          position: { x: 0, y: 0 },
          params: {},
          size: { width: 1100, height: 400 },
        },
      ],
      edges: [
        {
          id: "e1",
          source_node_id: "auto-config",
          source_port_id: "out",
          target_node_id: "auto-view",
          target_port_id: "config",
        },
        {
          id: "e2",
          source_node_id: "fixed-config",
          source_port_id: "out",
          target_node_id: "fixed-view",
          target_port_id: "config",
        },
      ],
      layout: {},
    };

    const state = definitionToEditorState(definition);
    const byId = new Map(state.definition.nodes.map((node) => [node.id, node]));

    expect(byId.get("auto-view")?.size).toEqual({ height: 420 });
    expect(byId.get("fixed-view")?.size).toEqual({ width: 1100, height: 400 });
    expect(byId.get("auto-config")?.params).not.toHaveProperty("width_mode");
    expect(byId.get("fixed-config")?.params).not.toHaveProperty("width_mode");
  });

  it("载荷提取列 event_type 按唯一路径回填，歧义与无匹配保持缺省", () => {
    const definition: WorkflowDefinition = {
      ...sampleDefinition(),
      nodes: [
        {
          id: "ev1",
          kind: "fetch",
          region_id: "analysis-1",
          position: { x: 0, y: 0 },
          params: {
            source: "events",
            payload_columns: [
              { path: "result.final_damage", name: "damage", type: "float" },
              { path: "result.source_ref", name: "src", type: "string" },
              { path: "custom.value", name: "custom", type: "float" },
            ],
          },
        },
      ],
    };
    const eventTypes = [
      {
        name: "DAMAGE_RESOLVED",
        fields: [{ path: "result.final_damage" }, { path: "result.source_ref" }],
      },
      {
        name: "HEALING_RESOLVED",
        fields: [{ path: "result.final_healing" }, { path: "result.source_ref" }],
      },
    ];

    const next = backfillPayloadEventTypes(definition, eventTypes);
    const rows = next.nodes[0].params.payload_columns as Record<string, unknown>[];

    expect(next).not.toBe(definition);
    expect(rows[0].event_type).toBe("DAMAGE_RESOLVED");
    expect(rows[1].event_type).toBeUndefined();
    expect(rows[2].event_type).toBeUndefined();
  });

  it("无需回填时返回原定义引用", () => {
    const definition: WorkflowDefinition = {
      ...sampleDefinition(),
      nodes: [
        {
          id: "ev1",
          kind: "fetch",
          region_id: "analysis-1",
          position: { x: 0, y: 0 },
          params: {
            source: "events",
            payload_columns: [
              {
                event_type: "DAMAGE_RESOLVED",
                path: "result.final_damage",
                name: "damage",
                type: "float",
              },
            ],
          },
        },
      ],
    };

    expect(backfillPayloadEventTypes(definition, [])).toBe(definition);
  });
});
