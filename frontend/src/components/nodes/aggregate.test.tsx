// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TableShape } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { AggregateEditor, setAnalysisEditorEnvironment } from "./analysis";

afterEach(() => {
  setAnalysisEditorEnvironment(null);
  cleanup();
});

const SHAPE: TableShape[] = [
  { name: "session_id", type: "string" },
  { name: "dps", type: "float" },
  { name: "hit_count", type: "int" },
  { name: "element", type: "string" },
  { name: "ok", type: "bool" },
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
        params: { source: "events" },
      },
      {
        id: "aggregate-1",
        kind: "aggregate",
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
        target_node_id: "aggregate-1",
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

function aggregateNode(params: Record<string, unknown>): WorkflowNode {
  return {
    id: "aggregate-1",
    kind: "aggregate",
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
    <AggregateEditor
      node={current}
      onChange={(params) => {
        onChange(params);
        setCurrent({ ...current, params });
      }}
    />
  );
}

describe("分组聚合节点编辑器（卡片直编）", () => {
  it("卡片内直编：分组列清单、指标区与中文函数名", () => {
    withUpstream();
    render(
      <AggregateEditor
        node={aggregateNode({
          group_by: ["element"],
          aggregates: [{ fn: "sum", column: "dps", as: "total_damage" }],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("统计维度（1）")).not.toBeNull();
    expect(screen.getByText("统计指标（1）")).not.toBeNull();
    expect(screen.getByText("求和")).not.toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("函数按列类型过滤：文本列只有计数，数值列有求和", () => {
    withUpstream();
    render(<Harness node={aggregateNode({})} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "＋ 添加统计指标" }));
    const columnSelect = screen.getAllByRole("combobox")[1];

    fireEvent.change(columnSelect, { target: { value: "element" } });
    expect(screen.queryByRole("option", { name: "求和" })).toBeNull();
    expect(screen.getByRole("option", { name: "计数" })).not.toBeNull();

    fireEvent.change(columnSelect, { target: { value: "dps" } });
    expect(screen.getByRole("option", { name: "求和" })).not.toBeNull();
  });

  it("选择函数和列后自动生成结果列名", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<Harness node={aggregateNode({})} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "＋ 添加统计指标" }));
    fireEvent.change(screen.getAllByRole("combobox")[1], {
      target: { value: "dps" },
    });

    expect(onChange).toHaveBeenLastCalledWith({
      aggregates: [{ fn: "sum", column: "dps", as: "sum_dps" }],
    });
  });

  it("自定义结果列名在切换列后保留", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness
        node={aggregateNode({
          aggregates: [{ fn: "sum", column: "dps", as: "sum_dps" }],
        })}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText("默认：sum_dps"), {
      target: { value: "total" },
    });
    fireEvent.change(screen.getAllByRole("combobox")[1], {
      target: { value: "hit_count" },
    });

    expect(onChange).toHaveBeenLastCalledWith({
      aggregates: [{ fn: "sum", column: "hit_count", as: "total" }],
    });
  });

  it("非数值列使用求和时行内提示", () => {
    withUpstream();
    render(
      <AggregateEditor
        node={aggregateNode({
          aggregates: [{ fn: "sum", column: "element" }],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("第 1 个统计指标：该函数仅适用于数值列")).not.toBeNull();
  });

  it("结果列名重复时行内提示", () => {
    withUpstream();
    render(
      <AggregateEditor
        node={aggregateNode({
          aggregates: [
            { fn: "sum", column: "dps", as: "sum_dps" },
            { fn: "sum", column: "dps", as: "sum_dps" },
          ],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("第 2 个统计指标：结果列名重复：sum_dps")).not.toBeNull();
  });

  it("勾选分组列即时写回 group_by", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<Harness node={aggregateNode({})} onChange={onChange} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /dps/ }));

    expect(onChange).toHaveBeenLastCalledWith({ group_by: ["dps"] });
  });

  it("分组列与指标皆空时提示", () => {
    withUpstream();
    render(<AggregateEditor node={aggregateNode({})} onChange={vi.fn()} />);
    expect(screen.getByText("至少选择一个统计维度或添加一个统计指标")).not.toBeNull();
  });
});
