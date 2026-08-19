import type {
  DataLanguage,
  Diagnostic,
  EnumValue,
  EnumValueType,
  NodeKind,
  PortCardinality,
  RegionKind,
  WorkflowDefinition,
  WorkflowNode,
} from "./types";
import { rangeEntries } from "./decimal";
import { parsePath } from "./path";

export type ParamFieldType =
  | "string"
  | "integer"
  | "number"
  | "boolean"
  | "text"
  | "asset_ref"
  | "list"
  | "range"
  | "object"
  | "json_fragment";

export interface ParamFieldSpec {
  type: ParamFieldType;
  required?: boolean;
  assetType?: "characters" | "weapons" | "artifact-sets";
  default?: unknown;
}

export interface PortSpec {
  id: string;
  cardinality: PortCardinality;
  dataLanguage: DataLanguage;
  connectionLimit: number;
}

export interface NodeKindSpec {
  kind: NodeKind;
  displayName: string;
  region: RegionKind | "bridge";
  ports: {
    inputs: PortSpec[];
    outputs: PortSpec[];
  };
  paramFields: Record<string, ParamFieldSpec>;
}

export interface FragmentSource {
  item_id: string;
  path: string;
  value: unknown;
}

function fragmentPort(id: string, cardinality: PortCardinality): PortSpec {
  return { id, cardinality, dataLanguage: "fragment", connectionLimit: 1 };
}

export const REGISTRY: Record<NodeKind, NodeKindSpec> = {
  root: {
    kind: "root",
    displayName: "根节点",
    region: "configuration",
    ports: { inputs: [], outputs: [fragmentPort("out", "single")] },
    paramFields: { file_path: { type: "string" } },
  },
  meta: {
    kind: "meta",
    displayName: "元信息",
    region: "configuration",
    ports: { inputs: [], outputs: [fragmentPort("out", "single")] },
    paramFields: {},
  },
  character: {
    kind: "character",
    displayName: "角色",
    region: "configuration",
    ports: { inputs: [], outputs: [fragmentPort("out", "single")] },
    paramFields: {
      slot: { type: "integer", required: true },
      asset: { type: "asset_ref", required: true, assetType: "characters" },
      level: { type: "integer", default: 90 },
      constellation: { type: "integer", default: 0 },
      talents: { type: "object", default: { normal_attack: 1, elemental_skill: 1, elemental_burst: 1 } },
    },
  },
  weapon: {
    kind: "weapon",
    displayName: "武器",
    region: "configuration",
    ports: { inputs: [], outputs: [fragmentPort("out", "single")] },
    paramFields: {
      slot: { type: "integer", required: true },
      asset: { type: "asset_ref", required: true, assetType: "weapons" },
      level: { type: "integer", default: 90 },
      refinement: { type: "integer", default: 1 },
    },
  },
  artifact: {
    kind: "artifact",
    displayName: "圣遗物",
    region: "configuration",
    ports: { inputs: [], outputs: [fragmentPort("out", "single")] },
    paramFields: {
      slot: { type: "integer", required: true },
      asset: { type: "asset_ref", required: true, assetType: "artifact-sets" },
      pieces: { type: "integer", default: 4 },
    },
  },
  target: {
    kind: "target",
    displayName: "目标",
    region: "configuration",
    ports: { inputs: [], outputs: [fragmentPort("out", "single")] },
    paramFields: {
      index: { type: "integer", required: true },
      id: { type: "string" },
      level: { type: "integer", default: 90 },
    },
  },
  input_trace: {
    kind: "input_trace",
    displayName: "按键轨迹",
    region: "configuration",
    ports: { inputs: [], outputs: [fragmentPort("out", "single")] },
    paramFields: { items: { type: "list", required: true } },
  },
  run_options: {
    kind: "run_options",
    displayName: "运行选项",
    region: "configuration",
    ports: { inputs: [], outputs: [fragmentPort("out", "single")] },
    paramFields: { max_frames: { type: "integer", default: 18000 } },
  },
  enum: {
    kind: "enum",
    displayName: "枚举",
    region: "configuration",
    ports: { inputs: [], outputs: [fragmentPort("out", "group")] },
    paramFields: {
      path: { type: "string", required: true },
      value_type: { type: "string", required: true },
      values: { type: "list", required: true },
    },
  },
  range: {
    kind: "range",
    displayName: "区间",
    region: "configuration",
    ports: { inputs: [], outputs: [fragmentPort("out", "group")] },
    paramFields: {
      path: { type: "string", required: true },
      start: { type: "number", required: true },
      end: { type: "number", required: true },
      step: { type: "number", required: true },
      label: { type: "string" },
    },
  },
  simulation: {
    kind: "simulation",
    displayName: "模拟桥",
    region: "bridge",
    ports: {
      inputs: [
        {
          id: "in",
          cardinality: "single",
          dataLanguage: "input_document",
          connectionLimit: 1,
        },
      ],
      outputs: [
        { id: "out", cardinality: "group", dataLanguage: "session", connectionLimit: 1 },
      ],
    },
    paramFields: {},
  },
};

