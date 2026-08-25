/** 分析视图节点内容区：消费处理节点结果表并渲染。 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { AnalysisNodeResult } from "../../workflow/analysis_runner";
import { connectedConfigNode, type AnalysisTableResult } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";

const ROW_HEIGHT = 28;
/** 超过该行数启用窗口化渲染，避免大批量一次性铺 DOM。 */
const VIRTUALIZE_THRESHOLD = 200;
const MAX_RENDERED_ROWS = 10000;
const SORT_ORDERS = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"];

type SortDirection = "asc" | "desc";
interface SortKey {
  column: string;
  direction: SortDirection;
}
type HighlightMode = "max" | "min";

export function AnalysisViewBody({
  node,
  result,
  definition,
  onLocateNode,
}: {
  node: WorkflowNode;
  result: AnalysisNodeResult | undefined;
  definition: WorkflowDefinition;
  onLocateNode?: (nodeId: string) => void;
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
    return <div className="analysis-view-state">结果已过期</div>;
  }
  if (result.status === "error") {
    return <div className="analysis-view-state analysis-view-error">{result.error}</div>;
  }
  const table = result.table;
  if (table === undefined || table.rows.length === 0) {
    return <div className="analysis-view-state">上游为空（无匹配数据）</div>;
  }
  switch (node.kind) {
    case "member_table":
      return <MemberTable node={node} definition={definition} table={table} />;
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
}: {
  node: WorkflowNode;
  definition: WorkflowDefinition;
  table: AnalysisTableResult;
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
        <table>
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
                const classNames = [
                  "member-th",
                  isData ? "data" : "condition",
                  isDataStart ? "data-start" : "",
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
            {visibleRows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {order.map((column, cellIndex) => {
                  const index = columnIndex.get(column);
                  const value = index === undefined ? null : row[index];
                  const isData = dataSet.has(column);
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
                    highlightClass,
                  ]
                    .filter((item) => item !== "")
                    .join(" ");
                  return (
                    <td key={column} className={cellClass}>
                      {formatCell(value, typeOf.get(column))}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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

/** 单元格格式化：int 千分位、float 两位小数去尾零、空值显示“—”。 */
export function formatCell(value: unknown, type?: string): string {
  if (value === null || value === undefined) {
    return "—";
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
