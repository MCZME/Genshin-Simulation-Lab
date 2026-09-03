/** 饼图视图：ECharts 饼图渲染 + 悬停数值占比 + 点击选择输出。 */

import { useCallback, useMemo, useRef, useState } from "react";
import { tableRowsByIndex } from "../../workflow/analysis_runner";
import {
  computeAnalysisShapes,
  connectedConfigNode,
  defaultPieBinding,
  viewInputShape,
  type AnalysisTableResult,
} from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import {
  useAnalysisSchemaCatalog,
  useAnalysisSelection,
  useAnalysisStageSelection,
} from "../analysis_context";
import { asString } from "./common";
import { useAssetNames } from "./useAssetNames";
import { MAX_RENDERED_ROWS, formatCell } from "./views";
import { useEChartsView, VIEW_CHART_PALETTE, type ChartOption } from "./echartsCore";

export interface PieViewBinding {
  group: string;
  value: string;
  /** 标签列；未绑定为 null。 */
  label: string | null;
}

export interface PieSliceData {
  /** 扇区展示名：绑定标签列时取该组首行标签显示值，否则取分组列显示值。 */
  name: string;
  /** 分组求和后的数值；null 表示该组没有数值行，不参与占比。 */
  value: number | null;
  /** 该组命中的输入表行下标，供选择输出行集表。 */
  rowIndexes: number[];
}

export interface PieChartData {
  slices: PieSliceData[];
}

export interface SelectedSlice {
  dataIndex: number;
}

/** 组装饼图数据：按分组列值合并为扇区，值列数值求和。 */
export function buildPieChartData(
  table: AnalysisTableResult,
  binding: PieViewBinding,
  formatValue: (column: string, value: unknown) => string,
): PieChartData | null {
  const columnIndex = new Map(table.columns.map((column, index) => [column.name, index]));
  const groupIndex = columnIndex.get(binding.group);
  const valueIndex = columnIndex.get(binding.value);
  const labelIndex = binding.label === null ? undefined : columnIndex.get(binding.label);
  if (groupIndex === undefined || valueIndex === undefined) {
    return null;
  }
  if (binding.label !== null && labelIndex === undefined) {
    return null;
  }

  const groups = new Map<string, { name: string; sum: number | null; rowIndexes: number[] }>();
  table.rows.forEach((row, rowIndex) => {
    const groupRaw = row[groupIndex];
    const key = String(groupRaw);
    let group = groups.get(key);
    if (group === undefined) {
      const name =
        labelIndex === undefined
          ? formatValue(binding.group, groupRaw)
          : formatValue(binding.label ?? "", row[labelIndex]);
      group = { name, sum: null, rowIndexes: [] };
      groups.set(key, group);
    }
    group.rowIndexes.push(rowIndex);
    const raw = row[valueIndex];
    if (typeof raw === "number" && Number.isFinite(raw)) {
      group.sum = (group.sum ?? 0) + raw;
    }
  });
  return {
    slices: [...groups.values()].map((group) => ({
      name: group.name,
      value: group.sum,
      rowIndexes: group.rowIndexes,
    })),
  };
}

/** 组装 ECharts option：暗色主题、图例滚动、悬停数值与占比、选中扇区描边。 */
export function buildPieChartOption(
  data: PieChartData,
  options: {
    selected: SelectedSlice | null;
    formatValue: (value: number | null) => string;
  },
): ChartOption {
  const asNumber = (value: unknown): number | null =>
    typeof value === "number" && Number.isFinite(value) ? value : null;
  const tooltipText = (params: { name?: unknown; value?: unknown; percent?: unknown }) => {
    const value = asNumber(params.value);
    const percent = typeof params.percent === "number" ? params.percent : null;
    const parts = [value === null ? "—" : options.formatValue(value)];
    if (percent !== null) {
      parts.push(`${percent}%`);
    }
    return `${String(params.name ?? "")}<br />${parts.join(" · ")}`;
  };
  return {
    animation: false,
    color: VIEW_CHART_PALETTE,
    legend: {
      type: "scroll",
      bottom: 0,
      left: 8,
      icon: "rect",
      itemWidth: 12,
      itemHeight: 8,
      textStyle: { color: "#94a3b8", fontSize: 12 },
    },
    tooltip: {
      trigger: "item",
      backgroundColor: "#263449",
      borderColor: "#334155",
      textStyle: { color: "#e2e8f0", fontSize: 12 },
      formatter: (params: unknown) =>
        tooltipText(params as { name?: unknown; value?: unknown; percent?: unknown }),
    },
    series: [
      {
        type: "pie" as const,
        radius: "68%",
        center: ["50%", "45%"],
        label: { show: false },
        labelLine: { show: false },
        data: data.slices.map((slice, dataIndex) => {
          // 值为 null 的组不传 value（ECharts 按空数据处理），保留数据项对齐下标。
          const item: {
            name: string;
            value?: number;
            itemStyle?: { borderColor: string; borderWidth: number };
          } = { name: slice.name };
          if (slice.value !== null) {
            item.value = slice.value;
          }
          if (options.selected !== null && options.selected.dataIndex === dataIndex) {
            item.itemStyle = { borderColor: "#e2e8f0", borderWidth: 1.5 };
          }
          return item;
        }),
      },
    ],
  };
}

