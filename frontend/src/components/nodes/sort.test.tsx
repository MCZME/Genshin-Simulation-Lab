// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TableShape } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { SortEditor, setAnalysisEditorEnvironment } from "./analysis";

afterEach(() => {
  setAnalysisEditorEnvironment(null);
  cleanup();
});

const SHAPE: TableShape[] = [
  { name: "session_id", type: "string" },
  { name: "dps", type: "float" },
  { name: "hit_count", type: "int" },
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
        id: "sort-1",
        kind: "sort",
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
        target_node_id: "sort-1",
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

function sortNode(params: Record<string, unknown>): WorkflowNode {
  return {
    id: "sort-1",
    kind: "sort",
    region_id: "analysis-1",
    position: { x: 0, y: 0 },
    params,
  };
}

function Harness({
  node,
  onChange,
}: {
  node: WorkflowNode;
  onChange: (params: Record<string, unknown>) => void;
}) {
  const [current, setCurrent] = useState(node);
  return (
    <SortEditor
      node={current}
      onChange={(params) => {
        onChange(params);
        setCurrent({ ...current, params });
      }}
    />
  );
}

describe("排序节点编辑器（卡片直编）", () => {
  it("卡片内直编：中文方向与排序键序号，无弹层", () => {
    withUpstream();
    render(
      <SortEditor
        node={sortNode({ keys: [{ column: "dps", direction: "desc" }] })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("①")).not.toBeNull();
    expect(screen.getByRole("option", { name: "升序" })).not.toBeNull();
    expect(screen.getByRole("option", { name: "降序" })).not.toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("添加排序键默认降序，选择列后写回", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<Harness node={sortNode({})} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "＋ 添加排序键" }));
    expect(onChange).toHaveBeenLastCalledWith({
      keys: [{ column: "", direction: "desc" }],
    });
    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "dps" },
    });

    expect(onChange).toHaveBeenLastCalledWith({
      keys: [{ column: "dps", direction: "desc" }],
    });
  });

  it("切换方向写回升序", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness
        node={sortNode({ keys: [{ column: "dps", direction: "desc" }] })}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getAllByRole("combobox")[1], {
      target: { value: "asc" },
    });

    expect(onChange).toHaveBeenLastCalledWith({
      keys: [{ column: "dps", direction: "asc" }],
    });
  });

  it("下移第一个排序键交换顺序", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness
        node={sortNode({
          keys: [
            { column: "dps", direction: "desc" },
            { column: "element", direction: "asc" },
          ],
        })}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getAllByRole("button", { name: "↓" })[0]);

    expect(onChange).toHaveBeenLastCalledWith({
      keys: [
        { column: "element", direction: "asc" },
        { column: "dps", direction: "desc" },
      ],
    });
  });

  it("首行上移与末行下移按钮禁用", () => {
    withUpstream();
    render(
      <SortEditor
        node={sortNode({
          keys: [
            { column: "dps", direction: "desc" },
            { column: "element", direction: "asc" },
          ],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(
      (screen.getAllByRole("button", { name: "↑" })[0] as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getAllByRole("button", { name: "↓" })[1] as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("未选列时行内提示", () => {
    withUpstream();
    render(
      <SortEditor
        node={sortNode({ keys: [{ column: "", direction: "desc" }] })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("第 1 个排序键：请选择列")).not.toBeNull();
  });

  it("排序列重复时行内提示", () => {
    withUpstream();
    render(
      <SortEditor
        node={sortNode({
          keys: [
            { column: "dps", direction: "desc" },
            { column: "dps", direction: "asc" },
          ],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("第 2 个排序键：列重复：dps")).not.toBeNull();
  });

  it("未添加排序键时提示", () => {
    withUpstream();
    render(<SortEditor node={sortNode({})} onChange={vi.fn()} />);
    expect(screen.getByText("至少添加一个排序键")).not.toBeNull();
  });

  it("移除排序键", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness
        node={sortNode({
          keys: [
            { column: "dps", direction: "desc" },
            { column: "element", direction: "asc" },
          ],
        })}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getAllByRole("button", { name: "×" })[0]);

    expect(onChange).toHaveBeenLastCalledWith({
      keys: [{ column: "element", direction: "asc" }],
    });
  });
});
