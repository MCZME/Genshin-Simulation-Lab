import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

interface TextFieldProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  mono?: boolean;
}

export function TextField({ value, onChange, placeholder, mono = false }: TextFieldProps) {
  const [draft, setDraft] = useState(value);
  const [composing, setComposing] = useState(false);
  function commit() {
    if (draft !== value) {
      onChange(draft);
    }
  }
  return (
    <input
      key={value}
      className={`field nowheel ${mono ? "field-mono" : ""}`}
      type="text"
      value={draft}
      placeholder={placeholder}
      onChange={(event) => setDraft(event.target.value)}
      onCompositionStart={() => setComposing(true)}
      onCompositionEnd={() => setComposing(false)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (composing || event.nativeEvent.isComposing) {
          return;
        }
        if (event.key === "Enter") {
          commit();
          event.currentTarget.blur();
        } else if (event.key === "Escape") {
          setDraft(value);
          event.currentTarget.blur();
        }
      }}
    />
  );
}

interface NumberFieldProps {
  value: number | null;
  onChange: (value: number | null) => void;
  min?: number;
  max?: number;
  /** 离散可选值；提供时滑块按选项索引映射（如角色等级 1-90、95、100）。 */
  options?: number[];
  /** 空值显示文案；缺省「未设置」。 */
  emptyLabel?: string;
}

export function NumberField({
  value,
  onChange,
  min,
  max,
  options = [],
  emptyLabel = "未设置",
}: NumberFieldProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<number | null>(value);
  const editingRef = useRef(false);
  const controlRef = useRef<HTMLInputElement>(null);

  const sliderValues =
    options.length > 0
      ? options
      : min !== undefined && max !== undefined && Number.isInteger(min) && Number.isInteger(max)
        ? integerRange(min, max)
        : null;

  useEffect(() => {
    if (editing) {
      controlRef.current?.focus();
      controlRef.current?.select();
    }
  }, [editing]);

  function startEdit() {
    editingRef.current = true;
    setDraft(value);
    setEditing(true);
  }

  function commit() {
    if (!editingRef.current) {
      return;
    }
    editingRef.current = false;
    setEditing(false);
    if (draft !== value) {
      onChange(draft);
    }
  }

  function cancel() {
    if (!editingRef.current) {
      return;
    }
    editingRef.current = false;
    setEditing(false);
    setDraft(value);
  }

  if (!editing) {
    return (
      <button
        type="button"
        className="number-display nowheel nodrag"
        onClick={startEdit}
      >
        {value === null ? emptyLabel : String(value)}
      </button>
    );
  }

  if (sliderValues !== null) {
    const index = clampIndex(sliderValues, draft);
    return (
      <div className="number-field-edit nowheel nodrag">
        <span className="number-slider-value">
          {sliderValues[index] === undefined ? emptyLabel : String(sliderValues[index])}
        </span>
        <input
          ref={controlRef}
          className="number-slider nodrag"
          type="range"
          min={0}
          max={sliderValues.length - 1}
          step={1}
          value={index}
          onChange={(event) => setDraft(sliderValues[Number(event.target.value)] ?? null)}
          onPointerUp={commit}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commit();
            } else if (event.key === "Escape") {
              event.preventDefault();
              cancel();
            }
          }}
        />
      </div>
    );
  }

  return (
    <div className="number-field-edit nowheel nodrag">
      <input
        ref={controlRef}
        className="field field-mono nowheel nodrag"
        type="number"
        value={draft === null ? "" : String(draft)}
        min={min}
        max={max}
        onChange={(event) => {
          const text = event.target.value;
          if (text === "") {
            setDraft(null);
            return;
          }
          const parsed = Number(text);
          setDraft(Number.isFinite(parsed) ? parsed : draft);
        }}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit();
            event.currentTarget.blur();
          } else if (event.key === "Escape") {
            event.preventDefault();
            cancel();
            event.currentTarget.blur();
          }
        }}
      />
    </div>
  );
}

function integerRange(min: number, max: number): number[] {
  const result: number[] = [];
  for (let value = min; value <= max; value += 1) {
    result.push(value);
  }
  return result;
}

function clampIndex(values: number[], draft: number | null): number {
  if (draft === null) {
    return 0;
  }
  const exact = values.indexOf(draft);
  if (exact >= 0) {
    return exact;
  }
  let best = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  values.forEach((value, index) => {
    const distance = Math.abs(value - draft);
    if (distance < bestDistance) {
      best = index;
      bestDistance = distance;
    }
  });
  return best;
}

interface SelectFieldProps {
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}

export function SelectField({ value, options, onChange }: SelectFieldProps) {
  return (
    <select className="field nowheel" value={value} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

interface TextAreaFieldProps {
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  invalid?: boolean;
}

export function TextAreaField({ value, onChange, rows = 6, invalid = false }: TextAreaFieldProps) {
  const [draft, setDraft] = useState(value);
  function commit() {
    if (draft !== value) {
      onChange(draft);
    }
  }
  return (
    <textarea
      key={value}
      className={`field field-mono nowheel ${invalid ? "field-invalid" : ""}`}
      rows={rows}
      value={draft}
      spellCheck={false}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
    />
  );
}

export function FieldRow({
  label,
  children,
  error,
}: {
  label: string;
  children: ReactNode;
  error?: string;
}) {
  return (
    <div className="field-row-wrap">
      <label className="field-row">
        <span className="field-label">{label}</span>
        {children}
      </label>
      {error !== undefined && <InlineError message={error} />}
    </div>
  );
}

export function InlineError({ message }: { message: string }) {
  return <span className="inline-error">{message}</span>;
}

export function CollapsibleGroup({
  title,
  summary,
  defaultOpen = true,
  children,
}: {
  title: string;
  summary?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="collapsible-group">
      <button
        type="button"
        className="collapsible-header"
        onClick={() => setOpen((current) => !current)}
      >
        <span className="collapsible-caret">{open ? "▾" : "▸"}</span>
        <span className="collapsible-title">{title}</span>
        {!open && summary !== undefined && (
          <span className="collapsible-summary">{summary}</span>
        )}
      </button>
      {open && <div className="collapsible-body">{children}</div>}
    </div>
  );
}
