// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisNodeResult } from "../../workflow/analysis_runner";
import type { AnalysisTableResult } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { AnalysisSelectionContext } from "../analysis_context";
import { AnalysisViewBody } from "./views";
import {
  DEFAULT_SERIES_NAME,
  BarChartView,
  buildBarChartData,
  buildBarChartOption,
  estimateBarChartFit,
} from "./barView";
import {
  BAR_AXIS_RESERVE,
  BAR_CATEGORY_GAP,
  BAR_HEIGHT_EXTRAS,
  BAR_MIN_HEIGHT,
  BAR_SERIES_GAP,
  BAR_TARGET_WIDTH,
  MAX_VIEW_FIT_HEIGHT,
  MIN_VIEW_WIDTH,
} from "../../workflow/view_size";

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
    { name: "来源", type: "string" },
  ],
  rows: [
    ["钟离", 100, "普攻"],
    ["雷电将军", 900, "大招"],
    ["钟离", 50, "普攻"],
  ],
  truncated: false,
};

function definitionWith(
  configParams: Record<string, unknown>,
  options: { viewKind?: "bar" | "member_table"; withDataEdge?: boolean } = {},
): WorkflowDefinition {
  const viewKind = options.viewKind ?? "bar";
  const withDataEdge = options.withDataEdge ?? true;
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
        kind: viewKind,
        region_id: "analysis-1",
        position: { x: 200, y: 0 },
        params: {},
      },
      {
        id: "config-1",
        kind: viewKind === "bar" ? "bar_config" : "table_config",
        region_id: "analysis-1",
        position: { x: 200, y: 200 },
        params: configParams,
      },
    ],
    edges: [
      ...(withDataEdge
        ? [
            {
              id: "e-data",
              source_node_id: "fetch-1",
              source_port_id: "out",
              target_node_id: "view-1",
              target_port_id: "in",
            },
          ]
        : []),
      {
        id: "e-config",
        source_node_id: "config-1",
        source_port_id: "out",
        target_node_id: "view-1",
        target_port_id: "config",
      },
    ],
    layout: {},
  };
}

