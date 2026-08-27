/** 分析视图节点内容区：消费处理节点结果表并渲染。 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { AnalysisNodeResult } from "../../workflow/analysis_runner";
import {
  computeAnalysisShapes,
  connectedConfigNode,
  viewInputShape,
  type AnalysisTableResult,
} from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import {
  DAMAGE_TYPE_LABELS,
  ELEMENT_LABELS,
  EVENT_TYPE_LABELS,
  RUN_STATE_LABELS,
  WEAPON_LABELS,
} from "../../theme/elements";
import { useAnalysisSchemaCatalog } from "../analysis_context";
import { useAssetNames } from "./useAssetNames";
import { MIN_VIEW_WIDTH } from "../../workflow/view_size";

const ROW_HEIGHT = 28;
/** 超过该行数启用窗口化渲染，避免大批量一次性铺 DOM。 */
const VIRTUALIZE_THRESHOLD = 200;
const MAX_RENDERED_ROWS = 10000;
const SORT_ORDERS = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"];
/** 列宽估算：单元格左右内边距合计（px）。 */
const CELL_PADDING = 16;
const MIN_COLUMN_WIDTH = 72;
const MAX_COLUMN_WIDTH = 240;

type SortDirection = "asc" | "desc";
interface SortKey {
  column: string;
  direction: SortDirection;
}
type HighlightMode = "max" | "min";

const ENUM_LABEL_MAPS: Record<string, Record<string, string>> = {
  "enum:element": ELEMENT_LABELS,
  "enum:weapon_type": WEAPON_LABELS,
  "enum:run_state": RUN_STATE_LABELS,
  "enum:event_type": EVENT_TYPE_LABELS,
  "enum:damage_type": DAMAGE_TYPE_LABELS,
};

export function AnalysisViewBody({
  node,
  result,
  definition,
  onLocateNode,
  viewWidth,
  onFitChange,
}: {
  node: WorkflowNode;
  result: AnalysisNodeResult | undefined;
  definition: WorkflowDefinition;
  onLocateNode?: (nodeId: string) => void;
  /** 节点内容区可用宽度（px）；供表格视图计算裁剪提示。 */
  viewWidth?: number;
  /** 表格视图布局变化时上报：内容自然宽与被隐藏列数。 */
  onFitChange?: (info: MemberTableFitInfo) => void;
}) {
  const hasDataInput = definition.edges.some(
    (edge) => edge.target_node_id === node.id && edge.target_port_id === "in",
  );
  if (!hasDataInput) {
    return <div className="analysis-view-state">未连接数据源（从取数或算子连线接入）</div>;
  }
  if (node.kind === "member_table") {
    const config = connectedConfigNode(definition, node.id, "table_config");
    if (config === null) {
      return <div className="analysis-view-state">缺少表格配置（连接表格配置节点）</div>;
    }
    const condition = asStringArray(config.params.condition_columns);
    const data = asStringArray(config.params.data_columns);
    if (condition.length === 0 && data.length === 0) {
      return (
        <div className="analysis-view-state">
          <span>表格配置未绑定列</span>
          {onLocateNode !== undefined && (
            <button
              type="button"
              className="text-button"
              onClick={() => onLocateNode(config.id)}
            >
              打开表格配置
            </button>
          )}
        </div>
      );
    }
  }
  if (result === undefined || result.status === "idle") {
    return <div className="analysis-view-state">未执行（连接数据后运行工作流）</div>;
  }
  if (result.status === "loading") {
    return (
      <div className="analysis-view-state analysis-view-loading" role="status">
        加载中…
      </div>
    );
  }
  if (result.status === "stale") {
    if (result.table !== undefined) {
      return (
        <div className="analysis-view-stale">
          <div className="analysis-stale-banner">结果已过期，正在刷新…</div>
          {renderAnalysisTable(node, definition, result.table)}
        </div>
      );
    }
    return <div className="analysis-view-state">结果已过期</div>;
  }
  if (result.status === "error") {
    return <div className="analysis-view-state analysis-view-error">{result.error}</div>;
  }
  const table = result.table;
  if (table === undefined || table.rows.length === 0) {
    return <div className="analysis-view-state">上游为空（无匹配数据）</div>;
  }
  return renderAnalysisTable(node, definition, table, viewWidth, onFitChange);
}

