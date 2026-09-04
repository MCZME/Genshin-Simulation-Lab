// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisNodeResult } from "../../workflow/analysis_runner";
import type { AnalysisTableResult } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { AnalysisSelectionContext } from "../analysis_context";
import { AnalysisViewBody } from "./views";
import { PieChartView, buildPieChartData, buildPieChartOption } from "./pieView";

// ECharts 依赖真实 DOM 尺寸与渲染管线，组件测试用桩替换生命周期封装，
// 捕获 option 与点击回调来断言视图行为。
const echartsStub = vi.hoisted(() => ({
  lastOption: null as unknown,
  lastClick: null as ((seriesIndex: number, dataIndex: number) => void) | null,
}));

vi.mock("./echartsCore", () => ({
  VIEW_CHART_PALETTE: ["#ef4444", "#3b82f6"],
  useEChartsView: (
    _containerRef: unknown,
    option: unknown,
    onClickBar: (seriesIndex: number, dataIndex: number) => void,
  ) => {
    echartsStub.lastOption = option;
    echartsStub.lastClick = onClickBar;
  },
}));

afterEach(() => {
  cleanup();
  echartsStub.lastOption = null;
  echartsStub.lastClick = null;
});

const TABLE: AnalysisTableResult = {
  columns: [
    { name: "角色", type: "string" },
    { name: "伤害", type: "float" },
    { name: "标签", type: "string" },
  ],
  rows: [
    ["钟离", 100, "帝君"],
    ["雷电将军", 900, "将军"],
    ["钟离", 50, "帝君"],
  ],
  truncated: false,
};

function definitionWith(
  configParams: Record<string, unknown>,
  options: { withConfigEdge?: boolean } = {},
): WorkflowDefinition {
  const withConfigEdge = options.withConfigEdge ?? true;
  return {
    schema_version: 1,
    meta: { name: "测试" },
    regions: [
      {
        id: "analysis-1",
        kind: "analysis",
        name: "分析",
        rect: { x: 0, y: 0, width: 800, height: 600 },
      },
    ],
    nodes: [
      {
        id: "fetch-1",
        kind: "fetch",
        region_id: "analysis-1",
        position: { x: 0, y: 0 },
        params: { source: "runs" },
      },
      {
        id: "view-1",
        kind: "pie",
        region_id: "analysis-1",
        position: { x: 200, y: 0 },
        params: {},
      },
      {
        id: "config-1",
        kind: "pie_config",
        region_id: "analysis-1",
        position: { x: 200, y: 200 },
        params: configParams,
      },
    ],
    edges: [
      ...(withConfigEdge
        ? [
            {
              id: "e-data",
              source_node_id: "fetch-1",
              source_port_id: "out",
              target_node_id: "config-1",
              target_port_id: "in",
            },
            {
              id: "e-forward",
              source_node_id: "config-1",
              source_port_id: "out",
              target_node_id: "view-1",
              target_port_id: "in",
            },
          ]
        : [
            {
              id: "e-data",
              source_node_id: "fetch-1",
              source_port_id: "out",
              target_node_id: "view-1",
              target_port_id: "in",
            },
          ]),
    ],
    layout: {},
  };
}

const PIE_NODE: WorkflowNode = {
  id: "view-1",
  kind: "pie",
  region_id: "analysis-1",
  position: { x: 200, y: 0 },
  params: {},
};

function readyResult(table: AnalysisTableResult): AnalysisNodeResult {
  return { status: "ready", table };
}

function renderView(
  node: WorkflowNode,
  definition: WorkflowDefinition,
  table: AnalysisTableResult,
  select?: (nodeId: string, item: unknown | null) => void,
) {
  return render(
    <AnalysisSelectionContext.Provider
      value={{ selections: new Map(), select: select ?? (() => {}) }}
    >
      <AnalysisViewBody node={node} result={readyResult(table)} definition={definition} />
    </AnalysisSelectionContext.Provider>,
  );
}

describe("buildPieChartData", () => {
  const identityFormat = (_column: string, value: unknown) => String(value);

  it("按分组列合并扇区并求和，记录组内全部行下标", () => {
    const data = buildPieChartData(
      TABLE,
      { group: "角色", value: "伤害", label: null },
      identityFormat,
    );
    expect(data?.slices).toEqual([
      { name: "钟离", value: 150, rowIndexes: [0, 2] },
      { name: "雷电将军", value: 900, rowIndexes: [1] },
    ]);
  });

  it("绑定标签列时扇区名取该组首行标签", () => {
    const data = buildPieChartData(
      TABLE,
      { group: "角色", value: "伤害", label: "标签" },
      identityFormat,
    );
    expect(data?.slices.map((slice) => slice.name)).toEqual(["帝君", "将军"]);
    expect(data?.slices.map((slice) => slice.value)).toEqual([150, 900]);
  });

  it("值列空值不参与求和，全空组为 null", () => {
    const table: AnalysisTableResult = {
      columns: TABLE.columns,
      rows: [...TABLE.rows, ["纳西妲", null, "草神"]],
      truncated: false,
    };
    const data = buildPieChartData(
      table,
      { group: "角色", value: "伤害", label: "标签" },
      identityFormat,
    );
    const nahida = data?.slices.find((slice) => slice.name === "草神");
    expect(nahida?.value).toBeNull();
    expect(nahida?.rowIndexes).toEqual([3]);
  });

  it("绑定列缺失时返回 null", () => {
    expect(
      buildPieChartData(
        TABLE,
        { group: "不存在", value: "伤害", label: null },
        identityFormat,
      ),
    ).toBeNull();
    expect(
      buildPieChartData(
        TABLE,
        { group: "角色", value: "伤害", label: "不存在" },
        identityFormat,
      ),
    ).toBeNull();
  });
});

