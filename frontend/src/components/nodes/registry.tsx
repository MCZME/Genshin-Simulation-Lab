import { COLORS } from "../../theme/tokens";
import {
  ArtifactEditor,
  CharacterEditor,
  EnumEditor,
  InputTraceEditor,
  MetaEditor,
  RangeEditor,
  RootEditor,
  RunOptionsEditor,
  SimulationEditor,
  TargetEditor,
  UnknownEditor,
  WeaponEditor,
} from "./editors";
import type { NodeEditorProps } from "./editors";

export interface NodeEditorHostProps extends Omit<NodeEditorProps, "fieldErrors"> {
  kind: string;
  fieldErrors?: Record<string, string[]>;
}

export function NodeEditorHost({
  kind,
  node,
  onChange,
  fieldErrors,
}: NodeEditorHostProps) {
  switch (kind) {
    case "root":
      return <RootEditor fieldErrors={fieldErrors} />;
    case "meta":
      return <MetaEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "character":
      return <CharacterEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "weapon":
      return <WeaponEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "artifact":
      return <ArtifactEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "target":
      return <TargetEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "input_trace":
      return <InputTraceEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "run_options":
      return <RunOptionsEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "enum":
      return <EnumEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "range":
      return <RangeEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "simulation":
      return <SimulationEditor />;
    default:
      return <UnknownEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
  }
}

export function nodeKindColor(kind: string): string {
  const colors = COLORS.node as Record<string, string>;
  return colors[kind] ?? "#64748b";
}

export const CONFIG_NODE_KINDS = [
  "root",
  "meta",
  "character",
  "weapon",
  "artifact",
  "target",
  "input_trace",
  "run_options",
  "enum",
  "range",
] as const;
