import { describe, expect, it } from "vitest";
import {
  addEdge,
  addNode,
  addRegion,
  createEmptyEditorState,
  deleteEdge,
  deleteNode,
  deleteRegion,
  markSaved,
  moveNode,
  renameRegion,
  renameWorkflow,
  setNodeParams,
  setNodeRegion,
  setSelection,
  updateRegionRect,
} from "./editor_state";

describe("editor state mutations", () => {
  it("创建空编辑状态", () => {
    const state = createEmptyEditorState("新工作流");
    expect(state.definition.schema_version).toBe(1);
    expect(state.definition.meta.name).toBe("新工作流");
    expect(state.definition.regions).toEqual([]);
    expect(state.definition.nodes).toEqual([]);
    expect(state.definition.edges).toEqual([]);
    expect(state.dirty).toBe(false);
  });

  it("添加区域和节点并标记未保存", () => {
    let state = createEmptyEditorState();
    state = addRegion(state, "configuration", "主配置", { x: 0, y: 0, width: 800, height: 600 });
    state = addNode(state, "character", { x: 10, y: 20 }, "region-1");

    expect(state.dirty).toBe(true);
    expect(state.definition.regions[0].id).toBe("region-1");
    const node = state.definition.nodes[0];
    expect(node.id).toBe("node-1");
    expect(node.kind).toBe("character");
    expect(node.region_id).toBe("region-1");
    expect(node.params.slot).toBe(1);
    expect(node.params.level).toBe(90);
  });

  it("未知节点类型不会创建节点", () => {
    const state = addNode(createEmptyEditorState(), "bogus", { x: 0, y: 0 }, null);
    expect(state.definition.nodes).toEqual([]);
    expect(state.dirty).toBe(false);
  });

  it("移动节点与更新参数", () => {
    let state = createEmptyEditorState();
    state = addRegion(state, "configuration", "主配置", { x: 0, y: 0, width: 800, height: 600 });
    state = addNode(state, "range", { x: 0, y: 0 }, "region-1");
    const nodeId = state.definition.nodes[0].id;

    state = moveNode(state, nodeId, { x: 100, y: 200 });
    expect(state.definition.nodes[0].position).toEqual({ x: 100, y: 200 });

    state = setNodeParams(state, nodeId, { path: "a.b", start: 1, end: 5, step: 1 });
    expect(state.definition.nodes[0].params).toEqual({ path: "a.b", start: 1, end: 5, step: 1 });
  });

  it("连线去重并生成稳定 id", () => {
    let state = createEmptyEditorState();
    state = addRegion(state, "configuration", "主配置", { x: 0, y: 0, width: 800, height: 600 });
    state = addNode(state, "character", { x: 0, y: 0 }, "region-1");
    state = addNode(state, "simulation", { x: 0, y: 0 }, null);
    const connection = {
      source_node_id: "node-1",
      source_port_id: "out",
      target_node_id: "region-1",
      target_port_id: "in",
    };
    state = addEdge(state, connection);
    state = addEdge(state, connection);
    expect(state.definition.edges).toHaveLength(1);
    expect(state.definition.edges[0].id).toBe("edge-1");
  });

  it("删除节点级联删除关联连线", () => {
    let state = createEmptyEditorState();
    state = addRegion(state, "configuration", "主配置", { x: 0, y: 0, width: 800, height: 600 });
    state = addNode(state, "character", { x: 0, y: 0 }, "region-1");
    state = addNode(state, "simulation", { x: 0, y: 0 }, null);
    state = addEdge(state, {
      source_node_id: "node-1",
      source_port_id: "out",
      target_node_id: "region-1",
      target_port_id: "in",
    });
    state = addEdge(state, {
      source_node_id: "region-1",
      source_port_id: "out",
      target_node_id: "node-2",
      target_port_id: "in",
    });

    state = deleteNode(state, "node-1");
    expect(state.definition.nodes).toHaveLength(1);
    expect(state.definition.edges.map((edge) => edge.id)).toEqual(["edge-2"]);

    state = deleteEdge(state, "edge-2");
    expect(state.definition.edges).toEqual([]);
  });

  it("删除区域时节点转为游离草稿并移除边界连线", () => {
    let state = createEmptyEditorState();
    state = addRegion(state, "configuration", "主配置", { x: 0, y: 0, width: 800, height: 600 });
    state = addNode(state, "character", { x: 0, y: 0 }, "region-1");
    state = addNode(state, "simulation", { x: 0, y: 0 }, null);
    state = addEdge(state, {
      source_node_id: "node-1",
      source_port_id: "out",
      target_node_id: "region-1",
      target_port_id: "in",
    });

    state = deleteRegion(state, "region-1");
    expect(state.definition.regions).toEqual([]);
    expect(state.definition.nodes[0].region_id).toBeNull();
    expect(state.definition.edges).toEqual([]);
  });

  it("重命名与选中状态", () => {
    let state = createEmptyEditorState("旧名字");
    state = renameWorkflow(state, "新名字");
    expect(state.definition.meta.name).toBe("新名字");

    state = addRegion(state, "configuration", "主配置", { x: 0, y: 0, width: 800, height: 600 });
    state = renameRegion(state, "region-1", "改名区域");
    expect(state.definition.regions[0].name).toBe("改名区域");

    state = updateRegionRect(state, "region-1", { x: 5, y: 6, width: 700, height: 500 });
    expect(state.definition.regions[0].rect.width).toBe(700);

    state = addNode(state, "character", { x: 0, y: 0 }, "region-1");
    state = setSelection(state, { nodes: ["node-1"] });
    expect(state.selection.nodes).toEqual(["node-1"]);

    state = setNodeRegion(state, "node-1", null);
    expect(state.definition.nodes[0].region_id).toBeNull();

    state = markSaved(state);
    expect(state.dirty).toBe(false);
  });
});
