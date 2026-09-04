// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TableShape } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { ComputeEditor, setAnalysisEditorEnvironment } from "./analysis";

afterEach(() => {
  setAnalysisEditorEnvironment(null);
  cleanup();
});

const SHAPE: TableShape[] = [
  { name: "total_damage", type: "float" },
  { name: "frames_run", type: "int" },
  { name: "element", type: "string" },
  { name: "总伤害", type: "float" },
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
        id: "compute-1",
        kind: "compute",
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
        target_node_id: "compute-1",
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

function computeNode(params: Record<string, unknown>): WorkflowNode {
  return {
    id: "compute-1",
    kind: "compute",
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
    <ComputeEditor
      node={current}
      onChange={(params) => {
        onChange(params);
        setCurrent({ ...current, params });
      }}
    />
  );
}

describe("计算列节点编辑器", () => {
  it("卡片直编：结果列名、公式输入与插入列下拉，无弹层", () => {
    withUpstream();
    render(<ComputeEditor node={computeNode({ columns: [{}] })} onChange={vi.fn()} />);
    expect(screen.getByPlaceholderText("结果列名")).not.toBeNull();
    expect(screen.getByPlaceholderText("公式，如 total_damage / (frames_run / 60)")).not.toBeNull();
    expect(screen.getByRole("option", { name: "插入列…" })).not.toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("有效公式写回契约 AST", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<Harness node={computeNode({ columns: [{}] })} onChange={onChange} />);
    fireEvent.change(screen.getByPlaceholderText("公式，如 total_damage / (frames_run / 60)"), {
      target: { value: "total_damage / (frames_run / 60)" },
    });

    expect(onChange).toHaveBeenLastCalledWith({
      columns: [
        {
          expr: {
            op: "/",
            left: { col: "total_damage" },
            right: { op: "/", left: { col: "frames_run" }, right: { lit: 60 } },
          },
        },
      ],
    });
  });

  it("无效公式行内提示且不写回", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<ComputeEditor node={computeNode({ columns: [{}] })} onChange={onChange} />);
    fireEvent.change(screen.getByPlaceholderText("公式，如 total_damage / (frames_run / 60)"), {
      target: { value: "total_damage /" },
    });

    expect(screen.getByText("公式不完整（缺少数值或列）")).not.toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("插入列下拉把列名写进公式", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<Harness node={computeNode({ columns: [{}] })} onChange={onChange} />);
    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "total_damage" },
    });

    expect(
      (screen.getByPlaceholderText(
        "公式，如 total_damage / (frames_run / 60)",
      ) as HTMLInputElement).value,
    ).toBe("total_damage");
    expect(onChange).toHaveBeenLastCalledWith({
      columns: [{ expr: { col: "total_damage" } }],
    });
  });

  it("结果列名即时写回", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<Harness node={computeNode({ columns: [{}] })} onChange={onChange} />);
    fireEvent.change(screen.getByPlaceholderText("结果列名"), {
      target: { value: "dps" },
    });

    expect(onChange).toHaveBeenLastCalledWith({ columns: [{ name: "dps" }] });
  });

  it("结果列名与公式支持中文", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<Harness node={computeNode({ columns: [{}] })} onChange={onChange} />);
    fireEvent.change(screen.getByPlaceholderText("结果列名"), {
      target: { value: "每秒伤害" },
    });
    fireEvent.change(screen.getByPlaceholderText("公式，如 total_damage / (frames_run / 60)"), {
      target: { value: "总伤害 / 2" },
    });

    expect(onChange).toHaveBeenLastCalledWith({
      columns: [
        { name: "每秒伤害", expr: { op: "/", left: { col: "总伤害" }, right: { lit: 2 } } },
      ],
    });
  });

  it("输入法组合期间结果列名不写回，组合结束写最终值", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<Harness node={computeNode({ columns: [{}] })} onChange={onChange} />);
    const nameInput = screen.getByPlaceholderText("结果列名");

    fireEvent.compositionStart(nameInput);
    fireEvent.change(nameInput, { target: { value: "角色 " } });
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.compositionEnd(nameInput);
    expect(onChange).toHaveBeenLastCalledWith({ columns: [{ name: "角色" }] });
  });

  it("输入法组合期间公式不写回 AST", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<Harness node={computeNode({ columns: [{}] })} onChange={onChange} />);
    const formulaInput = screen.getByPlaceholderText("公式，如 total_damage / (frames_run / 60)");

    fireEvent.compositionStart(formulaInput);
    fireEvent.change(formulaInput, { target: { value: "1" } });
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.compositionEnd(formulaInput);
    fireEvent.change(formulaInput, { target: { value: "总伤害 / 2" } });
    expect(onChange).toHaveBeenLastCalledWith({
      columns: [{ expr: { op: "/", left: { col: "总伤害" }, right: { lit: 2 } } }],
    });
  });

  it("结果列名与已有列重名时提示", () => {
    withUpstream();
    render(
      <ComputeEditor
        node={computeNode({ columns: [{ name: "total_damage" }] })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("结果列名重复：total_damage")).not.toBeNull();
  });

  it("公式引用未知列时提示", () => {
    withUpstream();
    render(<ComputeEditor node={computeNode({ columns: [{}] })} onChange={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText("公式，如 total_damage / (frames_run / 60)"), {
      target: { value: "nope" },
    });
    expect(screen.getByText("未知列：nope")).not.toBeNull();
  });

  it("公式引用非数值列时提示", () => {
    withUpstream();
    render(<ComputeEditor node={computeNode({ columns: [{}] })} onChange={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText("公式，如 total_damage / (frames_run / 60)"), {
      target: { value: "element" },
    });
    expect(screen.getByText("列 element 不是数值列，不能参与计算")).not.toBeNull();
  });

  it("未添加计算列时提示", () => {
    withUpstream();
    render(<ComputeEditor node={computeNode({})} onChange={vi.fn()} />);
    expect(screen.getByText("至少添加一个计算列")).not.toBeNull();
  });

  it("已有 expr 回显为公式文本", () => {
    withUpstream();
    render(
      <ComputeEditor
        node={computeNode({
          columns: [
            {
              name: "dps",
              expr: {
                op: "/",
                left: { col: "total_damage" },
                right: { op: "/", left: { col: "frames_run" }, right: { lit: 60 } },
              },
            },
          ],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(
      (screen.getByPlaceholderText(
        "公式，如 total_damage / (frames_run / 60)",
      ) as HTMLInputElement).value,
    ).toBe("total_damage / (frames_run / 60)");
  });
});