export function getNodeKindSpec(kind: string): NodeKindSpec | null {
  return (REGISTRY as Record<string, NodeKindSpec>)[kind] ?? null;
}

/** 单值节点产出一个片段；根节点与模拟桥不产出来源。 */
export function singleFragment(
  node: WorkflowNode,
  definition: WorkflowDefinition,
): FragmentSource | null {
  const params = node.params;
  switch (node.kind) {
    case "root":
      return null;
    case "meta":
      return {
        item_id: `node:${node.id}`,
        path: "meta",
        value: { name: definition.meta.name, description: "" },
      };
    case "character": {
      const slot = asInteger(params.slot) ?? 1;
      const asset = asString(params.asset);
      if (asset === null) {
        return null;
      }
      return {
        item_id: `node:${node.id}`,
        path: `team[${slot - 1}].${node.kind}`,
        value: {
          asset_key: asset,
          level: asInteger(params.level) ?? 90,
          constellation: asInteger(params.constellation) ?? 0,
          talents: isPlainObject(params.talents)
            ? params.talents
            : { normal_attack: 1, elemental_skill: 1, elemental_burst: 1 },
        },
      };
    }
    case "weapon": {
      const slot = asInteger(params.slot) ?? 1;
      const asset = asString(params.asset);
      if (asset === null) {
        return null;
      }
      return {
        item_id: `node:${node.id}`,
        path: `team[${slot - 1}].weapon`,
        value: {
          asset_key: asset,
          level: asInteger(params.level) ?? 90,
          refinement: asInteger(params.refinement) ?? 1,
        },
      };
    }
    case "artifact": {
      const slot = asInteger(params.slot) ?? 1;
      const asset = asString(params.asset);
      if (asset === null) {
        return null;
      }
      return {
        item_id: `node:${node.id}`,
        path: `team[${slot - 1}].artifacts`,
        value: {
          sets: [{ asset_key: asset, pieces: asInteger(params.pieces) ?? 4 }],
          stats: {},
        },
      };
    }
    case "target": {
      const index = asInteger(params.index) ?? 0;
      return {
        item_id: `node:${node.id}`,
        path: `scene.targets[${index}]`,
        value: {
          id: asString(params.id) ?? `target_${index}`,
          level: asInteger(params.level) ?? 90,
          position: { x: 0, y: 0, z: 5 },
          resistance: {},
        },
      };
    }
    case "input_trace":
      return {
        item_id: `node:${node.id}`,
        path: "input_trace",
        value: Array.isArray(params.items) ? params.items : [],
      };
    case "run_options":
      return {
        item_id: `node:${node.id}`,
        path: "run_options",
        value: { max_frames: asInteger(params.max_frames) ?? 18000 },
      };
    case "enum":
    case "range":
    case "simulation":
      return null;
    default:
      return null;
  }
}

