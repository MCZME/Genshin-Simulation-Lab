import { FieldRow, NumberField } from "../common/fields";
import { isRunTerminal, useRunState } from "../run_state_context";
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

export function SimulationEditor() {
  const { runState, onCancelRun } = useRunState();
  const members = runState.members;
  return (
    <div className="simulation-editor">
      {members.length === 0 ? (
        <p className="node-note">连接配置区域边界后运行批次</p>
      ) : (
        <ul className="member-list">
          {members.map((member) => (
            <li className="member-row" key={member.item_id}>
              <span className="member-id">{member.item_id}</span>
              <span className={`status-badge status-${member.state}`}>{member.state}</span>
            </li>
          ))}
        </ul>
      )}
      {runState.runId !== null && !isRunTerminal(runState.state) && (
        <button type="button" className="text-button danger" onClick={onCancelRun}>
          取消整批
        </button>
      )}
    </div>
  );
}

export function UnknownEditor({ node }: NodeEditorProps) {
  return <p className="node-note">未注册编辑器：{node.kind}</p>;
}
