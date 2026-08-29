/** 柱状图视图：ECharts 柱状渲染 + 悬停柱值 + 点击选择输出。 */

import { useCallback, useMemo, useRef, useState } from "react";
import { rowItem } from "../../workflow/analysis_runner";
import {
  computeAnalysisShapes,
  connectedConfigNode,
  viewInputShape,
  type AnalysisTableResult,
} from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { useAnalysisSchemaCatalog, useAnalysisSelection } from "../analysis_context";
import { asString } from "./common";
import { useAssetNames } from "./useAssetNames";
import { MAX_RENDERED_ROWS, formatCell } from "./views";
import { useEChartsView, VIEW_CHART_PALETTE, type ChartOption } from "./echartsCore";

/** 无系列列时唯一系列的展示名。 */
export const DEFAULT_SERIES_NAME = "数值";

export interface BarViewBinding {
  x: string;
  y: string;
  /** 系列列；未绑定为 null。 */
  series: string | null;
}

export interface BarGroupSeries {
  name: string;
  /** 数值已聚合（同 X + 系列多行求和）；null 表示该组没有数值行，不渲染柱。 */
  values: (number | null)[];
  /** 每根柱对应的表行下标（合并组取首行），供选择输出 item；-1 表示该组无行。 */
  rowIndexes: number[];
}

export interface BarChartData {
  /** 类目展示标签，按最终渲染顺序（排序后）。 */
  categories: string[];
  series: BarGroupSeries[];
}

export interface SelectedBar {
  seriesIndex: number;
  dataIndex: number;
}

/**
 * 组装柱状图数据：按 X 值分槽，槽内按系列分组；同一 X + 系列的多行求和合并。
 * 类目键取原始值字符串、展示标签经 formatValue 解析，避免显示名撞车导致错误合并。
 */
export function buildBarChartData(
  table: AnalysisTableResult,
  binding: BarViewBinding,
  formatValue: (column: string, value: unknown) => string,
): BarChartData | null {
  const columnIndex = new Map(table.columns.map((column, index) => [column.name, index]));
  const xIndex = columnIndex.get(binding.x);
  const yIndex = columnIndex.get(binding.y);
  const seriesIndex = binding.series === null ? undefined : columnIndex.get(binding.series);
  if (xIndex === undefined || yIndex === undefined) {
    return null;
  }
  if (binding.series !== null && seriesIndex === undefined) {
    return null;
  }

  interface Group {
    label: string;
    rows: Map<string, { sum: number | null; rowIndex: number }>;
  }
  const groups = new Map<string, Group>();
  const seriesNames = new Map<string, string>();
  table.rows.forEach((row, rowIndex) => {
    const xRaw = row[xIndex];
    const xKey = String(xRaw);
    let group = groups.get(xKey);
    if (group === undefined) {
      group = { label: formatValue(binding.x, xRaw), rows: new Map() };
      groups.set(xKey, group);
    }
    const sRaw = seriesIndex === undefined ? null : row[seriesIndex];
    const sKey = seriesIndex === undefined ? "" : String(sRaw);
    if (seriesIndex !== undefined && !seriesNames.has(sKey)) {
      seriesNames.set(sKey, formatValue(binding.series ?? "", sRaw));
    }
    const yRaw = row[yIndex];
    const yValue = typeof yRaw === "number" && Number.isFinite(yRaw) ? yRaw : null;
    const entry = group.rows.get(sKey);
    if (entry === undefined) {
      group.rows.set(sKey, { sum: yValue, rowIndex });
    } else {
      entry.sum = entry.sum === null ? yValue : yValue === null ? entry.sum : entry.sum + yValue;
    }
  });

  const orderedKeys = [...groups.keys()];

  const seriesList =
    seriesIndex === undefined
      ? [["", DEFAULT_SERIES_NAME] as const]
      : [...seriesNames.entries()];
  return {
    categories: orderedKeys.map((key) => groups.get(key)?.label ?? key),
    series: seriesList.map(([seriesKey, seriesLabel]) => ({
      name: seriesLabel,
      values: orderedKeys.map((key) => groups.get(key)?.rows.get(seriesKey)?.sum ?? null),
      rowIndexes: orderedKeys.map(
        (key) => groups.get(key)?.rows.get(seriesKey)?.rowIndex ?? -1,
      ),
    })),
  };
}