/** 枚举/区间节点产出按取值展开的多个片段来源。 */
export function groupFragments(node: WorkflowNode): FragmentSource[] {
  if (node.kind === "enum") {
    return enumFragments(node);
  }
  if (node.kind === "range") {
    return rangeFragments(node);
  }
  return [];
}

function enumFragments(node: WorkflowNode): FragmentSource[] {
  const path = asString(node.params.path) ?? "";
  const valueType = node.params.value_type as EnumValueType;
  const values = Array.isArray(node.params.values) ? (node.params.values as EnumValue[]) : [];
  return values.map((item) => ({
    item_id: item.item_id,
    path,
    value: enumValueToFragment(item.value, valueType),
  }));
}

function enumValueToFragment(value: string | number, valueType: EnumValueType): unknown {
  switch (valueType) {
    case "asset":
      return { asset_key: String(value) };
    case "number":
      return typeof value === "number" ? value : Number(value);
    case "string":
      return String(value);
    case "json_fragment":
      return JSON.parse(String(value)) as unknown;
  }
}

function rangeFragments(node: WorkflowNode): FragmentSource[] {
  const path = asString(node.params.path) ?? "";
  const entries = rangeEntries(
    asNumber(node.params.start) ?? 0,
    asNumber(node.params.end) ?? 0,
    asNumber(node.params.step) ?? 1,
  );
  return entries.map((entry) => ({
    item_id: `range:${path}:${entry.key}`,
    path,
    value: entry.value,
  }));
}

