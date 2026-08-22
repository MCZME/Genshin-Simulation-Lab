import type { CompileResult } from "../../workflow/types";
import type { RegionCheckState } from "../../state/run_state";

export interface RegionSummaryBarProps {
  compiles: CompileResult[];
  regionChecks: Record<string, RegionCheckState>;
  checkingRegionId: string | null;
}

export function RegionSummaryBar({
  compiles,
  regionChecks,
  checkingRegionId,
}: RegionSummaryBarProps) {
  return (
    <div className="region-summary-bar">
      {compiles.length === 0 && <span className="region-summary-empty">还没有配置区域</span>}
      {compiles.map((result) => {
        const errors = result.diagnostics.filter((item) => item.severity === "error").length;
        const warnings = result.diagnostics.filter((item) => item.severity === "warning").length;
        const check =
          checkingRegionId === result.region_id
            ? ({ status: "checking" } as Partial<RegionCheckState>)
            : regionChecks[result.region_id];
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
            {check !== undefined && <span className="region-summary-sep">·</span>}
            {check?.status === "checking" && (
              <span className="region-summary-check checking">检查中…</span>
            )}
            {check?.status === "passed" && (
              <span className="region-summary-check passed" title="后端输入校验全部通过">
                检查通过
              </span>
            )}
            {check?.status === "failed" && (
              <span
                className="region-summary-check failed"
                title={check.error ?? undefined}
              >
                检查未通过{failedSuffix(check)}
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}

function failedSuffix(check: Partial<RegionCheckState>): string {
  if (check.memberResults !== undefined) {
    const failed = check.memberResults.filter((member) => !member.ok).length;
    return failed > 0 ? `（${failed} 成员）` : "";
  }
  return "";
}
