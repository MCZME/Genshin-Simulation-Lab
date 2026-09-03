// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TableShape } from "../../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../../workflow/types";
import { DeriveEditor, setAnalysisEditorEnvironment } from "./index";

afterEach(() => {
  setAnalysisEditorEnvironment(null);
  cleanup();
});

const SHAPE: TableShape[] = [
  { name: "dps", type: "float" },
  { name: "element", type: "string" },
];

function withUpstream() {
  const definition: WorkflowDefinition = {
    schema_version: 1,
    meta: { name: "测试" },
    regions: [],
    nodes: [
      {
        id: "upstream-1",
        kind: "fetch",
        region_id: "analysis-1",
        position: { x: 0, y: 0 },
        params: { source: "runs" },
      },
      {
        id: "derive-1",
        kind: "derive",
        region_id: "analysis-1",
        position: { x: 0, y: 0 },
        params: {},
      },
    ],
    edges: [
      {
        id: "edge-1",
        source_node_id: "upstream-1",
        source_port_id: "out",
        target_node_id: "derive-1",
        target_port_id: "in",
      },
    ],
    layout: {},
  };
  setAnalysisEditorEnvironment({
    catalog: null,
    definition,
    shapes: new Map([["upstream-1", SHAPE]]),
  });
}

function deriveNode(params: Record<string, unknown>): WorkflowNode {
  return {
    id: "derive-1",
    kind: "derive",
    region_id: "analysis-1",
    position: { x: 0, y: 0 },
    params,
  };
}

describe("设置列值节点编辑器（卡片直编）", () => {
  it("空态提示并可通过添加按钮追加列设置", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<DeriveEditor node={deriveNode({ columns: [] })} onChange={onChange} />);
    expect(screen.getByText("至少添加一个列设置")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "＋ 添加列设置" }));
    expect(onChange).toHaveBeenCalledWith({
      columns: [{ name: "", type: "string", value: "" }],
    });
  });

  it("两个新增列重名时在对应行内提示", () => {
    withUpstream();
    render(
      <DeriveEditor
        node={deriveNode({
          columns: [
            { name: "role", type: "string", value: "输出" },
            { name: "role", type: "string", value: "辅助" },
          ],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("新列名重复：role")).toBeTruthy();
  });

  it("重复覆盖同一输入列时在对应行内提示", () => {
    withUpstream();
    render(
      <DeriveEditor
        node={deriveNode({
          columns: [
            { name: "dps", type: "float", value: 1 },
            { name: "dps", type: "float", value: 2 },
          ],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("输入列 dps 不能重复覆盖")).toBeTruthy();
  });

  it("覆盖输入列类型不一致时在对应行内提示", () => {
    withUpstream();
    render(
      <DeriveEditor
        node={deriveNode({
          columns: [{ name: "dps", type: "int", value: 1 }],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("覆盖列类型须与输入列一致（float）")).toBeTruthy();
  });
});
