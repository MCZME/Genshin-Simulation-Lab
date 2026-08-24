/** 分析视图节点内容区：消费处理节点结果表并渲染。 */

import type { WorkflowNode } from "../../workflow/types";
import type { AnalysisNodeResult } from "../../workflow/analysis_runner";

export function AnalysisViewBody({
  node,
  result,
}: {
  node: WorkflowNode;
  result: AnalysisNodeResult | undefined;
}) {
  if (result === undefined || result.status === "idle") {
    return <div className="analysis-view-state">未执行（连接数据后运行工作流）</div>;
  }
  if (result.status === "loading") {
    return <div className="analysis-view-state">加载中…</div>;
  }
  if (result.status === "stale") {
    return <div className="analysis-view-state">结果已过期</div>;
  }
  if (result.status === "error") {
    return <div className="analysis-view-state analysis-view-error">{result.error}</div>;
  }
  const table = result.table;
  if (table === undefined || table.rows.length === 0) {
    return <div className="analysis-view-state">无数据</div>;
  }
  switch (node.kind) {
    case "member_table":
      return <MemberTable columns={table.columns.map((column) => column.name)} rows={table.rows} />;
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

function MemberTable({ columns, rows }: { columns: string[]; rows: unknown[][] }) {
  return (
    <div className="analysis-member-table">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}>{formatCell(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return String(value);
}