function formatThousands(text: string): string {
  return text.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** 组装 ECharts option：暗色主题、悬停柱值、选中柱描边、可选图例。 */
export function buildBarChartOption(
  data: BarChartData,
  options: {
    selected: SelectedBar | null;
    formatValue: (value: number | null) => string;
    showLegend: boolean;
  },
): ChartOption {
  const asNumber = (value: unknown): number | null =>
    typeof value === "number" && Number.isFinite(value) ? value : null;
  const tooltipText = (params: { name?: unknown; seriesName?: unknown; value?: unknown }) => {
    const value = asNumber(params.value);
    const seriesPart =
      params.seriesName === undefined || params.seriesName === DEFAULT_SERIES_NAME
        ? ""
        : `${String(params.seriesName)} · `;
    const valueText = value === null ? "—" : options.formatValue(value);
    return `${seriesPart}${String(params.name ?? "")}<br />${valueText}`;
  };
  return {
    animation: false,
    grid: { left: 8, right: 8, top: options.showLegend ? 28 : 12, bottom: 0, containLabel: true },
    xAxis: {
      type: "category",
      data: data.categories,
      axisLine: { lineStyle: { color: "#475569" } },
      axisTick: { show: false },
      axisLabel: { color: "#94a3b8", fontSize: 11, hideOverlap: true },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        color: "#94a3b8",
        fontSize: 11,
        formatter: (value: number) => formatThousands(String(value)),
      },
      splitLine: { lineStyle: { color: "#334155" } },
    },
    tooltip: {
      trigger: "item",
      backgroundColor: "#263449",
      borderColor: "#334155",
      textStyle: { color: "#e2e8f0", fontSize: 12 },
      formatter: (params: unknown) =>
        tooltipText(params as { name?: unknown; seriesName?: unknown; value?: unknown }),
    },
    legend: options.showLegend
      ? {
          top: 0,
          left: 8,
          icon: "rect",
          itemWidth: 12,
          itemHeight: 8,
          textStyle: { color: "#94a3b8", fontSize: 12 },
        }
      : undefined,
    series: data.series.map((series, seriesIndex) => ({
      name: series.name,
      type: "bar" as const,
      barMaxWidth: 48,
      itemStyle: {
        color: VIEW_CHART_PALETTE[seriesIndex % VIEW_CHART_PALETTE.length],
        borderRadius: [2, 2, 0, 0] as [number, number, number, number],
      },
      data: series.values.map((value, dataIndex) => {
        if (value === null) {
          return null;
        }
        if (
          options.selected !== null &&
          options.selected.seriesIndex === seriesIndex &&
          options.selected.dataIndex === dataIndex
        ) {
          return {
            value,
            itemStyle: { borderColor: "#e2e8f0", borderWidth: 1.5 },
          };
        }
        return value;
      }),
    })),
  };
}

