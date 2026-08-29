import { useMemo } from "react";
import { COLORS, type NodeCategory } from "../../theme/tokens";
import {
  AggregateEditor,
  ComputeEditor,
  DisplayConfigEditor,
  FetchEditor,
  FilterEditor,
  JoinEditor,
  LimitEditor,
  ProjectEditor,
  SortEditor,
  TableConfigEditor,
  setAnalysisEditorEnvironment,
} from "./analysis";
import { DataProviderEditor } from "./dataProvider";
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
  const shapes = useMemo(
    () => computeAnalysisShapes(definition, catalog),
    [definition, catalog],
  );
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
    case "fetch":
      return <FetchEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
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
    case "pie_config":
    case "bar_config":
      return <DisplayConfigEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "table_config":
      return <TableConfigEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
    case "single":
    case "frame_state":
    case "damage_detail":
    case "state_detail":
    case "attribute_detail":
      // 取单项与单项详情节点没有参数编辑区，数据在节点卡内容区呈现。
      return null;
    default:
      return <UnknownEditor node={node} onChange={onChange} fieldErrors={fieldErrors} />;
  }
}

/** 节点 -> 类别映射：颜色按类别共享，不按具体节点类型（决策 2.34）。 */
const NODE_CATEGORY_OF: Record<string, NodeCategory> = {
  root: "runSettings",
  meta: "runSettings",
  run_options: "runSettings",
  character: "teamConfig",
  weapon: "teamConfig",
  artifact: "teamConfig",
  target: "targetConfig",
  input_trace: "inputSequence",
  enum: "variantScan",
  range: "variantScan",
  simulation: "simulation",
  data_provider: "dataSource",
  fetch: "dataSource",
  filter: "dataProcessing",
  project: "dataProcessing",
  sort: "dataProcessing",
  aggregate: "dataProcessing",
  limit: "dataProcessing",
  join: "dataProcessing",
  compute: "dataProcessing",
  table_config: "displayConfig",
  pie_config: "displayConfig",
  bar_config: "displayConfig",
  member_table: "displayView",
  pie: "displayView",
  bar: "displayView",
  single: "dataProcessing",
  frame_state: "displayView",
  damage_detail: "displayView",
  state_detail: "displayView",
  attribute_detail: "displayView",
};

export function nodeCategoryOf(kind: string): NodeCategory | null {
  return NODE_CATEGORY_OF[kind] ?? null;
}

export function nodeKindColor(kind: string): string {
  if (kind === "region") {
    return COLORS.region.configuration;
  }
  if (kind === "analysis_region") {
    return COLORS.region.analysis;
  }
  const category = nodeCategoryOf(kind);
  return category === null ? "#64748b" : COLORS.nodeCategory[category];
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
  "fetch",
  "filter",
  "project",
  "sort",
  "aggregate",
  "limit",
  "join",
  "compute",
  "single",
  "table_config",
  "member_table",
  "pie_config",
  "pie",
  "bar_config",
  "bar",
  "frame_state",
  "damage_detail",
  "state_detail",
  "attribute_detail",
] as const;