describe("buildPieChartOption", () => {
  const identityFormat = (_column: string, value: unknown) => String(value);

  it("扇区数据映射为名称与数值，选中扇区使用描边数据项标记", () => {
    const data = buildPieChartData(
      TABLE,
      { group: "角色", value: "伤害", label: null },
      identityFormat,
    );
    const option = buildPieChartOption(data!, {
      selected: { dataIndex: 1 },
      formatValue: () => "",
    });
    const series = (option.series ?? []) as Array<{
      type: string;
      data: { name: string; value: number | null; itemStyle?: unknown }[];
    }>;
    expect(series[0]?.type).toBe("pie");
    expect(series[0]?.data[0]).toEqual({ name: "钟离", value: 150 });
    expect(series[0]?.data[1]).toMatchObject({
      name: "雷电将军",
      value: 900,
      itemStyle: { borderWidth: 1.5 },
    });
  });

  it("图例始终提供", () => {
    const data = buildPieChartData(
      TABLE,
      { group: "角色", value: "伤害", label: null },
      identityFormat,
    );
    const option = buildPieChartOption(data!, {
      selected: null,
      formatValue: () => "",
    });
    expect(option.legend).toBeDefined();
  });
});

describe("PieChartView 集成", () => {
  it("直连数据且无配置时使用默认分组/值列渲染", () => {
    const definition = definitionWith(
      { group: "角色", value: "伤害" },
      { withConfigEdge: false },
    );
    render(
      <AnalysisViewBody node={PIE_NODE} result={readyResult(TABLE)} definition={definition} />,
    );
    expect(screen.getByRole("img", { name: "饼图：分组=角色，值=伤害" })).toBeTruthy();
  });

  it("饼图配置未绑定列时显示提示", () => {
    const definition = definitionWith({ group: "", value: "" });
    render(
      <AnalysisViewBody node={PIE_NODE} result={readyResult(TABLE)} definition={definition} />,
    );
    expect(screen.getByText("饼图配置未绑定列")).toBeTruthy();
  });

  it("渲染扇区数据，点击扇区输出对应组行集表", () => {
    const select = vi.fn();
    const definition = definitionWith({ group: "角色", value: "伤害", label: "标签" });
    renderView(PIE_NODE, definition, TABLE, select);

    expect(screen.getByRole("img", { name: "饼图：分组=角色，值=伤害" })).toBeTruthy();
    const option = echartsStub.lastOption as {
      series: { data: { name: string; value: number | null }[] }[];
    };
    expect(option.series[0]?.data.map((item) => item.name)).toEqual(["帝君", "将军"]);
    expect(option.series[0]?.data.map((item) => item.value)).toEqual([150, 900]);

    act(() => {
      echartsStub.lastClick?.(0, 0);
    });
    expect(select).toHaveBeenCalledWith("view-1", {
      columns: TABLE.columns,
      rows: [
        ["钟离", 100, "帝君"],
        ["钟离", 50, "帝君"],
      ],
      truncated: false,
    });

    act(() => {
      echartsStub.lastClick?.(0, 0);
    });
    expect(select).toHaveBeenLastCalledWith("view-1", null);
  });

  it("非饼图系列的点击不产生选择输出", () => {
    const select = vi.fn();
    const definition = definitionWith({ group: "角色", value: "伤害", label: "标签" });
    renderView(PIE_NODE, definition, TABLE, select);
    act(() => {
      echartsStub.lastClick?.(1, 0);
    });
    expect(select).not.toHaveBeenCalled();
  });

  it("值列不是数值列时显示错误", () => {
    const definition = definitionWith({ group: "角色", value: "标签", label: "" });
    render(
      <AnalysisSelectionContext.Provider
        value={{ selections: new Map(), select: () => {} }}
      >
        <PieChartView node={PIE_NODE} definition={definition} table={TABLE} />
      </AnalysisSelectionContext.Provider>,
    );
    expect(screen.getByText("值列必须是数值列：标签")).toBeTruthy();
  });

  it("绑定列不在上游表中时显示错误", () => {
    const definition = definitionWith({ group: "角色", value: "伤害", label: "不存在" });
    render(
      <AnalysisSelectionContext.Provider
        value={{ selections: new Map(), select: () => {} }}
      >
        <PieChartView node={PIE_NODE} definition={definition} table={TABLE} />
      </AnalysisSelectionContext.Provider>,
    );
    expect(screen.getByText("绑定列不在上游表中：不存在")).toBeTruthy();
  });
});
