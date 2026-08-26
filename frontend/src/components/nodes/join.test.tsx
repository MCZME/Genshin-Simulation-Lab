// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TableShape } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { getNodeKindSpec } from "../../workflow/registry";
import { JoinEditor, setAnalysisEditorEnvironment } from "./analysis";

afterEach(() => {
  setAnalysisEditorEnvironment(null);
  cleanup();
});

const LEFT_SHAPE: TableShape[] = [
  { name: "session_id", type: "string" },
  { name: "dps", type: "float" },
];

const RIGHT_SHAPE: TableShape[] = [
  { name: "session_id", type: "string" },
  { name: "hit_count", type: "int" },
];

function withInputs(leftShape: TableShape[], rightShape: TableShape[]) {
  const definition: WorkflowDefinition = {
    schema_version: 1,
    meta: { name: "测试" },
    regions: [],
    nodes: [
      {
        id: "left-up",
        kind: "fetch",
        region_id: "analysis-1",
        position: { x: 0, y: 0 },
        params: { source: "runs" },
      },
      {
        id: "right-up",
        kind: "fetch",
        region_id: "analysis-1",
        position: { x: 0, y: 0 },
        params: { source: "events" },
      },
      {
        id: "join-1",
        kind: "join",
        region_id: "analysis-1",
        position: { x: 0, y: 0 },
        params: {},
      },
    ],
    edges: [
      {
        id: "edge-l",
        source_node_id: "left-up",
        source_port_id: "out",
        target_node_id: "join-1",
        target_port_id: "left",
      },
      {
        id: "edge-r",
        source_node_id: "right-up",
        source_port_id: "out",
        target_node_id: "join-1",
        target_port_id: "right",
      },
    ],
    layout: {},
  };
  setAnalysisEditorEnvironment({
    catalog: null,
    definition,
    shapes: new Map([
      ["left-up", leftShape],
      ["right-up", rightShape],
    ]),
  });
}

function joinNode(params: Record<string, unknown>): WorkflowNode {
  return {
    id: "join-1",
    kind: "join",
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
    <JoinEditor
      node={current}
      onChange={(params) => {
        onChange(params);
        setCurrent({ ...current, params });
      }}
    />
  );
}

describe("合并表（连接）节点编辑器", () => {
  it("节点显示名为合并表", () => {
    expect(getNodeKindSpec("join")?.displayName).toBe("合并表");
  });

  it("卡片内直编：主表/副表匹配键与两种合并方式说明", () => {
    withInputs(LEFT_SHAPE, RIGHT_SHAPE);
    render(<JoinEditor node={joinNode({})} onChange={vi.fn()} />);
    expect(screen.getByText("第一路输入为主表，第二路为副表")).not.toBeNull();
    expect(screen.getByText("只保留两边匹配上的行")).not.toBeNull();
    expect(screen.getByText("保留主表全部行")).not.toBeNull();
    expect(screen.getByText("主表")).not.toBeNull();
    expect(screen.getByText("副表")).not.toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("切换合并方式写回 mode=left", () => {
    withInputs(LEFT_SHAPE, RIGHT_SHAPE);
    const onChange = vi.fn();
    render(<Harness node={joinNode({})} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /保留主表全部行/ }));

    expect(onChange).toHaveBeenLastCalledWith({ mode: "left" });
  });

  it("选择主表与副表匹配键写回 left_key / right_key", () => {
    withInputs(LEFT_SHAPE, RIGHT_SHAPE);
    const onChange = vi.fn();
    render(<Harness node={joinNode({})} onChange={onChange} />);
    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "session_id" },
    });
    expect(onChange).toHaveBeenLastCalledWith({ left_key: "session_id" });
    fireEvent.change(screen.getAllByRole("combobox")[1], {
      target: { value: "session_id" },
    });
    expect(onChange).toHaveBeenLastCalledWith({
      left_key: "session_id",
      right_key: "session_id",
    });
  });

  it("键类型不一致时警告", () => {
    withInputs(LEFT_SHAPE, RIGHT_SHAPE);
    render(
      <JoinEditor
        node={joinNode({ left_key: "session_id", right_key: "hit_count" })}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByText(/主表键（string）与副表键（int）类型不一致/),
    ).not.toBeNull();
  });

  it("未选匹配键时逐侧提示", () => {
    withInputs(LEFT_SHAPE, RIGHT_SHAPE);
    render(<JoinEditor node={joinNode({})} onChange={vi.fn()} />);
    expect(screen.getByText("请选择主表匹配列")).not.toBeNull();
    expect(screen.getByText("请选择副表匹配列")).not.toBeNull();
  });

  it("未连接输入时提示先连接两路输入", () => {
    withInputs([], []);
    render(<JoinEditor node={joinNode({})} onChange={vi.fn()} />);
    expect(screen.getByText("连接两路输入后配置匹配键")).not.toBeNull();
  });

  it("显示合并后列数，重名列只输出一份", () => {
    withInputs(LEFT_SHAPE, RIGHT_SHAPE);
    render(
      <JoinEditor
        node={joinNode({ left_key: "session_id", right_key: "session_id" })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("合并后 3 列（副表与主表重名的列只输出一份）")).not.toBeNull();
  });
});
