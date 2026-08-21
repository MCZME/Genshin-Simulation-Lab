import type { WorkflowNode } from "../../workflow/types";

export interface NodeEditorProps {
  node: WorkflowNode;
  onChange: (params: Record<string, unknown>) => void;
  fieldErrors?: Record<string, string[]>;
}

export type ErrorOnlyProps = Pick<NodeEditorProps, "fieldErrors">;

export function firstError(errors: Record<string, string[]>, path: string): string | undefined {
  return errors[path]?.[0];
}

export function firstErrorPrefix(
  errors: Record<string, string[]>,
  prefix: string,
): string | undefined {
  const key = Object.keys(errors).find(
    (path) => path === prefix || path.startsWith(`${prefix}[`),
  );
  return key === undefined ? undefined : errors[key]?.[0];
}

export function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

export function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
