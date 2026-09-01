// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisNodeResult } from "../../workflow/analysis_runner";
import type { AnalysisTableResult } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import {
  AnalysisViewBody,
  compareCells,
  countHiddenColumns,
  estimateMemberTableLayout,
  estimateTextWidth,
  formatCell,
  sortRows,
  type ViewFitInfo,
} from "./views";

afterEach(() => {
  cleanup();
});

function definitionWith(
  configParams: Record<string, unknown>,
  options: { withDataEdge?: boolean; withConfigEdge?: boolean } = {},
): WorkflowDefinition {
  const withDataEdge = options.withDataEdge ?? true;
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
        kind: "member_table",
        region_id: "analysis-1",
        position: { x: 200, y: 0 },
        params: {},
      },
      {
        id: "config-1",
        kind: "table_config",
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
      ...(withConfigEdge
        ? [
            {
              id: "e-config",
              source_node_id: "config-1",
              source_port_id: "out",
              target_node_id: "view-1",
              target_port_id: "config",
            },
          ]
        : []),
    ],
    layout: {},
  };
}

function viewNode(definition: WorkflowDefinition): WorkflowNode {
  return definition.nodes.find((node) => node.id === "view-1") as WorkflowNode;
}

function sampleTable(overrides: Partial<AnalysisTableResult> = {}): AnalysisTableResult {
  return {
    columns: [
      { name: "session_id", type: "string" },
      { name: "weapon", type: "string" },
      { name: "total_damage", type: "int" },
      { name: "dps", type: "float" },
    ],
    rows: [
      ["s-1", "sword", 61500, 1025.0],
      ["s-2", "claymore", 82000, 1366.666],
      ["s-3", "polearm", 41000, 683.333],
    ],
    truncated: false,
    ...overrides,
  };
}

function readyResult(overrides: Partial<AnalysisTableResult> = {}): AnalysisNodeResult {
  return { status: "ready", table: sampleTable(overrides) };
}

function headerNames(): string[] {
  return screen
    .getAllByRole("columnheader")
    .map((item) => (item.textContent ?? "").replace(/▾/g, "").trim());
}

function renderView(
  result: AnalysisNodeResult | undefined,
  options: { withDataEdge?: boolean; withConfigEdge?: boolean } = {},
  onLocateNode: (nodeId: string) => void = vi.fn(),
  viewOptions: { viewWidth?: number; onFitChange?: (info: ViewFitInfo) => void } = {},
) {
  const definition = definitionWith(
    { condition_columns: ["weapon"], data_columns: ["total_damage", "dps"] },
    options,
  );
  return render(
    <AnalysisViewBody
      node={viewNode(definition)}
      result={result}
      definition={definition}
      onLocateNode={onLocateNode}
      viewWidth={viewOptions.viewWidth}
      onFitChange={viewOptions.onFitChange}
    />,
  );
}

