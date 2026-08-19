import { describe, expect, it } from "vitest";
import type { WorkflowDefinition } from "../workflow/types";
import {
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
});
