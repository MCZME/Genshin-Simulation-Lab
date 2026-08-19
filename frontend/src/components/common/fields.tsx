import type { ReactNode } from "react";

interface TextFieldProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  mono?: boolean;
}

export function TextField({ value, onChange, placeholder, mono = false }: TextFieldProps) {
  return (
    <input
      className={`field ${mono ? "field-mono" : ""}`}
      type="text"
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
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
  return (
    <input
      className="field field-mono"
      type="number"
      value={value ?? ""}
      min={min}
      max={max}
      onChange={(event) => {
        const text = event.target.value;
        if (text === "") {
          onChange(null);
          return;
        }
        const number = Number(text);
        onChange(Number.isFinite(number) ? number : null);
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
  return (
    <textarea
      className={`field field-mono ${invalid ? "field-invalid" : ""}`}
      rows={rows}
      value={value}
      spellCheck={false}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

export function FieldRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field-row">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

export function InlineError({ message }: { message: string }) {
  return <span className="inline-error">{message}</span>;
}
