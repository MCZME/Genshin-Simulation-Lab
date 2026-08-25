import { useMemo } from "react";
import { COLORS } from "../../theme/tokens";
import {
  AggregateEditor,
  ComputeEditor,
  DataProviderEditor,
  DisplayConfigEditor,
  FetchEventsEditor,
  FetchRunsEditor,
  FilterEditor,
  JoinEditor,
  LimitEditor,
  ProjectEditor,
  SortEditor,
  setAnalysisEditorEnvironment,
} from "./analysis";
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
import { computeAnalysisShapes } from "../../workflow/templates";
import type { AnalysisSchemaCatalog } from "../../workflow/templates";
import type { WorkflowDefinition } from "../../workflow/types";

export interface NodeEditorHostProps extends Omit<NodeEditorProps, "fieldErrors"> {
  kind: string;
  fieldErrors?: Record<string, string[]>;
  definition: WorkflowDefinition;
  catalog: AnalysisSchemaCatalog | null;
}

export function NodeEditorHost({
  kind,
  node,
  onChange,
  fieldErrors,
  definition,
  catalog,
}: NodeEditorHostProps) {
  const shapes = useMemo(() => computeAnalysisShapes(definition), [definition]);
  setAnalysisEditorEnvironment({ catalog, definition, shapes });
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
      return <SimulationEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "data_provider":
      return <DataProviderEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "fetch_runs":
      return <FetchRunsEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "fetch_events":
      return <FetchEventsEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "filter":
      return <FilterEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "project":
      return <ProjectEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "sort":
      return <SortEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "aggregate":
      return <AggregateEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "limit":
      return <LimitEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "join":
      return <JoinEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "compute":
      return <ComputeEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "table_config":
    case "timeline_config":
    case "pie_config":
    case "bar_config":
      return <DisplayConfigEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
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

/** 分析区域内节点种类（不含画布级 data_provider）。 */
export const ANALYSIS_NODE_KINDS = [
  "fetch_runs",
  "fetch_events",
  "filter",
  "project",
  "sort",
  "aggregate",
  "limit",
  "join",
  "compute",
  "table_config",
  "timeline_config",
  "pie_config",
  "bar_config",
  "member_table",
  "timeline",
  "pie",
  "bar",
] as const;
