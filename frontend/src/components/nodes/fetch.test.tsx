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
        fields: [
          {
            path: "result.final_damage",
            type: "float",
            description: "结算伤害值",
            value_kind: "",
          },
        ],
      },
      {
        name: "HEALING_RESOLVED",
        fields: [
          {
            path: "result.final_healing",
            type: "float",
            description: "结算治疗值",
            value_kind: "",
          },
        ],
      },
    ],
    snapshot_tree: {
      key: "root",
      label: "输入快照",
      kind: "object",
      children: [
        {
          key: "team",
          label: "队伍",
          kind: "list",
          children: [
            {
              key: "character",
              label: "角色",
              kind: "object",
              children: [
                {
                  key: "asset_key",
                  label: "资产",
                  kind: "scalar",
                  type: "string",
                  default_name_template: "char_{0}_key",
                },
                {
                  key: "level",
                  label: "等级",
                  kind: "scalar",
                  type: "int",
                  default_name_template: "char_{0}_level",
                },
              ],
            },
          ],
        },
      ],
    },
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
  it("摘要卡显示来源、数据范围与输出列，编辑按钮打开弹层", () => {
    withCatalog();
    render(
      <FetchEditor
        node={fetchNode({
          source: "runs",
          snapshot_columns: [
            { path: "team.0.character.asset_key", name: "char_1_key", type: "string" },
          ],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("运行记录")).not.toBeNull();
    expect(screen.getByText("输入条件列 1 列")).not.toBeNull();
    expect(screen.getByText("char_1_key")).not.toBeNull();
    expect(screen.getByText("来源")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "编辑数据…" }));
    expect(screen.getByRole("dialog", { name: "配置获取数据" })).not.toBeNull();
  });

  it("无输出列时摘要显示空态", () => {
    withCatalog();
    render(<FetchEditor node={fetchNode({ source: "events" })} onChange={vi.fn()} />);
    expect(screen.getByText("事件范围 全部")).not.toBeNull();
    expect(screen.getByText("未添加输出列")).not.toBeNull();
  });

  it("弹层内切换事件记录来源需要二次确认", () => {
    withCatalog();
    const onChange = vi.fn();
    render(
      <Harness
        node={fetchNode({
          source: "runs",
          snapshot_columns: [
            { path: "team.0.character.asset_key", name: "char", type: "string" },
          ],
        })}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "编辑数据…" }));
    fireEvent.click(screen.getByRole("button", { name: "事件记录" }));
    expect(screen.getByText("切换来源将清空当前来源的参数，再次点击确认。")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "确认切换？" }));
    fireEvent.click(screen.getByRole("button", { name: "完成" }));
    expect(onChange).toHaveBeenLastCalledWith({
      source: "events",
      event_types: [],
      payload_columns: [],
    });
  });

  it("运行记录：目录勾选输入条件列并提交", () => {
    withCatalog();
    const onChange = vi.fn();
    render(<Harness node={fetchNode({ source: "runs" })} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "编辑数据…" }));

    fireEvent.click(screen.getByRole("checkbox", { name: /资产/ }));
    fireEvent.click(screen.getByRole("button", { name: "添加" }));
    fireEvent.click(screen.getByRole("button", { name: "完成" }));

    expect(onChange).toHaveBeenLastCalledWith({
      source: "runs",
      snapshot_columns: [
        { path: "team.0.character.asset_key", name: "char_1_key", type: "string" },
      ],
    });
  });

  it("事件记录：勾选字段自动带出事件范围与输出列", () => {
    withCatalog();
    const onChange = vi.fn();
    render(<Harness node={fetchNode({ source: "events" })} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "编辑数据…" }));

    fireEvent.click(screen.getByRole("checkbox", { name: /结算伤害值/ }));
    fireEvent.click(screen.getByRole("button", { name: "完成" }));

    expect(onChange).toHaveBeenLastCalledWith({
      source: "events",
      event_types: ["DAMAGE_RESOLVED"],
      payload_columns: [
        {
          event_type: "DAMAGE_RESOLVED",
          path: "result.final_damage",
          name: "final_damage",
          type: "float",
        },
      ],
    });
  });

  it("事件范围由输出列目录统一控制并显示状态", () => {
    withCatalog();
    const onChange = vi.fn();
    render(<Harness node={fetchNode({ source: "events" })} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "编辑数据…" }));

    expect(screen.getByText("事件范围：全部（未筛选）")).not.toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: "DAMAGE_RESOLVED" }));
    expect(screen.getByText("事件范围：已选 1 类")).not.toBeNull();

    fireEvent.change(screen.getByPlaceholderText("搜索事件类型…"), {
      target: { value: "NOPE" },
    });
    expect(screen.getByText("无匹配事件类型")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "完成" }));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ event_types: ["DAMAGE_RESOLVED"] }),
    );
  });

  it("手动添加列并提交", () => {
    withCatalog();
    const onChange = vi.fn();
    render(<Harness node={fetchNode({ source: "runs" })} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "编辑数据…" }));

    fireEvent.click(screen.getByRole("button", { name: "＋ 手动添加列" }));
    fireEvent.change(screen.getByPlaceholderText("路径（目录外）"), {
      target: { value: "custom.path" },
    });
    fireEvent.change(screen.getByPlaceholderText("列名"), {
      target: { value: "custom_col" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));
    fireEvent.click(screen.getByRole("button", { name: "完成" }));

    expect(onChange).toHaveBeenLastCalledWith({
      source: "runs",
      snapshot_columns: [{ path: "custom.path", name: "custom_col", type: "string" }],
    });
  });

  it("手动添加列支持中文列名", () => {
    withCatalog();
    const onChange = vi.fn();
    render(<Harness node={fetchNode({ source: "runs" })} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "编辑数据…" }));

    fireEvent.click(screen.getByRole("button", { name: "＋ 手动添加列" }));
    fireEvent.change(screen.getByPlaceholderText("路径（目录外）"), {
      target: { value: "custom.path" },
    });
    fireEvent.change(screen.getByPlaceholderText("列名"), {
      target: { value: "角色等级" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));
    fireEvent.click(screen.getByRole("button", { name: "完成" }));

    expect(onChange).toHaveBeenLastCalledWith({
      source: "runs",
      snapshot_columns: [{ path: "custom.path", name: "角色等级", type: "string" }],
    });
  });

  it("输出列名重复时弹层内提示", () => {
    withCatalog();
    const onChange = vi.fn();
    render(<Harness node={fetchNode({ source: "runs" })} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "编辑数据…" }));

    fireEvent.click(screen.getByRole("button", { name: "＋ 手动添加列" }));
    fireEvent.change(screen.getByPlaceholderText("路径（目录外）"), {
      target: { value: "a.b" },
    });
    fireEvent.change(screen.getByPlaceholderText("列名"), {
      target: { value: "same" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));

    // 添加后表单保持打开，直接填第二行制造重名列。
    fireEvent.change(screen.getByPlaceholderText("路径（目录外）"), {
      target: { value: "c.d" },
    });
    fireEvent.change(screen.getByPlaceholderText("列名"), {
      target: { value: "same" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));

    expect(screen.getByText("输出列名重复：same")).not.toBeNull();
  });
});