const BAR_NODE: WorkflowNode = {
  id: "view-1",
  kind: "bar",
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

describe("buildBarChartData", () => {
  const identityFormat = (_column: string, value: unknown) => String(value);

  it("按 X 分槽、同 X + 系列求和合并，并记录首行下标", () => {
    const data = buildBarChartData(
      TABLE,
      { x: "角色", y: "伤害", series: "来源" },
      identityFormat,
    );
    expect(data).not.toBeNull();
    expect(data?.categories).toEqual(["钟离", "雷电将军"]);
    expect(data?.series.map((series) => series.name)).toEqual(["普攻", "大招"]);
    const puGong = data?.series.find((series) => series.name === "普攻");
    expect(puGong?.values).toEqual([150, null]);
    expect(puGong?.rowIndexes).toEqual([0, -1]);
    const daZhao = data?.series.find((series) => series.name === "大招");
    expect(daZhao?.values).toEqual([null, 900]);
    expect(daZhao?.rowIndexes).toEqual([-1, 1]);
  });

  it("无系列列时输出单一系列", () => {
    const data = buildBarChartData(
      TABLE,
      { x: "角色", y: "伤害", series: null },
      identityFormat,
    );
    expect(data?.series).toHaveLength(1);
    expect(data?.series[0]?.name).toBe(DEFAULT_SERIES_NAME);
    expect(data?.series[0]?.values).toEqual([150, 900]);
    expect(data?.series[0]?.rowIndexes).toEqual([0, 1]);
  });

  it("绑定列缺失时返回 null", () => {
    expect(
      buildBarChartData(
        TABLE,
        { x: "不存在", y: "伤害", series: null },
        identityFormat,
      ),
    ).toBeNull();
    expect(
      buildBarChartData(
        TABLE,
        { x: "角色", y: "伤害", series: "不存在" },
        identityFormat,
      ),
    ).toBeNull();
  });

  it("类目展示标签经 formatValue 解析", () => {
    const data = buildBarChartData(
      TABLE,
      { x: "角色", y: "伤害", series: null },
      (column, value) => (column === "角色" ? `显示:${String(value)}` : String(value)),
    );
    expect(data?.categories).toEqual(["显示:钟离", "显示:雷电将军"]);
  });
});

describe("buildBarChartOption", () => {
  const identityFormat = (_column: string, value: unknown) => String(value);

  it("选中柱使用描边数据项标记", () => {
    const data = buildBarChartData(
      TABLE,
      { x: "角色", y: "伤害", series: null },
      identityFormat,
    );
    const option = buildBarChartOption(data!, {
      selected: { seriesIndex: 0, dataIndex: 1 },
      formatValue: () => "",
      showLegend: false,
    });
    const series = (option.series ?? []) as Array<{
      data: (number | { value: number; itemStyle: unknown })[];
    }>;
    expect(series[0]?.data[0]).toBe(150);
    expect(series[0]?.data[1]).toMatchObject({ value: 900, itemStyle: { borderWidth: 1.5 } });
  });

  it("单系列不显示图例", () => {
    const data = buildBarChartData(
      TABLE,
      { x: "角色", y: "伤害", series: null },
      identityFormat,
    );
    const option = buildBarChartOption(data!, {
      selected: null,
      formatValue: () => "",
      showLegend: false,
    });
    expect(option.legend).toBeUndefined();
  });
});

describe("BarChartView 集成", () => {
  it("缺少柱状图配置时显示提示", () => {
    const definition = definitionWith(
      { x: "角色", y: "伤害" },
      { withDataEdge: true },
    );
    definition.edges = definition.edges.filter((edge) => edge.id !== "e-config");
    render(
      <AnalysisViewBody node={BAR_NODE} result={readyResult(TABLE)} definition={definition} />,
    );
    expect(screen.getByText("缺少柱状图配置（连接柱状图配置节点）")).toBeTruthy();
  });

  it("柱状图配置未绑定列时显示提示", () => {
    const definition = definitionWith({ x: "", y: "" });
    render(
      <AnalysisViewBody node={BAR_NODE} result={readyResult(TABLE)} definition={definition} />,
    );
    expect(screen.getByText("柱状图配置未绑定列")).toBeTruthy();
  });

  it("渲染类目与聚合数值，点击柱输出对应行 item", () => {
    const select = vi.fn();
    const definition = definitionWith({ x: "角色", y: "伤害", series: "来源" });
    renderView(BAR_NODE, definition, TABLE, select);

    expect(screen.getByRole("img", { name: "指标柱状图：X=角色，Y=伤害" })).toBeTruthy();
    const option = echartsStub.lastOption as {
      xAxis: { data: string[] };
      series: { name: string; data: unknown[] }[];
    };
    expect(option.xAxis.data).toEqual(["钟离", "雷电将军"]);
    expect(option.series.map((series) => series.name)).toEqual(["普攻", "大招"]);

    act(() => {
      echartsStub.lastClick?.(1, 1);
    });
    expect(select).toHaveBeenCalledWith("view-1", {
      角色: "雷电将军",
      伤害: 900,
      来源: "大招",
    });

    act(() => {
      echartsStub.lastClick?.(1, 1);
    });
    expect(select).toHaveBeenLastCalledWith("view-1", null);
  });

  it("越界点击不产生选择输出", () => {
    const select = vi.fn();
    const definition = definitionWith({ x: "角色", y: "伤害", series: "来源" });
    renderView(BAR_NODE, definition, TABLE, select);
    echartsStub.lastClick?.(0, 1);
    expect(select).not.toHaveBeenCalled();
  });

  it("Y 轴列不是数值列时显示错误", () => {
    const definition = definitionWith({ x: "角色", y: "来源", series: "" });
    render(
      <AnalysisSelectionContext.Provider
        value={{ selections: new Map(), select: () => {} }}
      >
        <BarChartView node={BAR_NODE} definition={definition} table={TABLE} />
      </AnalysisSelectionContext.Provider>,
    );
    expect(screen.getByText("Y 轴列必须是数值列：来源")).toBeTruthy();
  });

  it("绑定列不在上游表中时显示错误", () => {
    const definition = definitionWith({ x: "角色", y: "伤害", series: "不存在" });
    render(
      <AnalysisSelectionContext.Provider
        value={{ selections: new Map(), select: () => {} }}
      >
        <BarChartView node={BAR_NODE} definition={definition} table={TABLE} />
      </AnalysisSelectionContext.Provider>,
    );
    expect(screen.getByText("绑定列不在上游表中：不存在")).toBeTruthy();
  });
});

describe("estimateBarChartFit 内容尺寸估算", () => {
  const series = (values: (number | null)[]) => ({
    name: "数值",
    values,
    rowIndexes: values.map((_, index) => index),
  });

  it("无数据或空类目返回最小宽与 null 高度", () => {
    expect(estimateBarChartFit(null)).toEqual({
      fitWidth: MIN_VIEW_WIDTH,
      fitHeight: null,
    });
    expect(estimateBarChartFit({ categories: [], series: [] })).toEqual({
      fitWidth: MIN_VIEW_WIDTH,
      fitHeight: null,
    });
  });

  it("宽度按类目数与系列数估算，标签更长时取标签宽", () => {
    const slot =
      BAR_TARGET_WIDTH +
      (1 - 1) * BAR_SERIES_GAP +
      BAR_CATEGORY_GAP;
    const fit = estimateBarChartFit({
      categories: ["a", "b", "c"],
      series: [series([1, 2, 3])],
    });
    expect(fit.fitWidth).toBe(3 * slot + BAR_AXIS_RESERVE);

    const multiSlot =
      2 * BAR_TARGET_WIDTH + (2 - 1) * BAR_SERIES_GAP + BAR_CATEGORY_GAP;
    const multi = estimateBarChartFit({
      categories: ["a", "b", "c"],
      series: [series([1, 2, 3]), series([4, 5, 6])],
    });
    expect(multi.fitWidth).toBe(3 * multiSlot + BAR_AXIS_RESERVE);

    const longLabel = estimateBarChartFit({
      categories: ["非常非常长的类目标签"],
      series: [series([1])],
    });
    expect(longLabel.fitWidth).toBeGreaterThan(
      1 * slot + BAR_AXIS_RESERVE,
    );
  });

  it("高度按最大值/最小非零值比值估算并夹持上限", () => {
    const fit = estimateBarChartFit({
      categories: ["a", "b", "c"],
      series: [series([100, 1, null])],
    });
    expect(fit.fitHeight).toBe(
      Math.round(100 * BAR_MIN_HEIGHT + BAR_HEIGHT_EXTRAS),
    );

    const extreme = estimateBarChartFit({
      categories: ["a", "b"],
      series: [series([1_000_000, 1])],
    });
    expect(extreme.fitHeight).toBe(MAX_VIEW_FIT_HEIGHT);
  });

  it("没有正数值时高度无法估算", () => {
    const fit = estimateBarChartFit({
      categories: ["a", "b"],
      series: [series([0, null])],
    });
    expect(fit.fitHeight).toBeNull();
    expect(fit.fitWidth).toBeGreaterThan(0);
  });
});
