import { FieldRow, NumberField } from "../common/fields";
import { useRunState } from "../run_state_context";
import { BATCH_STATUS_LABELS } from "../../state/run_state";
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

/**
 * 模拟节点编辑器：只展示本节点对应的批次视图（一个模拟节点 = 一个批次，决策 2.32）。
 */
export function SimulationEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const { runState, onCancelRun } = useRunState();
  const batch = runState.run?.batches.find((item) => item.nodeId === node.id) ?? null;
  const params = node.params;
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
            {batch.state !== null && <span className="batch-run-state">{batch.state}</span>}
          </div>
          <ul className="member-list">
            {batch.members.map((member) => (
              <li className="member-row" key={member.item_id}>
                <span className="member-id">{member.item_id}</span>
                <span className={`status-badge status-${member.state}`}>{member.state}</span>
              </li>
            ))}
          </ul>
          {batch.error !== null && <p className="node-note danger">{batch.error}</p>}
          {(batch.status === "submitting" || batch.status === "running") && (
            <button type="button" className="text-button danger" onClick={onCancelRun}>
              取消整批
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
