/** 连接表节点：卡片直编。 */

import { asString } from "../common";
import { inputShapeFor, type EditorProps } from "./context";

const JOIN_MODE_OPTIONS = [
  {
    value: "inner",
    title: "只保留两边匹配上的行",
    description: "对不上号的行都丢弃",
  },
  {
    value: "left",
    title: "保留主表全部行",
    description: "副表匹配不上的补空，多余的行丢弃",
  },
] as const;

export function JoinEditor({ node, onChange }: EditorProps) {
  const leftShape = inputShapeFor(node.id, "left");
  const rightShape = inputShapeFor(node.id, "right");
  const mode = node.params.mode === "left" ? "left" : "inner";
  const leftKey = asString(node.params.left_key) ?? "";
  const rightKey = asString(node.params.right_key) ?? "";
  const leftType = leftShape.find((column) => column.name === leftKey)?.type ?? "";
  const rightType = rightShape.find((column) => column.name === rightKey)?.type ?? "";
  const typeMismatch =
    leftKey !== "" && rightKey !== "" && leftType !== "" && rightType !== "" && leftType !== rightType;
  const outputCount =
    leftShape.length +
    rightShape.filter((column) => !leftShape.some((left) => left.name === column.name)).length;
  const connected = leftShape.length > 0 && rightShape.length > 0;
  return (
    <div className="join-inline">
      <p className="join-hint">第一路输入为主表，第二路为副表</p>
      <div className="join-mode-grid" role="radiogroup" aria-label="合并方式">
        {JOIN_MODE_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`join-mode-card${mode === option.value ? " active" : ""}`}
            onClick={() => onChange({ ...node.params, mode: option.value })}
          >
            <span className="join-mode-title">{option.title}</span>
            <span className="join-mode-description">{option.description}</span>
          </button>
        ))}
      </div>
      {!connected ? (
        <p className="analysis-editor-empty">连接两路输入后配置匹配键</p>
      ) : (
        <>
          <div className="join-key-row">
            <span className="join-key-label">主表</span>
            <select
              value={leftKey}
              onChange={(event) => onChange({ ...node.params, left_key: event.target.value })}
            >
              <option value="">匹配列…</option>
              {leftShape.map((column) => (
                <option key={column.name} value={column.name}>
                  {column.name}（{column.type}）
                </option>
              ))}
            </select>
            <span className="join-equals">＝</span>
            <span className="join-key-label">副表</span>
            <select
              value={rightKey}
              onChange={(event) => onChange({ ...node.params, right_key: event.target.value })}
            >
              <option value="">匹配列…</option>
              {rightShape.map((column) => (
                <option key={column.name} value={column.name}>
                  {column.name}（{column.type}）
                </option>
              ))}
            </select>
          </div>
          {leftKey === "" && <p className="analysis-row-error">请选择主表匹配列</p>}
          {rightKey === "" && <p className="analysis-row-error">请选择副表匹配列</p>}
          {typeMismatch && (
            <p className="join-warning">
              主表键（{leftType}）与副表键（{rightType}）类型不一致，可能永远匹配不上
            </p>
          )}
          <p className="join-hint">合并后 {outputCount} 列（副表与主表重名的列只输出一份）</p>
        </>
      )}
    </div>
  );
}
