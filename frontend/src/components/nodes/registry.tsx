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

export function NodeEditorHost({
  kind,
  node,
  onChange,
}: NodeEditorProps & { kind: string }) {
  switch (kind) {
    case "root":
      return <RootEditor />;
    case "meta":
      return <MetaEditor />;
    case "character":
      return <CharacterEditor node={node} onChange={onChange} />;
    case "weapon":
      return <WeaponEditor node={node} onChange={onChange} />;
    case "artifact":
      return <ArtifactEditor node={node} onChange={onChange} />;
    case "target":
      return <TargetEditor node={node} onChange={onChange} />;
    case "input_trace":
      return <InputTraceEditor node={node} onChange={onChange} />;
    case "run_options":
      return <RunOptionsEditor node={node} onChange={onChange} />;
    case "enum":
      return <EnumEditor node={node} onChange={onChange} />;
    case "range":
      return <RangeEditor node={node} onChange={onChange} />;
    case "simulation":
      return <SimulationEditor />;
    default:
      return <UnknownEditor node={node} onChange={onChange} />;
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