export function PieChartView({
  node,
  definition,
  table,
  stageId,
}: {
  node: WorkflowNode;
  definition: WorkflowDefinition;
  table: AnalysisTableResult;
  stageId?: string;
}) {
  const config = useMemo(
    () => connectedConfigNode(definition, node.id, "pie_config"),
    [definition, node.id],
  );
  const defaultBinding = useMemo(
    () => (config === null ? defaultPieBinding(table.columns) : null),
    [config, table.columns],
  );
  const group = config === null ? (defaultBinding?.group ?? "") : (asString(config.params.group) ?? "");
  const value = config === null ? (defaultBinding?.value ?? "") : (asString(config.params.value) ?? "");
  const labelColumn = config === null ? "" : (asString(config.params.label) ?? "");

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
    for (const column of [group, labelColumn]) {
      if (column === "" || !valueKinds.get(column)?.startsWith("asset:")) {
        continue;
      }
      const index = columnIndex.get(column);
      if (index === undefined) {
        continue;
      }
      for (const row of table.rows) {
        const cell = row[index];
        if (typeof cell === "string" && cell !== "") {
          keys.add(cell);
        }
      }
    }
    return Array.from(keys);
  }, [group, labelColumn, valueKinds, columnIndex, table.rows]);
  const assetNames = useAssetNames(assetKeys);

  const selection = useAnalysisSelection();
  const stageSelection = useAnalysisStageSelection();

  const [selected, setSelected] = useState<SelectedSlice | null>(null);
  const [prevStageId, setPrevStageId] = useState(stageId);
  if (stageId !== prevStageId) {
    setPrevStageId(stageId);
    setSelected(null);
  }
  // 绑定变化时重置瞬态选择（不随工作流保存）。
  const bindingKey = [group, value, labelColumn].join("|");
  const [prevBindingKey, setPrevBindingKey] = useState(bindingKey);
  if (bindingKey !== prevBindingKey) {
    setPrevBindingKey(bindingKey);
    setSelected(null);
  }

  const missingColumn = [group, value, ...(labelColumn === "" ? [] : [labelColumn])].find(
    (name) => name !== "" && !columnIndex.has(name),
  );
  const valueType = typeOf.get(value) ?? "";
  const chartReady =
    group !== "" &&
    value !== "" &&
    missingColumn === undefined &&
    (valueType === "int" || valueType === "float");

  const formatValue = useCallback(
    (column: string, cell: unknown) =>
      formatCell(cell, typeOf.get(column), valueKinds.get(column), assetNames),
    [typeOf, valueKinds, assetNames],
  );

  const data = useMemo(
    () =>
      chartReady
        ? buildPieChartData(
            table,
            { group, value, label: labelColumn === "" ? null : labelColumn },
            formatValue,
          )
        : null,
    [chartReady, table, group, value, labelColumn, formatValue],
  );

  const handleSliceClick = useCallback(
    (seriesIndex: number, dataIndex: number) => {
      if (data === null || seriesIndex !== 0) {
        return;
      }
      const slice = data.slices[dataIndex];
      if (slice === undefined || slice.rowIndexes.length === 0) {
        return;
      }
      const isSame = selected !== null && selected.dataIndex === dataIndex;
      setSelected(isSame ? null : { dataIndex });
      if (isSame) {
        stageSelection?.select(node.id, null);
        selection?.select(node.id, null);
        return;
      }
      if (selection === null) {
        return;
      }
      const stageContextId =
        stageId === undefined ? null : stageSelection?.contextIdFor(node.region_id ?? "") ?? null;
      const groupIndex = columnIndex.get(group);
      const firstRow = table.rows[slice.rowIndexes[0]];
      if (
        stageContextId !== null &&
        groupIndex !== undefined &&
        firstRow !== undefined &&
        stageSelection !== null
      ) {
        stageSelection.select(node.id, {
          groupColumns: [group],
          groupValues: [firstRow[groupIndex]],
        });
        return;
      }
      selection.select(node.id, isSame ? null : tableRowsByIndex(table, slice.rowIndexes));
    },
    [
      data,
      table,
      selected,
      selection,
      stageSelection,
      stageId,
      columnIndex,
      group,
      node.id,
      node.region_id,
    ],
  );

  const option = useMemo(
    () =>
      buildPieChartOption(data ?? { slices: [] }, {
        selected,
        formatValue: (cell) => formatCell(cell, valueType),
      }),
    [data, selected, valueType],
  );

  const containerRef = useRef<HTMLDivElement | null>(null);
  useEChartsView(containerRef, chartReady ? option : null, handleSliceClick);

  if (group === "" || value === "") {
    return (
      <div className="analysis-view-state">
        {config === null
          ? "直连视图未找到可用的默认分组列与数值列"
          : "饼图配置未就绪"}
      </div>
    );
  }
  if (missingColumn !== undefined) {
    return (
      <div className="analysis-view-state analysis-view-error">
        绑定列不在上游表中：{missingColumn}
      </div>
    );
  }
  if (valueType !== "int" && valueType !== "float") {
    return (
      <div className="analysis-view-state analysis-view-error">值列必须是数值列：{value}</div>
    );
  }

  return (
    <div className="analysis-chart-view">
      <div
        className="analysis-chart"
        ref={containerRef}
        role="img"
        aria-label={`饼图：分组=${group}，值=${value}`}
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
