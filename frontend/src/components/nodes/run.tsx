import { FieldRow, NumberField } from "../common/fields";
import { useRunState } from "../run_state_context";
import { BATCH_STATUS_LABELS } from "../../state/run_state";
import type { RunMemberStatus } from "../../api/client";
import type { NodeEditorProps } from "./common";
import { asNumber, firstError } from "./common";
export function RunOptionsEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="最大帧数" error={firstError(fieldErrors, "max_frames")}>
        <NumberField
          value={asNumber(params.max_frames)}
          min={1}
          onChange={(value) => onChange({ ...params, max_frames: value ?? 18000 })}
        />
      </FieldRow>
    </div>
  );
}

/** 进度条分段与计数的展示顺序；后端成员状态之外的状态不进入统计。 */
const PROGRESS_STATES = ["completed", "failed", "cancelled", "running", "stopping", "queued"] as const;

const PROGRESS_STATE_LABELS: Record<(typeof PROGRESS_STATES)[number], string> = {
  completed: "完成",
  failed: "失败",
  cancelled: "已取消",
  running: "运行中",
  stopping: "停止中",
  queued: "排队",
};

interface ProgressSegment {
  state: (typeof PROGRESS_STATES)[number];
  count: number;
  percent: number;
}

function progressSegments(members: RunMemberStatus[]): ProgressSegment[] {
  const total = members.length;
  return PROGRESS_STATES.map((state) => {
    const count = members.filter((member) => member.state === state).length;
    return {
      state,
      count,
      percent: total === 0 ? 0 : (count / total) * 100,
    };
  }).filter((segment) => segment.count > 0);
}

function progressCountsText(members: RunMemberStatus[]): string {
  const counts = Object.fromEntries(
    PROGRESS_STATES.map((state) => [state, members.filter((member) => member.state === state).length]),
  ) as Record<(typeof PROGRESS_STATES)[number], number>;
  const parts = [`完成 ${counts.completed}/${members.length}`];
  for (const state of PROGRESS_STATES) {
    if (state !== "completed" && counts[state] > 0) {
      parts.push(`${PROGRESS_STATE_LABELS[state]} ${counts[state]}`);
    }
  }
  return parts.join(" · ");
}

/**
 * 模拟节点编辑器：只展示本节点对应的批次视图（一个模拟节点 = 一个批次，决策 2.32）。
 * 节点定位为「模拟入口 + 批次监控」（决策 2.38，2026-08-23 修订）：批次进度以分段
 * 进度条 + 聚合计数呈现；失败成员保留可见错误行（组装期失败不落结果库，节点是
 * 其错误信息的唯一出口）；不显示成员标签、跳转与指标数值。
 */
export function SimulationEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const { runState, onCancelBatch } = useRunState();
  const batch = runState.run?.batches.find((item) => item.nodeId === node.id) ?? null;
  const params = node.params;
  const segments = batch === null ? [] : progressSegments(batch.members);
  const countsText = batch === null ? "" : progressCountsText(batch.members);
  const failedMembers = batch === null ? [] : batch.members.filter((member) => member.state === "failed");
  const terminalCount =
    batch === null
      ? 0
      : batch.members.filter(
          (member) => member.state === "completed" || member.state === "failed" || member.state === "cancelled",
        ).length;
  return (
    <div className="simulation-editor">
      <FieldRow
        label="并发度"
        error={firstError(fieldErrors, "concurrency")}
      >
        <NumberField
          value={asNumber(params.concurrency)}
          min={1}
          max={16}
          emptyLabel="自动"
          onChange={(value) => {
            const next = { ...params };
            if (value === null) {
              delete next.concurrency;
            } else {
              next.concurrency = value;
            }
            onChange(next);
          }}
        />
      </FieldRow>
      {batch === null ? (
        <p className="node-note">连接配置区域边界后运行批次</p>
      ) : (
        <>
          <div className="batch-status-line">
            <span className={`status-badge status-${batch.status}`}>
              {BATCH_STATUS_LABELS[batch.status]}
            </span>
            <span className="batch-counts">{countsText}</span>
          </div>
          <div
            className="batch-progress"
            role="progressbar"
            aria-label="批次成员进度"
            aria-valuemin={0}
            aria-valuemax={batch.members.length}
            aria-valuenow={terminalCount}
          >
            {segments.map((segment) => (
              <span
                key={segment.state}
                className={`batch-progress-segment seg-${segment.state}`}
                style={{ width: `${segment.percent}%` }}
              />
            ))}
          </div>
          {failedMembers.length > 0 && (
            <ul className="member-failures">
              {failedMembers.map((member) => (
                <li className="member-failure" key={member.item_id}>
                  <span className="member-failure-id">{member.item_id}</span>
                  <span className="member-failure-text">
                    {member.error_message ?? member.error_code ?? "未知错误"}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {batch.error !== null && <p className="node-note danger">{batch.error}</p>}
          {(batch.status === "submitting" || batch.status === "running") && (
            <button
              type="button"
              className="text-button danger"
              onClick={() => onCancelBatch(node.id)}
            >
              取消本批
            </button>
          )}
        </>
      )}
    </div>
  );
}

export function UnknownEditor({ node }: NodeEditorProps) {
  return <p className="node-note">未注册编辑器：{node.kind}</p>;
}
