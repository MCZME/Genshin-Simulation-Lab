/** 限制行数节点：卡片直编。 */

import type { EditorProps } from "./context";

const LIMIT_MAX = 10_000;

export function LimitEditor({ node, onChange }: EditorProps) {
  const count = node.params.count;
  const raw = typeof count === "number" ? String(count) : "";
  const valid =
    typeof count === "number" && Number.isInteger(count) && count >= 1 && count <= LIMIT_MAX;
  return (
    <div className="limit-inline">
      <label className="limit-line">
        <span>保留前</span>
        <input
          type="number"
          min={1}
          max={LIMIT_MAX}
          step={1}
          value={raw}
          placeholder="1000"
          onChange={(event) => {
            const next = { ...node.params };
            if (event.target.value === "") {
              delete next.count;
            } else {
              next.count = Number(event.target.value);
            }
            onChange(next);
          }}
        />
        <span>行</span>
      </label>
      {!valid && <p className="filter-row-error">请输入 1–10000 的整数</p>}
    </div>
  );
}
