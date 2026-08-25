// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createAnalysisSchemaCatalog } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { FetchEditor, setAnalysisEditorEnvironment } from "./analysis";

afterEach(() => {
  setAnalysisEditorEnvironment(null);
  cleanup();
});

const EMPTY_DEFINITION: WorkflowDefinition = {
  schema_version: 1,
  meta: { name: "测试" },
  regions: [],
  nodes: [],
  edges: [],
  layout: {},
};

function catalogWith() {
  const catalog = createAnalysisSchemaCatalog();
  catalog.load({
    tables: [],
    event_types: [
      {
        name: "DAMAGE_RESOLVED",
        fields: [{ path: "result.final_damage", type: "float", description: "结算伤害值" }],
      },
    ],
    snapshot_paths: [
      {
        path: "team.0.character.asset_key",
        type: "string",
        default_name: "char_1_key",
        segments: ["队伍", "槽位 1", "角色", "资产"],
      },
      {
        path: "team.0.character.level",
        type: "int",
        default_name: "char_1_level",
        segments: ["队伍", "槽位 1", "角色", "等级"],
      },
    ],
  });
  return catalog;
}

function withCatalog() {
  setAnalysisEditorEnvironment({
    catalog: catalogWith(),
    definition: EMPTY_DEFINITION,
    shapes: new Map(),
  });
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
    <FetchEditor
      node={current}
      onChange={(params) => {
        onChange(params);
        setCurrent({ ...current, params });
      }}
    />
  );
}

function fetchNode(params: Record<string, unknown>): WorkflowNode {
  return {
    id: "fetch-1",
    kind: "fetch",
    region_id: "analysis-1",
    position: { x: 0, y: 0 },
    params,
  };
}

describe("获取数据节点编辑器", () => {
  it("默认运行记录来源显示快照提取列", () => {
    render(<FetchEditor node={fetchNode({ source: "runs" })} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "运行记录" }).className).toContain("active");
    expect(screen.getByText("快照提取列")).not.toBeNull();
    expect(screen.queryByText(/事件类型/)).toBeNull();
  });

  it("切换事件记录来源写入 source 与事件参数", () => {
    const onChange = vi.fn();
    render(
      <FetchEditor
        node={fetchNode({
          source: "runs",
          snapshot_columns: [{ path: "team.0.character.asset_key", name: "char", type: "string" }],
        })}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "事件记录" }));
    expect(onChange).toHaveBeenCalledWith({
      source: "events",
      event_types: [],
      frame_min: undefined,
      frame_max: undefined,
      payload_columns: [],
    });
  });

  it("事件记录来源显示事件类型与载荷提取列", () => {
    render(
      <FetchEditor
        node={fetchNode({ source: "events", event_types: ["DAMAGE_RESOLVED"] })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/事件类型（已选 1）/)).not.toBeNull();
    expect(screen.getByText("载荷提取列")).not.toBeNull();
    expect(screen.queryByText("快照提取列")).toBeNull();
  });

  it("运行记录来源按结构路径逐段选择并写入路径/类型/默认列名", () => {
    withCatalog();
    const onChange = vi.fn();
    render(<Harness node={fetchNode({ source: "runs" })} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "＋ 添加提取列" }));
    fireEvent.change(screen.getByLabelText("快照路径第 1 段"), { target: { value: "队伍" } });
    fireEvent.change(screen.getByLabelText("快照路径第 2 段"), { target: { value: "槽位 1" } });
    fireEvent.change(screen.getByLabelText("快照路径第 3 段"), { target: { value: "角色" } });
    fireEvent.change(screen.getByLabelText("快照路径第 4 段"), { target: { value: "资产" } });

    expect(onChange).toHaveBeenLastCalledWith({
      source: "runs",
      snapshot_columns: [
        { path: "team.0.character.asset_key", type: "string", name: "char_1_key" },
      ],
    });
  });

  it("事件记录来源先选事件类型再选字段，自动带出路径与类型", () => {
    withCatalog();
    const onChange = vi.fn();
    render(<Harness node={fetchNode({ source: "events" })} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "＋ 添加提取列" }));
    fireEvent.change(screen.getByLabelText("载荷事件类型 1"), {
      target: { value: "DAMAGE_RESOLVED" },
    });
    fireEvent.change(screen.getByLabelText("载荷字段 1"), {
      target: { value: "result.final_damage" },
    });

    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        source: "events",
        payload_columns: [
          { path: "result.final_damage", type: "float", name: "final_damage" },
        ],
      }),
    );
  });

  it("输出形状摘要显示固定列数量与提取列 chips", () => {
    withCatalog();
    render(
      <FetchEditor
        node={fetchNode({
          source: "runs",
          snapshot_columns: [{ path: "team.0.character.asset_key", name: "char_1_key", type: "string" }],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("运行记录固定列 16")).not.toBeNull();
    expect(screen.getByText("char_1_key")).not.toBeNull();
  });

  it("无提取列时形状摘要显示提示，事件来源显示事件固定列", () => {
    withCatalog();
    render(<FetchEditor node={fetchNode({ source: "events" })} onChange={vi.fn()} />);
    expect(screen.getByText("事件记录固定列 4")).not.toBeNull();
    expect(screen.getByText("无提取列")).not.toBeNull();
  });
});
