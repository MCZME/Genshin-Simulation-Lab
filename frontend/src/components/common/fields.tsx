import { useState } from "react";
import type { ReactNode } from "react";

interface TextFieldProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  mono?: boolean;
}

export function TextField({ value, onChange, placeholder, mono = false }: TextFieldProps) {
  const [draft, setDraft] = useState(value);
  function commit() {
    if (draft !== value) {
      onChange(draft);
    }
  }
  return (
    <input
      key={value}
      className={`field ${mono ? "field-mono" : ""}`}
      type="text"
      value={draft}
      placeholder={placeholder}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
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
}

export function NumberField({ value, onChange, min, max }: NumberFieldProps) {
  const [draft, setDraft] = useState(value === null ? "" : String(value));
  function commit() {
    const text = draft.trim();
    if (text === "") {
      onChange(null);
      return;
    }
    const number = Number(text);
    onChange(Number.isFinite(number) ? number : null);
  }
  return (
    <input
      key={value}
      className="field field-mono"
      type="number"
      value={draft}
      min={min}
      max={max}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          commit();
          event.currentTarget.blur();
        } else if (event.key === "Escape") {
          setDraft(value === null ? "" : String(value));
          event.currentTarget.blur();
        }
      }}
    />
  );
}

interface SelectFieldProps {
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}

export function SelectField({ value, options, onChange }: SelectFieldProps) {
  return (
    <select className="field" value={value} onChange={(event) => onChange(event.target.value)}>
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
      className={`field field-mono ${invalid ? "field-invalid" : ""}`}
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
