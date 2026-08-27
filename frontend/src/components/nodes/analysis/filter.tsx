/** 过滤节点：卡片直编。 */

import { useState } from "react";
import { CONDITION_OPERATORS } from "../../../workflow/templates";
import type { FilterCondition, TableShape } from "../../../workflow/templates";
import { upstreamShape, type EditorProps } from "./context";

const FILTER_OPERATOR_LABELS: Record<string, string> = {
  eq: "等于",
  ne: "不等于",
  gt: "大于",
  gte: "大于等于",
  lt: "小于",
  lte: "小于等于",
  in: "属于",
  not_in: "不属于",
  is_null: "为空",
  is_not_null: "不为空",
};

const OPERATORS_BY_TYPE: Record<string, string[]> = {
  string: ["eq", "ne", "in", "not_in", "is_null", "is_not_null"],
  bool: ["eq", "ne", "is_null", "is_not_null"],
  int: ["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "is_null", "is_not_null"],
  float: ["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "is_null", "is_not_null"],
};

const FILTER_NUMERIC_TYPES = new Set(["int", "float"]);

function operatorsForType(type: string, currentOp: string): string[] {
  const base = OPERATORS_BY_TYPE[type] ?? [...CONDITION_OPERATORS];
  return base.includes(currentOp) ? base : [...base, currentOp];
}

function filterValueMatchesType(type: string, value: unknown): boolean {
  if (type === "string") {
    return typeof value === "string";
  }
  if (type === "bool") {
    return typeof value === "boolean";
  }
  if (type === "int") {
    return typeof value === "number" && Number.isInteger(value);
  }
  if (type === "float") {
    return typeof value === "number" && Number.isFinite(value);
  }
  return true;
}

function formatFilterValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(formatFilterValue).join("、");
  }
  if (value === true) {
    return "真";
  }
  if (value === false) {
    return "假";
  }
  if (typeof value === "number") {
    return String(value);
  }
  return value === null || value === undefined ? "" : String(value);
}

function filterConditionError(
  condition: FilterCondition,
  index: number,
  shape: TableShape[],
): string | null {
  const prefix = `第 ${index + 1} 个条件：`;
  if (typeof condition.column !== "string" || condition.column === "") {
    return `${prefix}请选择列`;
  }
  const type = shape.find((column) => column.name === condition.column)?.type ?? "";
  if (type === "") {
    return `${prefix}列不存在`;
  }
  if (typeof condition.op !== "string" || !CONDITION_OPERATORS.includes(condition.op as never)) {
    return `${prefix}请选择操作符`;
  }
  const op = condition.op;
  if (op === "gt" || op === "gte" || op === "lt" || op === "lte") {
    if (!FILTER_NUMERIC_TYPES.has(type)) {
      return `${prefix}该操作符不适用于${type === "string" ? "文本" : type}列`;
    }
  }
  if (op === "is_null" || op === "is_not_null") {
    return null;
  }
  if (op === "in" || op === "not_in") {
    if (!Array.isArray(condition.value) || condition.value.length === 0) {
      return `${prefix}请至少添加一个值`;
    }
    if (condition.value.some((item) => !filterValueMatchesType(type, item))) {
      return `${prefix}值的类型与列类型不一致`;
    }
    return null;
  }
  if (!filterValueMatchesType(type, condition.value)) {
    return type === "bool" ? `${prefix}请选择真或假` : `${prefix}请填写与列类型匹配的值`;
  }
  return null;
}

function toArrayValue(value: unknown, type: string): unknown[] {
  if (Array.isArray(value)) {
    return value.filter((item) => filterValueMatchesType(type, item));
  }
  return filterValueMatchesType(type, value) &&
    value !== undefined &&
    value !== null &&
    value !== ""
    ? [value]
    : [];
}

function toScalarValue(value: unknown, type: string): unknown {
  if (Array.isArray(value) && value.length === 1 && filterValueMatchesType(type, value[0])) {
    return value[0];
  }
  return filterValueMatchesType(type, value) ? value : undefined;
}

