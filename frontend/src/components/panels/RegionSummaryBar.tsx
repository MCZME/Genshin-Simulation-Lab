import type { CompileResult } from "../../workflow/types";

export interface RegionSummaryBarProps {
  compiles: CompileResult[];
}

export function RegionSummaryBar({ compiles }: RegionSummaryBarProps) {
  return (
    <div className="region-summary-bar">
      {compiles.length === 0 && <span className="region-summary-empty">还没有配置区域</span>}
      {compiles.map((result) => {
        const errors = result.diagnostics.filter((item) => item.severity === "error").length;
        const warnings = result.diagnostics.filter((item) => item.severity === "warning").length;
        return (
          <span className="region-summary" key={result.region_id}>
            <span className="region-summary-name">{result.region_id}</span>
            {result.ok ? (
              <span className="region-summary-count">{result.members.length} 个成员</span>
            ) : (
              <span className="region-summary-error">阻止运行</span>
            )}
            {errors > 0 && <span className="region-summary-error">{errors} 错误</span>}
            {warnings > 0 && <span className="region-summary-warning">{warnings} 警告</span>}
          </span>
        );
      })}
    </div>
  );
}