describe("表格视图", () => {
  it("未连接数据源时显示提示", () => {
    renderView(readyResult(), { withDataEdge: false });
    expect(screen.getByText(/未连接数据源/)).not.toBeNull();
  });

  it("缺少表格配置时显示提示", () => {
    renderView(readyResult(), { withConfigEdge: false });
    expect(screen.getByText(/缺少表格配置/)).not.toBeNull();
  });

  it("配置未绑定列时提示并可定位到配置节点", () => {
    const definition = definitionWith({
      condition_columns: [],
      data_columns: [],
    });
    const onLocateNode = vi.fn();
    render(
      <AnalysisViewBody
        node={viewNode(definition)}
        result={readyResult()}
        definition={definition}
        onLocateNode={onLocateNode}
      />,
    );
    expect(screen.getByText(/表格配置未绑定列/)).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "打开表格配置" }));
    expect(onLocateNode).toHaveBeenCalledWith("config-1");
  });

  it("未执行、加载中、错误与上游为空分别呈现", () => {
    renderView(undefined);
    expect(screen.getByText(/未执行/)).not.toBeNull();
    cleanup();

    renderView({ status: "loading" });
    expect(screen.getByText(/加载中/)).not.toBeNull();
    cleanup();

    renderView({ status: "error", error: "查询失败" });
    expect(screen.getByText("查询失败")).not.toBeNull();
    cleanup();

    renderView({ status: "ready", table: sampleTable({ rows: [] }) });
    expect(screen.getByText(/上游为空/)).not.toBeNull();
  });

  it("过期状态保留旧表并显示刷新横幅", () => {
    renderView({ status: "stale", table: sampleTable() });
    expect(screen.getByText("结果已过期，正在刷新…")).not.toBeNull();
    expect(screen.getByText("共 3 行")).not.toBeNull();
  });

  it("过期状态无旧表时显示过期提示", () => {
    renderView({ status: "stale" });
    expect(screen.getByText("结果已过期")).not.toBeNull();
  });

  it("按绑定渲染列，session_id 默认隐藏，数值按类型格式化", () => {
    renderView(readyResult());
    expect(headerNames()).toEqual(["weapon", "total_damage", "dps"]);
    expect(screen.queryByText("session_id")).toBeNull();
    expect(screen.getByText("61,500")).not.toBeNull();
    expect(screen.getByText("1,366.67")).not.toBeNull();
    expect(screen.getByText(/共 3 行/)).not.toBeNull();
  });

  it("空值单元格带 cell-null 标记", () => {
    renderView(
      readyResult({
        rows: [
          ["s-1", "sword", null, 1025.0],
          ["s-2", "claymore", 82000, 1366.666],
        ],
      }),
    );
    const nullCell = screen.getByText("—");
    expect(nullCell.className).toContain("cell-null");
  });

  it("交替行带 stripe 标记（按绝对行号）", () => {
    renderView(readyResult());
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].className).not.toContain("stripe");
    expect(rows[1].className).toContain("stripe");
    expect(rows[2].className).not.toContain("stripe");
  });

  it("数据列点击表头单列升降排序并可清除", () => {
    renderView(readyResult());
    const damageHeader = screen.getByRole("columnheader", { name: /total_damage/ });
    fireEvent.click(damageHeader);
    expect(damageHeader.className).toContain("sorted");
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("polearm");
    expect(rows[2].textContent).toContain("claymore");

    fireEvent.click(damageHeader);
    const descRows = screen.getAllByRole("row").slice(1);
    expect(descRows[0].textContent).toContain("claymore");
    expect(descRows[2].textContent).toContain("polearm");

    fireEvent.click(screen.getByRole("button", { name: "清除排序" }));
    const resetRows = screen.getAllByRole("row").slice(1);
    expect(resetRows[0].textContent).toContain("sword");
    expect(screen.queryByRole("button", { name: "清除排序" })).toBeNull();
  });

  it("条件列组合排序显示序号，跨列点击顺序即优先级", () => {
    const definition = definitionWith({
      condition_columns: ["weapon", "level"],
      data_columns: ["total_damage"],
    });
    const table = sampleTable({
      columns: [
        { name: "session_id", type: "string" },
        { name: "weapon", type: "string" },
        { name: "level", type: "int" },
        { name: "total_damage", type: "int" },
      ],
      rows: [
        ["s-1", "sword", 2, 61000],
        ["s-2", "claymore", 1, 82000],
        ["s-3", "polearm", 1, 41000],
        ["s-4", "sword", 1, 59000],
      ],
    });
    render(
      <AnalysisViewBody
        node={viewNode(definition)}
        result={{ status: "ready", table }}
        definition={definition}
        onLocateNode={vi.fn()}
      />,
    );
    const weaponHeader = screen.getByRole("columnheader", { name: /weapon/ });
    const levelHeader = screen.getByRole("columnheader", { name: /level/ });
    fireEvent.click(weaponHeader);
    expect(screen.getByText("①")).not.toBeNull();
    fireEvent.click(levelHeader);
    expect(screen.getByText("①")).not.toBeNull();
    expect(screen.getByText("②")).not.toBeNull();
    const rows = screen.getAllByRole("row").slice(1);
    // 主键 weapon 升序，组内按 level 升序。
    expect(rows[0].textContent).toContain("claymore");
    expect(rows[1].textContent).toContain("polearm");
    expect(within(rows[2]).getByText("1")).not.toBeNull();
    expect(within(rows[3]).getByText("2")).not.toBeNull();
  });

  it("高亮最大/最小作用于数据列并可清除", () => {
    renderView(readyResult());
    const damageHeader = screen.getByRole("columnheader", { name: /total_damage/ });
    fireEvent.click(within(damageHeader).getByTitle("列操作"));
    fireEvent.click(screen.getByRole("button", { name: "高亮最大" }));
    expect(damageHeader).not.toBeNull();
    expect(document.querySelector("td.hl-max")?.textContent).toBe("82,000");

    fireEvent.click(within(damageHeader).getByTitle("列操作"));
    fireEvent.click(screen.getByRole("button", { name: "高亮最小" }));
    expect(document.querySelector("td.hl-min")?.textContent).toBe("41,000");
    expect(document.querySelector("td.hl-max")).toBeNull();
  });

  it("拖列头调整显示顺序，跨区不改绑定角色", () => {
    renderView(readyResult());
    const headers = () => screen.getAllByRole("columnheader");
    const first = headers()[0];
    const last = headers()[2];
    fireEvent.dragStart(first);
    fireEvent.dragOver(last);
    fireEvent.drop(last);
    fireEvent.dragEnd(first);
    expect(headerNames()).toEqual(["total_damage", "dps", "weapon"]);
  });

  it("截断时显示提示", () => {
    renderView(readyResult({ truncated: true }));
    expect(screen.getByText(/仅显示前 10000 行/)).not.toBeNull();
  });

  it("内容宽超过可用宽度时显示右缘渐隐并上报被隐藏列数", () => {
    const onFitChange = vi.fn();
    renderView(readyResult(), {}, vi.fn(), {
      viewWidth: 200,
      onFitChange,
    });
    expect(onFitChange).toHaveBeenCalled();
    const info = onFitChange.mock.calls[0][0] as ViewFitInfo;
    expect(info.fitWidth).toBeGreaterThan(200);
    expect(info.hiddenColumns).toBeGreaterThan(0);
    expect(
      screen.getByLabelText(new RegExp(`还有 ${info.hiddenColumns} 列被隐藏`)),
    ).not.toBeNull();
  });

  it("宽度充足时不显示渐隐遮罩", () => {
    renderView(readyResult(), {}, vi.fn(), { viewWidth: 560 });
    expect(document.querySelector(".analysis-member-fade")).toBeNull();
  });

  it("内容自然宽等于卡片宽时不算超出，不显示渐隐", () => {
    const table = sampleTable();
    const layout = estimateMemberTableLayout({
      order: ["weapon", "total_damage", "dps"],
      rows: table.rows,
      columnIndex: new Map(table.columns.map((column, index) => [column.name, index])),
      typeOf: new Map(table.columns.map((column) => [column.name, column.type])),
      valueKinds: new Map(),
      assetNames: new Map(),
      dataColumns: ["total_damage", "dps"],
    });
    renderView(readyResult(), {}, vi.fn(), { viewWidth: layout.fitWidth });
    expect(document.querySelector(".analysis-member-fade")).toBeNull();

    cleanup();
    renderView(readyResult(), {}, vi.fn(), { viewWidth: layout.fitWidth - 1 });
    expect(document.querySelector(".analysis-member-fade")).not.toBeNull();
  });
});

