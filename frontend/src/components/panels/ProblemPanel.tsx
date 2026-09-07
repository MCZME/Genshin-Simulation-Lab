import { useState } from "react";
import { COLORS } from "../../theme/tokens";
import type { Diagnostic } from "../../workflow/types";

export interface ProblemPanelProps {
  diagnostics: Diagnostic[];
  onLocate: (diagnostic: Diagnostic) => void;
}

type Filter = "all" | "error" | "warning";

export function ProblemPanel({ diagnostics, onLocate }: ProblemPanelProps) {
  const [filter, setFilter] = useState<Filter>("all");
  const visible = diagnostics.filter(
    (item) => filter === "all" || item.severity === filter,
  );

  return (
    <aside className="tool-panel">
      <div className="panel-filters">
        {(["all", "error", "warning"] as const).map((value) => (
          <button
            type="button"
            key={value}
            className={`filter-button ${filter === value ? "active" : ""}`}
            onClick={() => setFilter(value)}
          >
            {value === "all" ? "全部" : value === "error" ? "错误" : "警告"}
            <span className="filter-count">
              {value === "all"
                ? diagnostics.length
                : diagnostics.filter((item) => item.severity === value).length}
            </span>
          </button>
        ))}
      </div>
      <ul className="problem-list">
        {visible.map((item, index) => (
          <li
            key={`${item.code}-${index}`}
            className="problem-row"
            onClick={() => onLocate(item)}
          >
            <span
              className="problem-severity"
              style={{ background: COLORS.severity[item.severity] }}
            />
            <div className="problem-text">
              <span className="problem-code">{item.code}</span>
              <span className="problem-message">{item.message}</span>
            </div>
          </li>
        ))}
        {visible.length === 0 && <li className="problem-empty">没有问题</li>}
      </ul>
    </aside>
  );
}