export function FilterEditor({ node, onChange }: EditorProps) {
  const shape = upstreamShape(node.id);
  const mode = node.params.mode === "any" ? "any" : "all";
  const conditions = Array.isArray(node.params.conditions)
    ? (node.params.conditions as FilterCondition[])
    : [];
  const updateCondition = (index: number, patch: Partial<FilterCondition>) => {
    onChange({
      ...node.params,
      conditions: conditions.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    });
  };
  const replaceCondition = (index: number, next: FilterCondition) => {
    onChange({
      ...node.params,
      conditions: conditions.map((item, i) => (i === index ? next : item)),
    });
  };
  const removeCondition = (index: number) => {
    onChange({ ...node.params, conditions: conditions.filter((_, i) => i !== index) });
  };
  const changeColumn = (index: number, column: string) => {
    const type = shape.find((item) => item.name === column)?.type ?? "";
    const target = conditions[index];
    const op = operatorsForType(type, "").includes(target.op) ? target.op : "eq";
    const value = op === target.op ? target.value : toScalarValue(target.value, type);
    replaceCondition(index, { column, op, value });
  };
  const changeOp = (index: number, op: string) => {
    const target = conditions[index];
    const type = shape.find((item) => item.name === target.column)?.type ?? "";
    const next: FilterCondition = { column: target.column, op };
    if (op !== "is_null" && op !== "is_not_null") {
      next.value =
        op === "in" || op === "not_in"
          ? toArrayValue(target.value, type)
          : toScalarValue(target.value, type);
    }
    replaceCondition(index, next);
  };
  const errors = conditions.map((condition, index) =>
    filterConditionError(condition, index, shape),
  );
  return (
    <div className="filter-inline">
      <div className="fetch-source-switch">
        <button
          type="button"
          className={mode === "all" ? "active" : ""}
          onClick={() => onChange({ ...node.params, mode: "all", conditions })}
        >
          满足全部
        </button>
        <button
          type="button"
          className={mode === "any" ? "active" : ""}
          onClick={() => onChange({ ...node.params, mode: "any", conditions })}
        >
          满足任一
        </button>
      </div>
      {conditions.map((condition, index) => (
        <FilterConditionRow
          key={index}
          condition={condition}
          shape={shape}
          error={errors[index]}
          onChangeColumn={(column) => changeColumn(index, column)}
          onChangeOp={(op) => changeOp(index, op)}
          onChangeValue={(value) => updateCondition(index, { value })}
          onRemove={() => removeCondition(index)}
        />
      ))}
      <button
        type="button"
        className="filter-add-button"
        onClick={() =>
          onChange({
            ...node.params,
            conditions: [...conditions, { column: "", op: "eq", value: "" }],
          })
        }
      >
        ＋ 添加条件
      </button>
    </div>
  );
}

function FilterConditionRow({
  condition,
  shape,
  error,
  onChangeColumn,
  onChangeOp,
  onChangeValue,
  onRemove,
}: {
  condition: FilterCondition;
  shape: TableShape[];
  error: string | null;
  onChangeColumn: (column: string) => void;
  onChangeOp: (op: string) => void;
  onChangeValue: (value: unknown) => void;
  onRemove: () => void;
}) {
  const type = shape.find((column) => column.name === condition.column)?.type ?? "";
  const ops = operatorsForType(type, condition.op);
  return (
    <div className="filter-condition-row">
      <div className="filter-condition-line">
        <select
          value={condition.column}
          onChange={(event) => onChangeColumn(event.target.value)}
        >
          <option value="">选择列…</option>
          {shape.map((column) => (
            <option key={column.name} value={column.name}>
              {column.name}（{column.type}）
            </option>
          ))}
        </select>
        <select value={condition.op} onChange={(event) => onChangeOp(event.target.value)}>
          {ops.map((op) => (
            <option key={op} value={op}>
              {FILTER_OPERATOR_LABELS[op] ?? op}
            </option>
          ))}
        </select>
        <FilterValueControl condition={condition} type={type} onChange={onChangeValue} />
        <button
          type="button"
          className="filter-row-remove"
          title="移除条件"
          onClick={onRemove}
        >
          ×
        </button>
      </div>
      {error !== null && <p className="filter-row-error">{error}</p>}
    </div>
  );
}

