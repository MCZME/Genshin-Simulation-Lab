import { COLORS } from "../../theme/tokens";
import type { RunState } from "../../state/run_state";

export interface ResultPanelProps {
  runState: RunState;
}

export function ResultPanel({ runState }: ResultPanelProps) {
  const members = runState.members;
  return (
    <section className="result-panel">
      <h2 className="panel-title">运行结果{runningLabel(runState.state)}</h2>
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
          {members.map((member) => {
            const metrics = runState.metrics[member.item_id];
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
                  {metrics?.total_damage != null ? formatNumber(metrics.total_damage.value) : "—"}
                </td>
                <td className="result-number">
                  {metrics?.dps != null ? formatNumber(metrics.dps.value) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {members.length === 0 && <p className="panel-empty">还没有运行记录</p>}
    </section>
  );
}

function runningLabel(state: string | null): string {
  return state === null ? "" : ` · ${state}`;
}

function formatNumber(value: number): string {
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
}
