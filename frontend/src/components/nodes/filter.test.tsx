// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TableShape } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { FilterEditor, setAnalysisEditorEnvironment } from "./analysis";

afterEach(() => {
  setAnalysisEditorEnvironment(null);
  cleanup();
});

const SHAPE: TableShape[] = [
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
        params: { source: "runs" },
      },
      {
        id: "filter-1",
        kind: "filter",
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
        target_node_id: "filter-1",
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

function filterNode(params: Record<string, unknown>): WorkflowNode {
  return {
    id: "filter-1",
    kind: "filter",
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
    <FilterEditor
      node={current}
      onChange={(params) => {
        onChange(params);
        setCurrent({ ...current, params });
      }}
    />
  );
}

describe("过滤节点编辑器（卡片直编）", () => {
  it("条件直接在卡片内编辑，没有弹层", () => {
    withUpstream();
    render(
      <FilterEditor
        node={filterNode({
          mode: "all",
          conditions: [{ column: "dps", op: "gte", value: 0.5 }],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("spinbutton")).not.toBeNull();
    expect(screen.getByText("大于等于")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "编辑条件…" })).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("操作符按列类型过滤：文本列无大小比较，数值列有", () => {
    withUpstream();
    render(<Harness node={filterNode({})} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "＋ 添加条件" }));
    const columnSelect = screen.getAllByRole("combobox")[0];

    fireEvent.change(columnSelect, { target: { value: "element" } });
    expect(screen.queryByRole("option", { name: "大于" })).toBeNull();
    expect(screen.getByRole("option", { name: "属于" })).not.toBeNull();

    fireEvent.change(columnSelect, { target: { value: "dps" } });
    expect(screen.getByRole("option", { name: "大于等于" })).not.toBeNull();
  });

  it("数值列：数字输入即时写回为数值", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness
        node={filterNode({
          mode: "all",
          conditions: [{ column: "dps", op: "gte", value: "" }],
        })}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "0.5" } });

    expect(onChange).toHaveBeenLastCalledWith({
      mode: "all",
      conditions: [{ column: "dps", op: "gte", value: 0.5 }],
    });
  });

  it("属于：多值 chips 即时写回数组", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness
        node={filterNode({
          mode: "all",
          conditions: [{ column: "element", op: "in", value: [] }],
        })}
        onChange={onChange}
      />,
    );
    const chipsInput = screen.getByPlaceholderText("输入值后回车");
    fireEvent.change(chipsInput, { target: { value: "hydro" } });
    fireEvent.keyDown(chipsInput, { key: "Enter" });
    expect(screen.getByText("hydro")).not.toBeNull();
    fireEvent.change(chipsInput, { target: { value: "pyro,electro" } });
    fireEvent.keyDown(chipsInput, { key: "Enter" });

    expect(onChange).toHaveBeenLastCalledWith({
      mode: "all",
      conditions: [
        { column: "element", op: "in", value: ["hydro", "pyro", "electro"] },
      ],
    });
  });

  it("为空：不出现值输入且写回不含 value", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness
        node={filterNode({
          mode: "all",
          conditions: [{ column: "element", op: "eq", value: "hydro" }],
        })}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getAllByRole("combobox")[1], {
      target: { value: "is_null" },
    });
    expect(screen.queryByRole("textbox")).toBeNull();

    expect(onChange).toHaveBeenLastCalledWith({
      mode: "all",
      conditions: [{ column: "element", op: "is_null" }],
    });
  });

  it("布尔列：真/假下拉即时写回布尔值", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness
        node={filterNode({
          mode: "all",
          conditions: [{ column: "ok", op: "eq" }],
        })}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getAllByRole("combobox")[2], {
      target: { value: "true" },
    });

    expect(onChange).toHaveBeenLastCalledWith({
      mode: "all",
      conditions: [{ column: "ok", op: "eq", value: true }],
    });
  });

  it("切换列时操作符自动回退为等于", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness
        node={filterNode({
          mode: "all",
          conditions: [{ column: "dps", op: "gte", value: 0.5 }],
        })}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "element" },
    });

    const last = onChange.mock.calls.at(-1)?.[0] as {
      conditions: { column: string; op: string; value?: unknown }[];
    };
    expect(last.conditions[0]).toMatchObject({ column: "element", op: "eq" });
    expect(last.conditions[0].value).toBeUndefined();
  });

  it("存量错误类型值行内提示", () => {
    withUpstream();
    render(
      <FilterEditor
        node={filterNode({
          mode: "all",
          conditions: [{ column: "dps", op: "gte", value: "0.5" }],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("第 1 个条件：请填写与列类型匹配的值")).not.toBeNull();
  });

  it("切换任一模式即时写回 mode=any", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<Harness node={filterNode({})} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "满足任一" }));

    expect(onChange).toHaveBeenLastCalledWith({ mode: "any", conditions: [] });
  });
});