describe("表格纯逻辑", () => {
  it("formatCell 按类型格式化", () => {
    expect(formatCell(61500, "int")).toBe("61,500");
    expect(formatCell(1366.666, "float")).toBe("1,366.67");
    expect(formatCell(1025.0, "float")).toBe("1,025");
    expect(formatCell(null, "string")).toBe("—");
    expect(formatCell("sword", "string")).toBe("sword");
  });

  it("formatCell 按 valueKind 解析资产与枚举显示名", () => {
    const names = new Map([["character:barbara", "芭芭拉"]]);
    expect(formatCell("character:barbara", "string", "asset:characters", names)).toBe(
      "芭芭拉",
    );
    expect(formatCell("character:missing", "string", "asset:characters", names)).toBe(
      "character:missing",
    );
    expect(formatCell("hydro", "string", "enum:element")).toBe("水");
    expect(formatCell("completed", "string", "enum:run_state")).toBe("已完成");
    expect(formatCell("DAMAGE_RESOLVED", "string", "enum:event_type")).toBe(
      "伤害结算",
    );
    expect(formatCell("unknown", "string", "enum:element")).toBe("unknown");
    expect(formatCell("sword", "string", undefined)).toBe("sword");
  });

  it("compareCells 空值恒排最后", () => {
    expect(compareCells(null, 1)).toBeGreaterThan(0);
    expect(compareCells(1, null)).toBeLessThan(0);
    expect(compareCells(null, null)).toBe(0);
    expect(compareCells(2, 1)).toBeGreaterThan(0);
  });

  it("sortRows 按多键稳定排序", () => {
    const rows = [
      ["b", 2],
      ["a", 2],
      ["b", 1],
      ["a", 1],
    ];
    const columnIndex = new Map([
      ["group", 0],
      ["value", 1],
    ]);
    const sorted = sortRows(rows, [
      { column: "group", direction: "asc" },
      { column: "value", direction: "desc" },
    ], columnIndex);
    expect(sorted).toEqual([
      ["a", 2],
      ["a", 1],
      ["b", 2],
      ["b", 1],
    ]);
  });

  it("estimateTextWidth 对中文与数字采用不同宽度", () => {
    expect(estimateTextWidth("测试")).toBeGreaterThan(estimateTextWidth("123"));
    expect(estimateTextWidth("abc")).toBeGreaterThan(0);
  });

  it("estimateMemberTableLayout 按表头与单元格内容取宽并夹持", () => {
    const columnIndex = new Map([
      ["weapon", 0],
      ["damage", 1],
    ]);
    const typeOf = new Map([
      ["weapon", "string"],
      ["damage", "int"],
    ]);
    const layout = estimateMemberTableLayout({
      order: ["weapon", "damage"],
      rows: [
        ["sword", 61500],
        ["claymore", 82000],
      ],
      columnIndex,
      typeOf,
      valueKinds: new Map(),
      assetNames: new Map(),
      dataColumns: ["damage"],
    });
    expect(layout.widths).toHaveLength(2);
    expect(layout.fitWidth).toBe(layout.widths[0] + layout.widths[1]);
    expect(layout.widths[1]).toBeGreaterThan(layout.widths[0]);
    expect(layout.widths[0]).toBeGreaterThanOrEqual(72);
    expect(layout.widths[0]).toBeLessThanOrEqual(240);
  });

  it("countHiddenColumns 按累计宽度统计被隐藏列", () => {
    expect(countHiddenColumns([100, 100, 100], 250)).toBe(1);
    expect(countHiddenColumns([100, 100], 250)).toBe(0);
    expect(countHiddenColumns([], 100)).toBe(0);
  });
});