function FilterValueControl({
  condition,
  type,
  onChange,
}: {
  condition: FilterCondition;
  type: string;
  onChange: (value: unknown) => void;
}) {
  const op = condition.op;
  if (op === "is_null" || op === "is_not_null") {
    return null;
  }
  if (op === "in" || op === "not_in") {
    return (
      <FilterMultiValue
        values={Array.isArray(condition.value) ? condition.value : []}
        type={type === "int" ? "int" : type === "float" ? "float" : "string"}
        placeholder={type === "string" ? "输入值后回车" : "输入数字后回车"}
        onChange={onChange}
      />
    );
  }
  if (type === "bool") {
    return (
      <select
        value={condition.value === true ? "true" : condition.value === false ? "false" : ""}
        onChange={(event) => onChange(event.target.value === "true")}
      >
        <option value="">真/假…</option>
        <option value="true">真</option>
        <option value="false">假</option>
      </select>
    );
  }
  if (type === "int" || type === "float") {
    return (
      <input
        type="number"
        step={type === "int" ? 1 : "any"}
        placeholder={type === "int" ? "整数" : "数值"}
        value={
          typeof condition.value === "number" && Number.isFinite(condition.value)
            ? String(condition.value)
            : ""
        }
        onChange={(event) =>
          onChange(event.target.value === "" ? undefined : Number(event.target.value))
        }
      />
    );
  }
  return (
    <input
      placeholder="输入值"
      value={typeof condition.value === "string" ? condition.value : ""}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

/** 多值 chips：回车或逗号添加，退格删除最后一个，chip 内可移除。 */
function FilterMultiValue({
  values,
  type,
  placeholder,
  onChange,
}: {
  values: unknown[];
  type: "string" | "int" | "float";
  placeholder: string;
  onChange: (value: unknown) => void;
}) {
  const [text, setText] = useState("");
  const [composing, setComposing] = useState(false);
  const commitText = (raw: string) => {
    const parts = raw
      .split(/[,，]/)
      .map((part) => part.trim())
      .filter((part) => part !== "");
    if (parts.length === 0) {
      setText("");
      return;
    }
    const next = [...values];
    for (const part of parts) {
      if (type === "string") {
        next.push(part);
        continue;
      }
      const number = Number(part);
      if (Number.isFinite(number) && (type === "float" || Number.isInteger(number))) {
        next.push(number);
      }
    }
    onChange(next);
    setText("");
  };
  return (
    <div className="filter-chips">
      {values.map((value, index) => (
        <span key={`${String(value)}-${index}`} className="filter-chip">
          {formatFilterValue(value)}
          <button
            type="button"
            title="移除"
            onClick={() => onChange(values.filter((_, i) => i !== index))}
          >
            ×
          </button>
        </span>
      ))}
      <input
        className="filter-chip-input"
        value={text}
        placeholder={placeholder}
        onChange={(event) => setText(event.target.value)}
        onCompositionStart={() => setComposing(true)}
        onCompositionEnd={() => setComposing(false)}
        onKeyDown={(event) => {
          if (composing || event.nativeEvent.isComposing) {
            return;
          }
          if (event.key === "Enter" || event.key === "," || event.key === "，") {
            event.preventDefault();
            commitText(text);
          } else if (event.key === "Backspace" && text === "" && values.length > 0) {
            onChange(values.slice(0, -1));
          }
        }}
        onBlur={() => {
          if (text.trim() !== "") {
            commitText(text);
          }
        }}
      />
    </div>
  );
}
