import { COLORS } from "../../theme/tokens";
import {
  BATCH_STATUS_LABELS,
  BUILD_STEP_LABELS,
  PHASE_LABELS,
  type BatchStatus,
  type BuildStepStatus,
  type RunState,
} from "../../state/run_state";

export interface ResultPanelProps {
  runState: RunState;
}

/** 结果面板：渲染执行轨迹（阶段 + 构建切片 + 批次步骤 + 摘要，决策 2.34）。 */
export function ResultPanel({ runState }: ResultPanelProps) {
  const run = runState.run;
  if (run === null) {
    return null;
  }
  return (
    <section className="result-panel">
      <h2 className="panel-title">运行结果 · {PHASE_LABELS[run.phase]}</h2>
      {run.phase === "build_failed" ? (
        <div className="build-errors">
          {run.buildErrors.map((message, index) => (
            <p className="build-error" key={index}>
              {message}
            </p>
          ))}
        </div>
      ) : (
        <div className="run-trace">
          {run.build.map((slice) => (
            <div className="trace-slice" key={`build-${slice.regionId}`}>
              <p className="trace-step trace-slice-title">
                <span className="trace-label">
                  构建 {slice.regionName} · {slice.memberCount} 成员
                </span>
              </p>
              {slice.methods.map((method) => (
                <p
                  className="trace-step trace-method"
                  key={method.nodeId}
                  title={BUILD_STEP_LABELS[method.status]}
                >
                  <span className={`trace-icon ${buildStepTone(method.status)}`}>
                    {buildStepIcon(method.status)}
                  </span>
                  <span className="trace-label">
                    {method.label}
                    {method.paths.length > 0 && (
                      <span className="trace-method-path"> → {method.paths.join("、")}</span>
                    )}
                    {method.variants > 1 && (
                      <span className="trace-method-variants"> ×{method.variants}</span>
                    )}
                    {method.overridden && (
                      <span className="trace-method-overridden">（被覆盖）</span>
                    )}
                  </span>
                </p>
              ))}
            </div>
          ))}
          {run.batches.map((batch) => (
            <div className="trace-batch" key={`batch-${batch.nodeId}`}>
              <p className="trace-step">
                <span className={`trace-icon ${traceTone(batch.status)}`}>
                  {traceIcon(batch.status)}
                </span>
                <span className="trace-label">
                  批次「{batch.name}」 · {BATCH_STATUS_LABELS[batch.status]}
                  {batch.error !== null ? ` · ${batch.error}` : ""}
                </span>
              </p>
              {batch.members.length > 0 && (
                <table className="result-table">
                  <thead>
                    <tr>
                      <th>成员</th>
                      <th>状态</th>
                      <th>总伤害</th>
                      <th>DPS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batch.members.map((member) => {
                      const metrics = batch.metrics[member.item_id];
                      return (
                        <tr key={member.item_id}>
                          <td className="result-item-id">{member.item_id}</td>
                          <td>
                            <span
                              className="status-badge"
                              style={{
                                background:
                                  COLORS.status[member.state as keyof typeof COLORS.status] ??
                                  COLORS.status.queued,
                              }}
                            >
                              {member.state}
                            </span>
                          </td>
                          <td className="result-number">
                            {metrics?.total_damage != null
                              ? formatNumber(metrics.total_damage.value)
                              : "—"}
                          </td>
                          <td className="result-number">
                            {metrics?.dps != null ? formatNumber(metrics.dps.value) : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          ))}
          <p className="trace-step">
            <span className={`trace-icon ${traceTone(run.summaryStatus)}`}>
              {traceIcon(run.summaryStatus)}
            </span>
            <span className="trace-label">结果摘要</span>
          </p>
        </div>
      )}
    </section>
  );
}

function buildStepIcon(status: BuildStepStatus): string {
  switch (status) {
    case "pending":
      return "○";
    case "running":
      return "◐";
    default:
      return status === "done" ? "✓" : "–";
  }
}

function buildStepTone(status: BuildStepStatus): string {
  switch (status) {
    case "done":
      return "ok";
    case "running":
      return "active";
    case "skipped":
      return "muted";
    default:
      return "muted";
  }
}

function traceIcon(status: BatchStatus): string {
  switch (status) {
    case "pending":
      return "○";
    case "submitting":
    case "running":
      return "◐";
    default:
      return status === "completed" ? "✓" : status === "failed" ? "✕" : "–";
  }
}

function traceTone(status: BatchStatus): string {
  switch (status) {
    case "completed":
      return "ok";
    case "failed":
      return "bad";
    case "skipped":
      return "muted";
    default:
      return "active";
  }
}

function formatNumber(value: number): string {
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
}