function renderAnalysisTable(
  node: WorkflowNode,
  definition: WorkflowDefinition,
  table: AnalysisTableResult,
  viewWidth?: number,
  onFitChange?: (info: MemberTableFitInfo) => void,
) {
  switch (node.kind) {
    case "member_table":
      return (
        <MemberTable
          node={node}
          definition={definition}
          table={table}
          viewWidth={viewWidth}
          onFitChange={onFitChange}
        />
      );
    case "timeline":
      return <div className="analysis-view-state">单场时间轴（后续实现）</div>;
    case "pie":
      return <div className="analysis-view-state">占比饼图（后续实现）</div>;
    case "bar":
      return <div className="analysis-view-state">指标柱状图（后续实现）</div>;
    default:
      return null;
  }
}

function MemberTable({
  node,
  definition,
  table,
  viewWidth,
  onFitChange,
}: {
  node: WorkflowNode;
  definition: WorkflowDefinition;
  table: AnalysisTableResult;
  viewWidth?: number;
  onFitChange?: (info: MemberTableFitInfo) => void;
}) {
  const config = useMemo(
    () => connectedConfigNode(definition, node.id, "table_config"),
    [definition, node.id],
  );
  const conditionColumns = useMemo(
    () => asStringArray(config?.params.condition_columns),
    [config],
  );
  const dataColumns = useMemo(() => asStringArray(config?.params.data_columns), [config]);
  const columnIndex = useMemo(
    () => new Map(table.columns.map((column, index) => [column.name, index])),
    [table.columns],
  );
  const typeOf = useMemo(
    () => new Map(table.columns.map((column) => [column.name, column.type])),
    [table.columns],
  );
  const catalog = useAnalysisSchemaCatalog();
  const shapes = useMemo(
    () => computeAnalysisShapes(definition, catalog),
    [definition, catalog],
  );
  const inputShape = useMemo(
    () => viewInputShape(shapes, definition, node.id),
    [shapes, definition, node.id],
  );
  const valueKinds = useMemo(
    () => new Map(inputShape.map((column) => [column.name, column.valueKind ?? ""])),
    [inputShape],
  );

  const defaultOrder = useMemo(() => {
    const present = new Set(table.columns.map((column) => column.name));
    return [...conditionColumns, ...dataColumns].filter((name) => present.has(name));
  }, [conditionColumns, dataColumns, table.columns]);

  const [order, setOrder] = useState<string[]>(defaultOrder);
  const [conditionSort, setConditionSort] = useState<SortKey[]>([]);
  const [dataSort, setDataSort] = useState<SortKey | null>(null);
  const [highlights, setHighlights] = useState<Record<string, HighlightMode>>({});
  const [menuColumn, setMenuColumn] = useState<string | null>(null);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [windowRange, setWindowRange] = useState({ start: 0, end: 0 });
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // 绑定变化时回到默认查看状态（排序/高亮/列顺序均为瞬态，不随工作流保存）。
  const bindingKey = defaultOrder.join("|");
  const [prevBindingKey, setPrevBindingKey] = useState(bindingKey);
  if (bindingKey !== prevBindingKey) {
    setPrevBindingKey(bindingKey);
    setOrder(defaultOrder);
    setConditionSort([]);
    setDataSort(null);
    setHighlights({});
    setMenuColumn(null);
  }

  const virtualizing = table.rows.length > VIRTUALIZE_THRESHOLD;
  useEffect(() => {
    if (!virtualizing) {
      return;
    }
    const el = scrollRef.current;
    if (el === null) {
      return;
    }
    const update = () => {
      const start = Math.max(0, Math.floor(el.scrollTop / ROW_HEIGHT) - 4);
      const count = Math.ceil(el.clientHeight / ROW_HEIGHT) + 8;
      setWindowRange({ start, end: Math.min(table.rows.length, start + count) });
    };
    const frame = window.requestAnimationFrame(update);
    el.addEventListener("scroll", update);
    window.addEventListener("resize", update);
    return () => {
      window.cancelAnimationFrame(frame);
      el.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [virtualizing, table.rows.length]);

  const sortKeys = useMemo(
    () => [...conditionSort, ...(dataSort === null ? [] : [dataSort])],
    [conditionSort, dataSort],
  );
  const sortedRows = useMemo(
    () => sortRows(table.rows, sortKeys, columnIndex),
    [table.rows, sortKeys, columnIndex],
  );
  const visibleRows = virtualizing
    ? sortedRows.slice(windowRange.start, windowRange.end)
    : sortedRows;

  const assetKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const column of conditionColumns) {
      const kind = valueKinds.get(column) ?? "";
      if (!kind.startsWith("asset:")) {
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
  }, [conditionColumns, valueKinds, columnIndex, table.rows]);
  const assetNames = useAssetNames(assetKeys);

  const layout = useMemo(
    () =>
      estimateMemberTableLayout({
        order,
        rows: table.rows,
        columnIndex,
        typeOf,
        valueKinds,
        assetNames,
        dataColumns,
      }),
    [order, table.rows, columnIndex, typeOf, valueKinds, assetNames, dataColumns],
  );
  // 卡片为 border-box：内容自然宽与卡片宽相等时视为恰好容纳，不显示渐隐。
  const contentWidth = Math.max(0, viewWidth ?? MIN_VIEW_WIDTH);
  const hiddenColumns = useMemo(
    () => countHiddenColumns(layout.widths, contentWidth),
    [layout.widths, contentWidth],
  );
  const clipped = layout.fitWidth > contentWidth;
  const fitInfo = useMemo(
    () => ({ fitWidth: layout.fitWidth, hiddenColumns }),
    [layout.fitWidth, hiddenColumns],
  );
  useEffect(() => {
    onFitChange?.(fitInfo);
  }, [fitInfo, onFitChange]);

  const highlightValues = useMemo(() => {
    const result = new Map<string, number>();
    for (const [column, mode] of Object.entries(highlights)) {
      const index = columnIndex.get(column);
      if (index === undefined) {
        continue;
      }
      let best: number | null = null;
      for (const row of table.rows) {
        const value = row[index];
        if (typeof value !== "number" || !Number.isFinite(value)) {
          continue;
        }
        if (best === null || (mode === "max" ? value > best : value < best)) {
          best = value;
        }
      }
      if (best !== null) {
        result.set(column, best);
      }
    }
    return result;
  }, [highlights, columnIndex, table.rows]);

  const dataSet = new Set(dataColumns);
  const hasSort = conditionSort.length > 0 || dataSort !== null;
  const clearSort = () => {
    setConditionSort([]);
    setDataSort(null);
  };

  const handleConditionHeaderClick = (column: string) => {
    setMenuColumn(null);
    setConditionSort((current) => {
      const existing = current.find((key) => key.column === column);
      if (existing === undefined) {
        return [...current, { column, direction: "asc" }];
      }
      return current.map((key) =>
        key.column === column
          ? { column, direction: key.direction === "asc" ? "desc" : "asc" }
          : key,
      );
    });
  };

  const handleDataHeaderClick = (column: string) => {
    setMenuColumn(null);
    setDataSort((current) => {
      if (current === null || current.column !== column) {
        return { column, direction: "asc" };
      }
      return { column, direction: current.direction === "asc" ? "desc" : "asc" };
    });
  };

  const moveColumn = (from: number, to: number) => {
    setOrder((current) => {
      if (
        from === to ||
        from < 0 ||
        to < 0 ||
        from >= current.length ||
        to >= current.length
      ) {
        return current;
      }
      const next = [...current];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
  };

  const setHighlight = (column: string, mode: HighlightMode | null) => {
    setHighlights((current) => {
      const next = { ...current };
      if (mode === null) {
        delete next[column];
      } else {
        next[column] = mode;
      }
      return next;
    });
    setMenuColumn(null);
  };

  return (
    <div className="analysis-member-table">
      <div className="analysis-member-toolbar">
        {hasSort && (
          <button type="button" className="text-button" onClick={clearSort}>
            清除排序
          </button>
        )}
      </div>
      <div className="analysis-member-scroll" ref={scrollRef}>
        <table style={{ width: layout.fitWidth }}>
          <thead>
            <tr>
              {order.map((column, index) => {
                const type = typeOf.get(column) ?? "";
                const isData = dataSet.has(column);
                const isNumeric = type === "int" || type === "float";
                const conditionOrder = conditionSort.findIndex(
                  (key) => key.column === column,
                );
                const direction =
                  isData && dataSort?.column === column
                    ? dataSort.direction
                    : conditionOrder >= 0
                      ? conditionSort[conditionOrder]?.direction
                      : undefined;
                const isDataStart =
                  isData && (index === 0 || !dataSet.has(order[index - 1]));
                const sorted = isData
                  ? dataSort?.column === column
                  : conditionOrder >= 0;
                const classNames = [
                  "member-th",
                  isData ? "data" : "condition",
                  isDataStart ? "data-start" : "",
                  sorted ? "sorted" : "",
                  dragIndex !== null && dragIndex !== index ? "drop-target" : "",
                ]
                  .filter((item) => item !== "")
                  .join(" ");
                return (
                  <th
                    key={column}
                    draggable
                    title={`${column}（${type}）`}
                    className={classNames}
                    style={{ width: layout.widths[index] }}
                    onDragStart={() => setDragIndex(index)}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={() => moveColumn(dragIndex ?? index, index)}
                    onDragEnd={() => setDragIndex(null)}
                    onClick={() =>
                      isData
                        ? handleDataHeaderClick(column)
                        : handleConditionHeaderClick(column)
                    }
                  >
                    <span className="member-th-name">{column}</span>
                    {conditionOrder >= 0 && (
                      <span className="member-sort-order">
                        {SORT_ORDERS[conditionOrder] ?? `#${conditionOrder + 1}`}
                      </span>
                    )}
                    {direction !== undefined && (
                      <span className="member-sort-direction">
                        {direction === "asc" ? "▲" : "▼"}
                      </span>
                    )}
                    {isData && isNumeric && (
                      <span
                        className="member-th-menu"
                        title="列操作"
                        onClick={(event) => {
                          event.stopPropagation();
                          setMenuColumn(menuColumn === column ? null : column);
                        }}
                      >
                        ▾
                      </span>
                    )}
                    {menuColumn === column && (
                      <span className="member-th-dropdown">
                        <button
                          type="button"
                          onClick={() => setHighlight(column, "max")}
                        >
                          高亮最大
                        </button>
                        <button
                          type="button"
                          onClick={() => setHighlight(column, "min")}
                        >
                          高亮最小
                        </button>
                        <button
                          type="button"
                          onClick={() => setHighlight(column, null)}
                        >
                          清除高亮
                        </button>
                      </span>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, rowIndex) => {
              // 窗口化渲染时 tbody 只含可见切片，斑马纹必须用绝对行号，
              // 避免滚动时同一行的明暗翻转。
              const absoluteRowIndex = virtualizing
                ? windowRange.start + rowIndex
                : rowIndex;
              return (
                <tr
                  key={rowIndex}
                  className={absoluteRowIndex % 2 === 1 ? "stripe" : ""}
                >
                  {order.map((column, cellIndex) => {
                    const index = columnIndex.get(column);
                    const value = index === undefined ? null : row[index];
                    const isData = dataSet.has(column);
                    const isNull =
                      value === null ||
                      value === undefined ||
                      (typeof value === "number" && !Number.isFinite(value));
                    const isDataStart =
                      isData && (cellIndex === 0 || !dataSet.has(order[cellIndex - 1]));
                    const highlightClass =
                      dataSet.has(column) &&
                      highlights[column] !== undefined &&
                      highlightValues.get(column) === value
                        ? `hl-${highlights[column]}`
                        : "";
                    const cellClass = [
                      isData ? "data" : "condition",
                      isDataStart ? "data-start" : "",
                      isNull ? "cell-null" : "",
                      highlightClass,
                    ]
                      .filter((item) => item !== "")
                      .join(" ");
                    return (
                      <td
                        key={column}
                        className={cellClass}
                        style={{ width: layout.widths[cellIndex] }}
                      >
                        {formatCell(
                          value,
                          typeOf.get(column),
                          valueKinds.get(column),
                          assetNames,
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {clipped && (
        <div
          className="analysis-member-fade"
          aria-label={`还有 ${hiddenColumns} 列被隐藏，拖宽查看`}
        />
      )}
      <div className="analysis-member-footer">
        <span>共 {table.rows.length} 行</span>
        {table.truncated && (
          <span className="analysis-member-truncated">
            仅显示前 {MAX_RENDERED_ROWS} 行
          </span>
        )}
      </div>
    </div>
  );
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

export interface MemberTableFitInfo {
  /** 全部绑定列完整显示所需的内容自然宽（px）。 */
  fitWidth: number;
  /** 当前内容区内被裁剪隐藏的列数（含部分可见列之外的列）。 */
  hiddenColumns: number;
}

/** 按 12px 字号粗略估算文本像素宽：CJK 全宽、数字窄、其余按字母宽度。 */
export function estimateTextWidth(text: string): number {
  let width = 0;
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0;
    if (ch === " ") {
      width += 4;
    } else if (
      (code >= 0x2e80 && code <= 0x9fff) ||
      (code >= 0xf900 && code <= 0xfaff) ||
      (code >= 0xff00 && code <= 0xffef)
    ) {
      width += 12;
    } else if (
      (code >= 0x30 && code <= 0x39) ||
      ch === "," ||
      ch === "." ||
      ch === "-"
    ) {
      width += 7;
    } else {
      width += 7.5;
    }
  }
  return Math.ceil(width);
}

/**
 * 估算表格视图各列宽度：表头文本与全部单元格格式化文本取宽者，
 * 数据列额外预留排序/下拉图标空间；每列夹持在上下限内。
 */
export function estimateMemberTableLayout(input: {
  order: string[];
  rows: unknown[][];
  columnIndex: Map<string, number>;
  typeOf: Map<string, string>;
  valueKinds: Map<string, string>;
  assetNames: Map<string, string>;
  dataColumns: string[];
}): { widths: number[]; fitWidth: number } {
  const dataSet = new Set(input.dataColumns);
  const widths = input.order.map((column) => {
    const index = input.columnIndex.get(column);
    const type = input.typeOf.get(column);
    const valueKind = input.valueKinds.get(column) ?? "";
    const headerWidth =
      estimateTextWidth(column) + (dataSet.has(column) ? 28 : 8);
    let cellWidth = 0;
    if (index !== undefined) {
      for (const row of input.rows) {
        const text = formatCell(row[index], type, valueKind, input.assetNames);
        cellWidth = Math.max(cellWidth, estimateTextWidth(text));
      }
    }
    const raw = Math.max(headerWidth, cellWidth) + CELL_PADDING;
    return clampWidth(raw);
  });
  return {
    widths,
    fitWidth: widths.reduce((sum, width) => sum + width, 0),
  };
}

function clampWidth(width: number): number {
  return Math.min(MAX_COLUMN_WIDTH, Math.max(MIN_COLUMN_WIDTH, width));
}

/** 计算超出内容宽被裁剪隐藏的列数：整列起点已超出可见区即计入隐藏。 */
export function countHiddenColumns(widths: number[], contentWidth: number): number {
  let used = 0;
  let hidden = 0;
  for (const width of widths) {
    if (used + width > contentWidth) {
      hidden += 1;
    }
    used += width;
  }
  return hidden;
}

/**
 * 单元格格式化：按 valueKind 解析显示名（资产/枚举），
 * 数值沿用 int 千分位、float 两位小数去尾零，空值显示“—”。
 */
export function formatCell(
  value: unknown,
  type?: string,
  valueKind?: string,
  assetNames?: Map<string, string>,
): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "string" && valueKind !== undefined && valueKind !== "") {
    if (valueKind.startsWith("asset:")) {
      return assetNames?.get(value) ?? value;
    }
    const map = ENUM_LABEL_MAPS[valueKind];
    if (map !== undefined) {
      return map[value] ?? value;
    }
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      return "—";
    }
    if (Number.isInteger(value) && (type === "int" || type === undefined)) {
      return thousands(String(value));
    }
    return formatNumber(trimFloat(value.toFixed(2)));
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
}

function thousands(text: string): string {
  return text.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function formatNumber(text: string): string {
  const parts = text.split(".");
  const integer = thousands(parts[0]);
  return parts.length > 1 ? `${integer}.${parts[1]}` : integer;
}

function trimFloat(text: string): string {
  return text.includes(".") ? text.replace(/\.?0+$/, "") : text;
}

/** 单元格比较：空值恒排在最后，方向由调用方处理。 */
export function compareCells(left: unknown, right: unknown): number {
  if (left === null || left === undefined) {
    return right === null || right === undefined ? 0 : 1;
  }
  if (right === null || right === undefined) {
    return -1;
  }
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  if (typeof left === "boolean" && typeof right === "boolean") {
    return Number(left) - Number(right);
  }
  return String(left).localeCompare(String(right), "zh-CN");
}

/** 按排序键顺序排序行（条件列组合 + 数据列单列）。 */
export function sortRows(
  rows: unknown[][],
  keys: SortKey[],
  columnIndex: Map<string, number>,
): unknown[][] {
  if (keys.length === 0) {
    return rows;
  }
  const indexes = rows.map((_, index) => index);
  indexes.sort((left, right) => {
    for (const key of keys) {
      const index = columnIndex.get(key.column);
      if (index === undefined) {
        continue;
      }
      const cmp = compareCells(rows[left][index], rows[right][index]);
      if (cmp !== 0) {
        return key.direction === "asc" ? cmp : -cmp;
      }
    }
    return left - right;
  });
  return indexes.map((index) => rows[index]);
}