export function validateNode(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const params = node.params;

  switch (node.kind) {
    case "root": {
      const filePath = params.file_path;
      if (typeof filePath === "string" && filePath.trim() !== "") {
        diagnostics.push(
          paramError(node, "file_path", "MVP 暂不支持从文件导入根文档"),
        );
      }
      break;
    }
    case "meta":
      break;
    case "character":
      if (!isPositiveInteger(params.slot)) {
        diagnostics.push(paramError(node, "slot", "槽位必须是 >= 1 的整数"));
      }
      if (asString(params.asset) === null) {
        diagnostics.push(paramError(node, "asset", "缺少资产引用"));
      }
      if (params.level !== undefined && !isPositiveInteger(params.level)) {
        diagnostics.push(paramError(node, "level", "等级必须是 >= 1 的整数"));
      }
      if (params.constellation !== undefined && !isInRange(params.constellation, 0, 6)) {
        diagnostics.push(paramError(node, "constellation", "命座必须在 0 到 6 之间"));
      }
      if (params.talents !== undefined && !isPlainObject(params.talents)) {
        diagnostics.push(paramError(node, "talents", "talents 必须是对象"));
      }
      break;
    case "weapon": {
      if (!isPositiveInteger(params.slot)) {
        diagnostics.push(paramError(node, "slot", "槽位必须是 >= 1 的整数"));
      }
      if (asString(params.asset) === null) {
        diagnostics.push(paramError(node, "asset", "缺少资产引用"));
      }
      if (params.level !== undefined && !isPositiveInteger(params.level)) {
        diagnostics.push(paramError(node, "level", "等级必须是 >= 1 的整数"));
      }
      if (params.refinement !== undefined && !isInRange(params.refinement, 1, 5)) {
        diagnostics.push(paramError(node, "refinement", "精炼必须在 1 到 5 之间"));
      }
      break;
    }
    case "artifact": {
      if (!isPositiveInteger(params.slot)) {
        diagnostics.push(paramError(node, "slot", "槽位必须是 >= 1 的整数"));
      }
      if (asString(params.asset) === null) {
        diagnostics.push(paramError(node, "asset", "缺少资产引用"));
      }
      if (params.pieces !== undefined && !isPositiveInteger(params.pieces)) {
        diagnostics.push(paramError(node, "pieces", "件数必须是 >= 1 的整数"));
      }
      break;
    }
    case "target": {
      if (!isNonNegativeInteger(params.index)) {
        diagnostics.push(paramError(node, "index", "目标索引必须是 >= 0 的整数"));
      }
      if (params.id !== undefined && asString(params.id) === null) {
        diagnostics.push(paramError(node, "id", "目标 id 必须是字符串"));
      }
      if (params.level !== undefined && !isPositiveInteger(params.level)) {
        diagnostics.push(paramError(node, "level", "等级必须是 >= 1 的整数"));
      }
      break;
    }
    case "input_trace": {
      if (!Array.isArray(params.items)) {
        diagnostics.push(paramError(node, "items", "items 必须是数组"));
      }
      break;
    }
    case "run_options": {
      if (params.max_frames !== undefined && !isPositiveInteger(params.max_frames)) {
        diagnostics.push(paramError(node, "max_frames", "max_frames 必须是 >= 1 的整数"));
      }
      break;
    }
    case "enum": {
      if (!isValidPath(params.path)) {
        diagnostics.push(paramError(node, "path", "路径语法错误"));
      }
      if (!isEnumValueType(params.value_type)) {
        diagnostics.push(paramError(node, "value_type", "未知取值类型"));
      }
      if (!Array.isArray(params.values) || params.values.length === 0) {
        diagnostics.push(paramError(node, "values", "values 至少需要一项"));
      } else {
        const seen = new Set<string>();
        for (const [index, item] of (params.values as unknown[]).entries()) {
          const enumItem = item as Partial<EnumValue>;
          if (typeof enumItem.item_id !== "string" || enumItem.item_id === "") {
            diagnostics.push(
              paramError(node, `values[${index}].item_id`, "取值 item_id 不能为空"),
            );
          } else if (seen.has(enumItem.item_id)) {
            diagnostics.push(
              paramError(node, `values[${index}].item_id`, `item_id 重复：${enumItem.item_id}`),
            );
          }
          seen.add(enumItem.item_id ?? "");
          if (enumItem.value === undefined || enumItem.value === null) {
            diagnostics.push(paramError(node, `values[${index}].value`, "取值不能为空"));
          }
          if (params.value_type === "json_fragment") {
            try {
              JSON.parse(String(enumItem.value));
            } catch {
              diagnostics.push(
                paramError(node, `values[${index}].value`, "json_fragment 无法解析"),
              );
            }
          }
        }
      }
      break;
    }
    case "range": {
      if (!isValidPath(params.path)) {
        diagnostics.push(paramError(node, "path", "路径语法错误"));
      }
      const start = asNumber(params.start);
      const end = asNumber(params.end);
      const step = asNumber(params.step);
      if (start === null) {
        diagnostics.push(paramError(node, "start", "起点必须是有限数字"));
      }
      if (end === null) {
        diagnostics.push(paramError(node, "end", "终点必须是有限数字"));
      }
      if (step === null || step <= 0) {
        diagnostics.push(paramError(node, "step", "步长必须是大于 0 的数字"));
      }
      if (start !== null && end !== null && start > end) {
        diagnostics.push(paramError(node, "start", "起点不能大于终点"));
      }
      break;
    }
    case "simulation":
      break;
    default:
      break;
  }

  return diagnostics;
}

function paramError(node: WorkflowNode, path: string, message: string): Diagnostic {
  return {
    severity: "error",
    code: "PARAM_INVALID",
    message,
    node_id: node.id,
    edge_id: null,
    region_id: node.region_id,
    path,
  };
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function asInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function isNonNegativeInteger(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isPositiveInteger(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 1;
}

function isInRange(value: unknown, min: number, max: number): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= min && value <= max;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isEnumValueType(value: unknown): value is EnumValueType {
  return value === "asset" || value === "number" || value === "string" || value === "json_fragment";
}

function isValidPath(path: unknown): boolean {
  if (typeof path !== "string") {
    return false;
  }
  try {
    parsePath(path);
    return true;
  } catch {
    return false;
  }
}
