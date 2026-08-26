/** 计算列节点：公式文本直编。 */

import { useEffect, useRef, useState } from "react";
import type { TableShape } from "../../../workflow/templates";
import {
  exprToFormula,
  parseFormula,
  type ComputeExpr,
} from "../../../workflow/formula";
import {
  COLUMN_NAME_PATTERN,
  upstreamShape,
  type EditorProps,
  type EditorRow,
} from "./context";

export function ComputeEditor({ node, onChange }: EditorProps) {
  const shape = upstreamShape(node.id);
  const types = new Map(shape.map((column) => [column.name, column.type]));
  const numericColumns = shape.filter(
    (column) => column.type === "int" || column.type === "float",
  );
  const rows = Array.isArray(node.params.columns)
    ? (node.params.columns as EditorRow[])
    : [];
  const takenFor = (index: number): Set<string> => {
    const taken = new Set(shape.map((column) => column.name));
    rows.forEach((row, i) => {
      if (i === index) {
        return;
      }
      const name = typeof row.name === "string" ? row.name.trim() : "";
      if (name !== "") {
        taken.add(name);
      }
    });
    return taken;
  };
  const updateRow = (index: number, patch: Partial<EditorRow>) => {
    onChange({
      ...node.params,
      columns: rows.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    });
  };
  return (
    <div className="compute-inline">
      {rows.length === 0 && <p className="analysis-editor-empty">至少添加一个计算列</p>}
      {rows.map((row, index) => (
        <ComputeRow
          key={index}
          row={row}
          types={types}
          numericColumns={numericColumns}
          taken={takenFor(index)}
          onChange={(patch) => updateRow(index, patch)}
          onRemove={() =>
            onChange({
              ...node.params,
              columns: rows.filter((_, i) => i !== index),
            })
          }
        />
      ))}
      <button
        type="button"
        className="filter-add-button"
        onClick={() => onChange({ ...node.params, columns: [...rows, {}] })}
      >
        ＋ 添加计算列
      </button>
    </div>
  );
}

function ComputeRow({
  row,
  types,
  numericColumns,
  taken,
  onChange,
  onRemove,
}: {
  row: EditorRow;
  types: Map<string, string>;
  numericColumns: TableShape[];
  taken: Set<string>;
  onChange: (patch: Partial<EditorRow>) => void;
  onRemove: () => void;
}) {
  const name = typeof row.name === "string" ? row.name : "";
  const [draft, setDraft] = useState<string>(() =>
    exprToFormula(row.expr as ComputeExpr | null | undefined),
  );
  const inputRef = useRef<HTMLInputElement | null>(null);
  const lastExprKey = useRef<string>(JSON.stringify(row.expr ?? null));
  useEffect(() => {
    const key = JSON.stringify(row.expr ?? null);
    if (key !== lastExprKey.current) {
      lastExprKey.current = key;
      setDraft(exprToFormula(row.expr as ComputeExpr | null | undefined));
    }
  }, [row.expr]);
  const commitFormula = (next: string) => {
    setDraft(next);
    const parsed = parseFormula(next, types);
    if (parsed.error === null && parsed.ast !== null) {
      lastExprKey.current = JSON.stringify(parsed.ast);
      onChange({ expr: parsed.ast });
    }
  };
  const insertColumn = (column: string) => {
    const position = inputRef.current?.selectionStart ?? draft.length;
    const next = draft.slice(0, position) + column + draft.slice(position);
    commitFormula(next);
    requestAnimationFrame(() => {
      const element = inputRef.current;
      if (element !== null) {
        element.focus();
        const caret = position + column.length;
        element.setSelectionRange(caret, caret);
      }
    });
  };
  const errors: string[] = [];
  const trimmedName = name.trim();
  if (trimmedName === "") {
    errors.push("请填写结果列名");
  } else if (!COLUMN_NAME_PATTERN.test(trimmedName)) {
    errors.push("结果列名不合法（字母/数字/下划线，≤64 位）");
  } else if (taken.has(trimmedName)) {
    errors.push(`结果列名重复：${trimmedName}`);
  }
  const parsed = parseFormula(draft, types);
  if (parsed.error !== null) {
    errors.push(parsed.error);
  }
  return (
    <div className="compute-row">
      <div className="compute-head">
        <input
          className="compute-name-input"
          placeholder="结果列名"
          value={name}
          onChange={(event) => onChange({ name: event.target.value.trim() })}
        />
        <select
          className="compute-insert-select"
          value=""
          onChange={(event) => {
            if (event.target.value !== "") {
              insertColumn(event.target.value);
            }
          }}
        >
          <option value="">插入列…</option>
          {numericColumns.map((column) => (
            <option key={column.name} value={column.name}>
              {column.name}
            </option>
          ))}
        </select>
        <button type="button" className="filter-row-remove" title="移除计算列" onClick={onRemove}>
          ×
        </button>
      </div>
      <input
        ref={inputRef}
        className="compute-formula-input"
        placeholder="公式，如 total_damage / (frames_run / 60)"
        value={draft}
        onChange={(event) => commitFormula(event.target.value)}
      />
      {errors.map((message) => (
        <p key={message} className="filter-row-error">
          {message}
        </p>
      ))}
    </div>
  );
}