export function BarChartView({
  node,
  definition,
  table,
}: {
  node: WorkflowNode;
  definition: WorkflowDefinition;
  table: AnalysisTableResult;
}) {
  const config = useMemo(
    () => connectedConfigNode(definition, node.id, "bar_config"),
    [definition, node.id],
  );
  const x = asString(config?.params.x) ?? "";
  const y = asString(config?.params.y) ?? "";
  const seriesColumn = asString(config?.params.series) ?? "";

  const catalog = useAnalysisSchemaCatalog();
  const shapes = useMemo(() => computeAnalysisShapes(definition, catalog), [definition, catalog]);
  const inputShape = useMemo(
    () => viewInputShape(shapes, definition, node.id),
    [shapes, definition, node.id],
  );
  const valueKinds = useMemo(
    () => new Map(inputShape.map((column) => [column.name, column.valueKind ?? ""])),
    [inputShape],
  );
  const typeOf = useMemo(
    () => new Map(table.columns.map((column) => [column.name, column.type])),
    [table.columns],
  );
  const columnIndex = useMemo(
    () => new Map(table.columns.map((column, index) => [column.name, index])),
    [table.columns],
  );

  const assetKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const column of [x, seriesColumn]) {
      if (column === "" || !valueKinds.get(column)?.startsWith("asset:")) {
        continue;
      }
      const index = columnIndex.get(column);
      if (index === undefined) {
        continue;
      }
      for (const row of table.rows) {
        const value = row[index];
        if (typeof value === "string" && value !== "") {
          keys.add(value);
        }
      }
    }
    return Array.from(keys);
  }, [x, seriesColumn, valueKinds, columnIndex, table.rows]);
  const assetNames = useAssetNames(assetKeys);

  const selection = useAnalysisSelection();

  const [selected, setSelected] = useState<SelectedBar | null>(null);
  // 绑定变化时重置瞬态选择（不随工作流保存）。
  const bindingKey = [x, y, seriesColumn].join("|");
  const [prevBindingKey, setPrevBindingKey] = useState(bindingKey);
  if (bindingKey !== prevBindingKey) {
    setPrevBindingKey(bindingKey);
    setSelected(null);
  }

  const missingColumn = [x, y, ...(seriesColumn === "" ? [] : [seriesColumn])].find(
    (name) => name !== "" && !columnIndex.has(name),
  );
  const yType = typeOf.get(y) ?? "";
  const chartReady =
    config !== null &&
    x !== "" &&
    y !== "" &&
    missingColumn === undefined &&
    (yType === "int" || yType === "float");

  const formatValue = useCallback(
    (column: string, value: unknown) =>
      formatCell(value, typeOf.get(column), valueKinds.get(column), assetNames),
    [typeOf, valueKinds, assetNames],
  );

  const data = useMemo(
    () =>
      missingColumn === undefined && (yType === "int" || yType === "float")
        ? buildBarChartData(
            table,
            { x, y, series: seriesColumn === "" ? null : seriesColumn },
            formatValue,
          )
        : null,
    [missingColumn, yType, table, x, y, seriesColumn, formatValue],
  );

  const handleBarClick = useCallback(
    (seriesIndex: number, dataIndex: number) => {
      if (data === null) {
        return;
      }
      const rowIndex = data.series[seriesIndex]?.rowIndexes[dataIndex] ?? -1;
      if (rowIndex < 0 || rowIndex >= table.rows.length) {
        return;
      }
      const isSame =
        selected !== null && selected.seriesIndex === seriesIndex && selected.dataIndex === dataIndex;
      setSelected(isSame ? null : { seriesIndex, dataIndex });
      if (selection === null) {
        return;
      }
      selection.select(node.id, isSame ? null : rowItem(table, table.rows[rowIndex]));
    },
    [data, table, selected, selection, node.id],
  );

  const option = useMemo(
    () =>
      buildBarChartOption(data ?? { categories: [], series: [] }, {
        selected,
        formatValue: (value) => formatCell(value, yType),
        showLegend: seriesColumn !== "" && (data?.series.length ?? 0) > 1,
      }),
    [data, selected, yType, seriesColumn],
  );

  const containerRef = useRef<HTMLDivElement | null>(null);
  useEChartsView(containerRef, chartReady ? option : null, handleBarClick);

  if (config === null || x === "" || y === "") {
    // 连接与绑定校验由 AnalysisViewBody 与图校验器承担；此处兜底。
    return <div className="analysis-view-state">柱状图配置未就绪</div>;
  }
  if (missingColumn !== undefined) {
    return (
      <div className="analysis-view-state analysis-view-error">
        绑定列不在上游表中：{missingColumn}
      </div>
    );
  }
  if (yType !== "int" && yType !== "float") {
    return (
      <div className="analysis-view-state analysis-view-error">Y 轴列必须是数值列：{y}</div>
    );
  }

  return (
    <div className="analysis-chart-view">
      <div
        className="analysis-chart"
        ref={containerRef}
        role="img"
        aria-label={`指标柱状图：X=${x}，Y=${y}`}
      />
      {table.truncated && (
        <div className="analysis-member-footer">
          <span className="analysis-member-truncated">
            仅显示前 {MAX_RENDERED_ROWS} 行
          </span>
        </div>
      )}
    </div>
  );
}
