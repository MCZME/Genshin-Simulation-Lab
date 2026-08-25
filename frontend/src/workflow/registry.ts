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
import { SUPPORTED_INPUT_KEYS } from "./inputKeys";
import { parsePath } from "./path";
import { MAX_ANALYSIS_SESSION_IDS } from "./types";

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

export interface FragmentSource {
  item_id: string;
  path: string;
  value: unknown;
}

export interface NodeKindSpec {
  kind: NodeKind;
  displayName: string;
  /** 所属区域类型；null 表示画布级节点，不归属任何区域。 */
  region: RegionKind | null;
  ports: {
    inputs: PortSpec[];
    outputs: PortSpec[];
  };
  paramFields: Record<string, ParamFieldSpec>;
  /** 创建节点时写入的默认参数；编译阶段在没有显式参数时沿用同一默认值。 */
  defaultParams: Record<string, unknown>;
  /** 片段形状：默认目标路径与值构造；枚举/区间由 groupFragments 提供多个来源。 */
  fragment: (node: WorkflowNode, definition: WorkflowDefinition) => FragmentSource | null;
  groupFragments?: (node: WorkflowNode) => FragmentSource[];
  /** 节点级校验规则。 */
  validate: (node: WorkflowNode) => Diagnostic[];
}

function fragmentPort(
  id: string,
  cardinality: PortCardinality,
  connectionLimit = Number.POSITIVE_INFINITY,
): PortSpec {
  return { id, cardinality, dataLanguage: "fragment", connectionLimit };
}

function rootFragment(): FragmentSource | null {
  return null;
}

function metaFragment(node: WorkflowNode): FragmentSource | null {
  const params = node.params;
  return {
    item_id: `node:${node.id}`,
    path: "meta",
    value: {
      name: asString(params.name) ?? "",
      description: asString(params.description) ?? "",
    },
  };
}

function characterFragment(
  node: WorkflowNode,
): FragmentSource | null {
  const params = node.params;
  const slot = asInteger(params.slot) ?? 1;
  const asset = asString(params.asset);
  if (asset === null) {
    return null;
  }
  return {
    item_id: `node:${node.id}`,
    path: asString(params.path) ?? `team[${slot - 1}].character`,
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

function weaponFragment(
  node: WorkflowNode,
): FragmentSource | null {
  const params = node.params;
  const slot = asInteger(params.slot) ?? 1;
  const asset = asString(params.asset);
  if (asset === null) {
    return null;
  }
  return {
    item_id: `node:${node.id}`,
    path: asString(params.path) ?? `team[${slot - 1}].weapon`,
    value: {
      asset_key: asset,
      level: asInteger(params.level) ?? 90,
      refinement: asInteger(params.refinement) ?? 1,
    },
  };
}

function artifactFragment(
  node: WorkflowNode,
): FragmentSource | null {
  const params = node.params;
  const slot = asInteger(params.slot) ?? 1;
  const sets = Array.isArray(params.sets)
    ? (params.sets as unknown[])
        .filter((entry): entry is Record<string, unknown> => isPlainObject(entry))
        .filter((entry) => asString(entry.asset_key) !== null)
        .map((entry) => ({
          asset_key: entry.asset_key as string,
          pieces: asInteger(entry.pieces) ?? 4,
        }))
    : [];
  if (sets.length === 0) {
    return null;
  }
  return {
    item_id: `node:${node.id}`,
    path: asString(params.path) ?? `team[${slot - 1}].artifacts`,
    value: {
      sets,
      stats: {},
    },
  };
}

/** 目标抗性支持的 8 个元素键；与后端 RESISTANCE_KEYS_BY_ELEMENT 保持一致。 */
export const RESISTANCE_ELEMENT_KEYS: readonly string[] = [
  "physical",
  "pyro",
  "hydro",
  "electro",
  "cryo",
  "anemo",
  "geo",
  "dendro",
];

const DEFAULT_TARGET_POSITION: Record<string, number> = { x: 0, y: 0, z: 5 };

const DEFAULT_TARGET_RESISTANCE: Record<string, number> = {
  physical: 10,
  pyro: 10,
  hydro: 10,
  electro: 10,
  cryo: 10,
  anemo: 10,
  geo: 10,
  dendro: 10,
};

function targetFragment(
  node: WorkflowNode,
): FragmentSource | null {
  const params = node.params;
  const index = asInteger(params.index) ?? 0;
  const position = isPlainObject(params.position) ? params.position : {};
  const resistance = isPlainObject(params.resistance) ? params.resistance : {};
  const resistanceValues: Record<string, number> = {};
  for (const key of RESISTANCE_ELEMENT_KEYS) {
    resistanceValues[key] = asNumber(resistance[key]) ?? DEFAULT_TARGET_RESISTANCE[key];
  }
  return {
    item_id: `node:${node.id}`,
    path: asString(params.path) ?? `scene.targets[${index}]`,
    value: {
      id: `target_${index}`,
      label: asString(params.label) ?? "遗迹守卫",
      level: asInteger(params.level) ?? 90,
      position: {
        x: asNumber(position.x) ?? DEFAULT_TARGET_POSITION.x,
        y: asNumber(position.y) ?? DEFAULT_TARGET_POSITION.y,
        z: asNumber(position.z) ?? DEFAULT_TARGET_POSITION.z,
      },
      resistance: resistanceValues,
    },
  };
}

function inputTraceFragment(
  node: WorkflowNode,
): FragmentSource | null {
  return {
    item_id: `node:${node.id}`,
    path: asString(node.params.path) ?? "input_trace",
    value: Array.isArray(node.params.items) ? node.params.items : [],
  };
}

function runOptionsFragment(
  node: WorkflowNode,
): FragmentSource | null {
  return {
    item_id: `node:${node.id}`,
    path: asString(node.params.path) ?? "run_options",
    value: { max_frames: asInteger(node.params.max_frames) ?? 18000 },
  };
}

function enumGroupFragments(node: WorkflowNode): FragmentSource[] {
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

function rangeGroupFragments(node: WorkflowNode): FragmentSource[] {
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

function validateRoot(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const filePath = node.params.file_path;
  if (typeof filePath === "string" && filePath.trim() !== "") {
    diagnostics.push(paramError(node, "file_path", "MVP 暂不支持从文件导入根文档"));
  }
  return diagnostics;
}

function validateMeta(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const name = node.params.name;
  if (typeof name !== "string" || name.trim() === "") {
    diagnostics.push(paramError(node, "name", "名称不能为空"));
  }
  if (node.params.description !== undefined && typeof node.params.description !== "string") {
    diagnostics.push(paramError(node, "description", "描述必须是字符串"));
  }
  return diagnostics;
}

function validateCharacter(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const params = node.params;
  checkCustomPath(node, diagnostics);
  if (!isInRange(params.slot, 1, 4)) {
    diagnostics.push(paramError(node, "slot", "槽位必须在 1 到 4 之间"));
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
  } else {
    const talents = isPlainObject(params.talents) ? params.talents : {};
    for (const key of ["normal_attack", "elemental_skill", "elemental_burst"]) {
      if (talents[key] !== undefined && !isInRange(talents[key], 1, 10)) {
        diagnostics.push(
          paramError(node, `talents.${key}`, "天赋等级必须在 1 到 10 之间"),
        );
      }
    }
  }
  return diagnostics;
}

function validateWeapon(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const params = node.params;
  checkCustomPath(node, diagnostics);
  if (!isInRange(params.slot, 1, 4)) {
    diagnostics.push(paramError(node, "slot", "槽位必须在 1 到 4 之间"));
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
  return diagnostics;
}

function validateArtifact(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const params = node.params;
  checkCustomPath(node, diagnostics);
  if (!isInRange(params.slot, 1, 4)) {
    diagnostics.push(paramError(node, "slot", "槽位必须在 1 到 4 之间"));
  }
  const sets = params.sets;
  if (!Array.isArray(sets)) {
    diagnostics.push(paramError(node, "sets", "sets 必须是数组"));
    return diagnostics;
  }
  if (sets.length < 1) {
    diagnostics.push(paramError(node, "sets", "至少需要一条套装"));
  }
  if (sets.length > 2) {
    diagnostics.push(paramError(node, "sets", "圣遗物套装最多 2 条"));
  }
  sets.forEach((raw, index) => {
    const prefix = `sets[${index}]`;
    const entry = raw as Record<string, unknown> | null;
    if (!isPlainObject(entry)) {
      diagnostics.push(paramError(node, prefix, "套装条目必须是对象"));
      return;
    }
    if (asString(entry.asset_key) === null) {
      diagnostics.push(paramError(node, `${prefix}.asset_key`, "缺少资产引用"));
    }
    if (entry.pieces !== undefined && ![1, 2, 4].includes(entry.pieces as number)) {
      diagnostics.push(paramError(node, `${prefix}.pieces`, "件数必须是 1、2 或 4"));
    }
  });
  if (!sets.some((raw) => asString((raw as Record<string, unknown> | null)?.asset_key) !== null)) {
    diagnostics.push(paramError(node, "sets", "至少需要一条已选套装的配置"));
  }
  return diagnostics;
}

function validateTarget(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const params = node.params;
  checkCustomPath(node, diagnostics);
  if (!isNonNegativeInteger(params.index)) {
    diagnostics.push(paramError(node, "index", "目标索引必须是 >= 0 的整数"));
  }
  if (params.label !== undefined && typeof params.label !== "string") {
    diagnostics.push(paramError(node, "label", "目标名称必须是字符串"));
  }
  if (params.level !== undefined && !isPositiveInteger(params.level)) {
    diagnostics.push(paramError(node, "level", "等级必须是 >= 1 的整数"));
  }
  const position = params.position;
  if (position !== undefined) {
    if (!isPlainObject(position)) {
      diagnostics.push(paramError(node, "position", "位置必须是对象"));
    } else {
      for (const axis of ["x", "y", "z"]) {
        const value = position[axis];
        if (value !== undefined && !isFiniteNumber(value)) {
          diagnostics.push(
            paramError(node, `position.${axis}`, `${axis.toUpperCase()} 必须是有限数字`),
          );
        }
      }
    }
  }
  const resistance = params.resistance;
  if (resistance !== undefined) {
    if (!isPlainObject(resistance)) {
      diagnostics.push(paramError(node, "resistance", "抗性必须是对象"));
    } else {
      for (const [key, value] of Object.entries(resistance)) {
        if (!RESISTANCE_ELEMENT_KEYS.includes(key)) {
          diagnostics.push(paramError(node, `resistance.${key}`, "不支持的目标抗性条目"));
        } else if (!isFiniteNumber(value)) {
          diagnostics.push(paramError(node, `resistance.${key}`, "抗性必须是有限数字"));
        }
      }
    }
  }
  return diagnostics;
}

function validateInputTrace(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const params = node.params;
  checkCustomPath(node, diagnostics);
  const items = params.items;
  if (!Array.isArray(items)) {
    diagnostics.push(paramError(node, "items", "items 必须是数组"));
    return diagnostics;
  }
  if (
    params.tracks !== undefined &&
    (!Array.isArray(params.tracks) ||
      params.tracks.some((track) => typeof track !== "string"))
  ) {
    diagnostics.push(paramError(node, "tracks", "tracks 必须是字符串数组"));
  }
  const sorted = (items as unknown[])
    .filter((item): item is Record<string, unknown> => item !== null && typeof item === "object")
    .sort((a, b) => (Number(a.frame) || 0) - (Number(b.frame) || 0));
  items.forEach((item, index) => {
    const record = item as Record<string, unknown> | null;
    if (record === null || typeof record !== "object") {
      diagnostics.push(paramError(node, `items[${index}]`, "事件项必须是对象"));
      return;
    }
    if (
      typeof record.frame !== "number" ||
      !Number.isInteger(record.frame) ||
      record.frame <= 0
    ) {
      diagnostics.push(paramError(node, `items[${index}].frame`, "帧号必须是正整数"));
    }
    if (!Array.isArray(record.events)) {
      diagnostics.push(paramError(node, `items[${index}].events`, "events 必须是数组"));
      return;
    }
    record.events.forEach((event, eventIndex) => {
      const eventRecord = event as Record<string, unknown> | null;
      if (
        eventRecord === null ||
        typeof eventRecord !== "object" ||
        typeof eventRecord.key !== "string" ||
        eventRecord.key === ""
      ) {
        diagnostics.push(
          paramError(node, `items[${index}].events[${eventIndex}].key`, "按键 key 必须是字符串"),
        );
        return;
      }
      if (!SUPPORTED_INPUT_KEYS.includes(eventRecord.key)) {
        diagnostics.push(
          paramError(
            node,
            `items[${index}].events[${eventIndex}].key`,
            `不支持的按键 ${eventRecord.key}`,
          ),
        );
      }
      if (eventRecord.phase !== "press" && eventRecord.phase !== "release") {
        diagnostics.push(
          paramError(
            node,
            `items[${index}].events[${eventIndex}].phase`,
            "phase 必须是 press 或 release",
          ),
        );
      }
    });
  });
  const openByKey = new Map<string, number>();
  for (const item of sorted) {
    const events = Array.isArray(item.events) ? (item.events as unknown[]) : [];
    for (const event of events) {
      const record = event as Record<string, unknown> | null;
      if (record === null || typeof record !== "object" || typeof record.key !== "string") {
        continue;
      }
      const open = openByKey.get(record.key) ?? 0;
      if (record.phase === "press") {
        openByKey.set(record.key, open + 1);
      } else if (record.phase === "release") {
        if (open <= 0) {
          diagnostics.push(paramError(node, "items", `按键 ${record.key} 存在未配对的松开事件`));
        } else {
          openByKey.set(record.key, open - 1);
        }
      }
    }
  }
  for (const [key, open] of openByKey) {
    if (open > 0) {
      diagnostics.push(paramError(node, "items", `按键 ${key} 存在未闭合的按下事件`));
    }
  }
  return diagnostics;
}

function validateRunOptions(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  checkCustomPath(node, diagnostics);
  const maxFrames = node.params.max_frames;
  if (maxFrames !== undefined && !isPositiveInteger(maxFrames)) {
    diagnostics.push(paramError(node, "max_frames", "max_frames 必须是 >= 1 的整数"));
  }
  return diagnostics;
}

function validateEnum(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const params = node.params;
  if (!isValidPath(params.path)) {
    diagnostics.push(paramError(node, "path", "路径语法错误"));
  }
  if (!isEnumValueType(params.value_type)) {
    diagnostics.push(paramError(node, "value_type", "未知取值类型"));
  }
  if (!Array.isArray(params.values) || params.values.length === 0) {
    diagnostics.push(paramError(node, "values", "values 至少需要一项"));
    return diagnostics;
  }
  const seen = new Set<string>();
  for (const [index, item] of (params.values as unknown[]).entries()) {
    const enumItem = item as Partial<EnumValue>;
    if (typeof enumItem.item_id !== "string" || enumItem.item_id === "") {
      diagnostics.push(paramError(node, `values[${index}].item_id`, "取值 item_id 不能为空"));
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
  return diagnostics;
}

function validateRange(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const params = node.params;
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
  return diagnostics;
}

function validateSimulation(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const concurrency = node.params.concurrency;
  if (concurrency !== undefined && !isInRange(concurrency, 1, 16)) {
    diagnostics.push(paramError(node, "concurrency", "并发度必须在 1 到 16 之间"));
  }
  return diagnostics;
}

function analysisPort(
  id: string,
  dataLanguage: DataLanguage,
  cardinality: PortCardinality = "single",
  connectionLimit = Number.POSITIVE_INFINITY,
): PortSpec {
  return { id, cardinality, dataLanguage, connectionLimit };
}

function validateDataProvider(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const sessionIds = node.params.session_ids;
  if (
    sessionIds !== undefined &&
    (!Array.isArray(sessionIds) ||
      !sessionIds.every((item) => typeof item === "string"))
  ) {
    diagnostics.push(paramError(node, "session_ids", "session_ids 必须是字符串数组"));
    return diagnostics;
  }
  if (sessionIds === undefined) {
    return diagnostics;
  }
  if (sessionIds.length > MAX_ANALYSIS_SESSION_IDS) {
    diagnostics.push(
      paramError(
        node,
        "session_ids",
        `session_ids 最多 ${MAX_ANALYSIS_SESSION_IDS} 个`,
      ),
    );
  }
  const seen = new Set<string>();
  for (const [index, sessionId] of sessionIds.entries()) {
    if (seen.has(sessionId)) {
      diagnostics.push(
        paramError(node, `session_ids[${index}]`, `session_id 重复：${sessionId}`),
      );
    }
    seen.add(sessionId);
  }
  return diagnostics;
}


function validateTableConfig(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const condition = node.params.condition_columns;
  const data = node.params.data_columns;
  if (condition !== undefined && !isStringArray(condition)) {
    diagnostics.push(paramError(node, "condition_columns", "条件列必须是字符串数组"));
  }
  if (data !== undefined && !isStringArray(data)) {
    diagnostics.push(paramError(node, "data_columns", "数据列必须是字符串数组"));
  }
  const conditionCount = Array.isArray(condition) ? condition.length : 0;
  const dataCount = Array.isArray(data) ? data.length : 0;
  if (conditionCount + dataCount === 0) {
    diagnostics.push(paramError(node, "condition_columns", "至少需要一个条件列或数据列"));
  }
  return diagnostics;
}

function validateRoleColumns(
  node: WorkflowNode,
  requiredRoles: string[],
): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  for (const role of requiredRoles) {
    const value = node.params[role];
    if (typeof value !== "string" || value.trim() === "") {
      diagnostics.push(paramError(node, role, `列绑定不能为空：${role}`));
    }
  }
  return diagnostics;
}

function validateTimelineConfig(node: WorkflowNode): Diagnostic[] {
  return validateRoleColumns(node, ["track", "start"]);
}

function validatePieConfig(node: WorkflowNode): Diagnostic[] {
  return validateRoleColumns(node, ["group", "value"]);
}

function validateBarConfig(node: WorkflowNode): Diagnostic[] {
  return validateRoleColumns(node, ["x", "y"]);
}

function validateView(): Diagnostic[] {
  return [];
}

function isStringArray(value: unknown): boolean {
  return (
    Array.isArray(value) && value.every((item) => typeof item === "string")
  );
}

export const REGISTRY: Record<NodeKind, NodeKindSpec> = {
  root: {
    kind: "root",
    displayName: "根节点",
    region: "configuration",
    ports: { inputs: [], outputs: [fragmentPort("out", "single", Number.POSITIVE_INFINITY)] },
    paramFields: { file_path: { type: "string" } },
    defaultParams: {},
    fragment: rootFragment,
    validate: validateRoot,
  },
  meta: {
    kind: "meta",
    displayName: "元信息",
    region: "configuration",
    ports: {
      inputs: [fragmentPort("in", "single")],
      outputs: [fragmentPort("out", "single", Number.POSITIVE_INFINITY)],
    },
    paramFields: {
      name: { type: "string", required: true },
      description: { type: "string" },
    },
    defaultParams: { name: "", description: "" },
    fragment: metaFragment,
    validate: validateMeta,
  },
  character: {
    kind: "character",
    displayName: "角色",
    region: "configuration",
    ports: {
      inputs: [fragmentPort("in", "single")],
      outputs: [fragmentPort("out", "single", Number.POSITIVE_INFINITY)],
    },
    paramFields: {
      slot: { type: "integer", required: true },
      asset: { type: "asset_ref", required: true, assetType: "characters" },
      level: { type: "integer", default: 90 },
      constellation: { type: "integer", default: 0 },
      talents: { type: "object", default: { normal_attack: 1, elemental_skill: 1, elemental_burst: 1 } },
    },
    defaultParams: {
      slot: 1,
      asset: "",
      level: 90,
      constellation: 0,
      talents: { normal_attack: 1, elemental_skill: 1, elemental_burst: 1 },
    },
    fragment: characterFragment,
    validate: validateCharacter,
  },
  weapon: {
    kind: "weapon",
    displayName: "武器",
    region: "configuration",
    ports: {
      inputs: [fragmentPort("in", "single")],
      outputs: [fragmentPort("out", "single", Number.POSITIVE_INFINITY)],
    },
    paramFields: {
      slot: { type: "integer", required: true },
      asset: { type: "asset_ref", required: true, assetType: "weapons" },
      level: { type: "integer", default: 90 },
      refinement: { type: "integer", default: 1 },
    },
    defaultParams: { slot: 1, asset: "", level: 90, refinement: 1 },
    fragment: weaponFragment,
    validate: validateWeapon,
  },
  artifact: {
    kind: "artifact",
    displayName: "圣遗物",
    region: "configuration",
    ports: {
      inputs: [fragmentPort("in", "single")],
      outputs: [fragmentPort("out", "single", Number.POSITIVE_INFINITY)],
    },
    paramFields: {
      slot: { type: "integer", required: true },
      sets: { type: "list", required: true },
    },
    defaultParams: { slot: 1, sets: [{ asset_key: "", pieces: 4 }] },
    fragment: artifactFragment,
    validate: validateArtifact,
  },
  target: {
    kind: "target",
    displayName: "目标",
    region: "configuration",
    ports: {
      inputs: [fragmentPort("in", "single")],
      outputs: [fragmentPort("out", "single", Number.POSITIVE_INFINITY)],
    },
    paramFields: {
      index: { type: "integer", required: true },
      label: { type: "string" },
      level: { type: "integer", default: 90 },
      position: { type: "object", default: DEFAULT_TARGET_POSITION },
      resistance: { type: "object", default: DEFAULT_TARGET_RESISTANCE },
    },
    defaultParams: {
      index: 0,
      label: "遗迹守卫",
      level: 90,
      position: DEFAULT_TARGET_POSITION,
      resistance: DEFAULT_TARGET_RESISTANCE,
    },
    fragment: targetFragment,
    validate: validateTarget,
  },
  input_trace: {
    kind: "input_trace",
    displayName: "按键轨迹",
    region: "configuration",
    ports: {
      inputs: [fragmentPort("in", "single")],
      outputs: [fragmentPort("out", "single", Number.POSITIVE_INFINITY)],
    },
    paramFields: {
      items: { type: "list", required: true },
    },
    defaultParams: { items: [] },
    fragment: inputTraceFragment,
    validate: validateInputTrace,
  },
  run_options: {
    kind: "run_options",
    displayName: "运行选项",
    region: "configuration",
    ports: {
      inputs: [fragmentPort("in", "single")],
      outputs: [fragmentPort("out", "single", Number.POSITIVE_INFINITY)],
    },
    paramFields: { max_frames: { type: "integer", default: 18000 } },
    defaultParams: { max_frames: 18000 },
    fragment: runOptionsFragment,
    validate: validateRunOptions,
  },
  enum: {
    kind: "enum",
    displayName: "枚举",
    region: "configuration",
    ports: {
      inputs: [fragmentPort("in", "single")],
      outputs: [fragmentPort("out", "group", Number.POSITIVE_INFINITY)],
    },
    paramFields: {
      path: { type: "string", required: true },
      value_type: { type: "string", required: true },
      values: { type: "list", required: true },
    },
    defaultParams: {
      path: "",
      value_type: "asset",
      values: [{ item_id: "e-1", value: "", label: null }],
    },
    fragment: () => null,
    groupFragments: enumGroupFragments,
    validate: validateEnum,
  },
  range: {
    kind: "range",
    displayName: "区间",
    region: "configuration",
    ports: {
      inputs: [fragmentPort("in", "single")],
      outputs: [fragmentPort("out", "group", Number.POSITIVE_INFINITY)],
    },
    paramFields: {
      path: { type: "string", required: true },
      start: { type: "number", required: true },
      end: { type: "number", required: true },
      step: { type: "number", required: true },
      label: { type: "string" },
    },
    defaultParams: { path: "", start: 1, end: 10, step: 1, label: null },
    fragment: () => null,
    groupFragments: rangeGroupFragments,
    validate: validateRange,
  },
  simulation: {
    kind: "simulation",
    displayName: "模拟节点",
    region: null,
    ports: {
      inputs: [
        {
          id: "in",
          cardinality: "single",
          dataLanguage: "input_document",
          connectionLimit: Number.POSITIVE_INFINITY,
        },
      ],
      outputs: [
        { id: "out", cardinality: "group", dataLanguage: "session_group", connectionLimit: 1 },
      ],
    },
    paramFields: {
      concurrency: { type: "integer" },
    },
    defaultParams: {},
    fragment: () => null,
    validate: validateSimulation,
  },
  data_provider: {
    kind: "data_provider",
    displayName: "数据提供",
    region: null,
    ports: {
      inputs: [],
      outputs: [analysisPort("out", "session_group", "group")],
    },
    paramFields: {
      session_ids: { type: "list" },
    },
    defaultParams: { session_ids: [] },
    fragment: () => null,
    validate: validateDataProvider,
  },
  fetch: {
    kind: "fetch",
    displayName: "获取数据",
    region: "analysis",
    ports: {
      inputs: [
        { id: "in", cardinality: "single", dataLanguage: "session_group", connectionLimit: 1 },
      ],
      outputs: [{ id: "out", cardinality: "group", dataLanguage: "table", connectionLimit: Number.POSITIVE_INFINITY }],
    },
    paramFields: {
      source: { type: "string", required: true },
      snapshot_columns: { type: "list" },
      event_types: { type: "list" },
      frame_min: { type: "integer" },
      frame_max: { type: "integer" },
      payload_columns: { type: "list" },
    },
    defaultParams: { source: "runs", snapshot_columns: [] },
    fragment: () => null,
    validate: validateFetchNode,
  },
  filter: _operator("filter", "过滤"),
  project: _operator("project", "投影"),
  sort: _operator("sort", "排序"),
  aggregate: _operator("aggregate", "分组聚合"),
  limit: _operator("limit", "截断"),
  join: {
    kind: "join",
    displayName: "连接",
    region: "analysis",
    ports: {
      inputs: [
        { id: "left", cardinality: "single", dataLanguage: "table", connectionLimit: 1 },
        { id: "right", cardinality: "single", dataLanguage: "table", connectionLimit: 1 },
      ],
      outputs: [{ id: "out", cardinality: "single", dataLanguage: "table", connectionLimit: Number.POSITIVE_INFINITY }],
    },
    paramFields: {},
    defaultParams: {},
    fragment: () => null,
    validate: () => [],
  },
  compute: _operator("compute", "计算列"),
  table_config: {
    kind: "table_config",
    displayName: "表格配置",
    region: "analysis",
    ports: {
      inputs: [],
      outputs: [analysisPort("out", "table_config", "single", 1)],
    },
    paramFields: {
      condition_columns: { type: "list" },
      data_columns: { type: "list" },
    },
    defaultParams: { condition_columns: [], data_columns: [] },
    fragment: () => null,
    validate: validateTableConfig,
  },
  timeline_config: {
    kind: "timeline_config",
    displayName: "时间轴配置",
    region: "analysis",
    ports: {
      inputs: [],
      outputs: [analysisPort("out", "timeline_config", "single", 1)],
    },
    paramFields: {
      track: { type: "string", required: true },
      start: { type: "string", required: true },
      end: { type: "string" },
      value: { type: "string" },
      label: { type: "string" },
    },
    defaultParams: { track: "", start: "", end: "", value: "", label: "" },
    fragment: () => null,
    validate: validateTimelineConfig,
  },
  pie_config: {
    kind: "pie_config",
    displayName: "饼图配置",
    region: "analysis",
    ports: {
      inputs: [],
      outputs: [analysisPort("out", "pie_config", "single", 1)],
    },
    paramFields: {
      group: { type: "string", required: true },
      value: { type: "string", required: true },
      label: { type: "string" },
    },
    defaultParams: { group: "", value: "", label: "" },
    fragment: () => null,
    validate: validatePieConfig,
  },
  bar_config: {
    kind: "bar_config",
    displayName: "柱状图配置",
    region: "analysis",
    ports: {
      inputs: [],
      outputs: [analysisPort("out", "bar_config", "single", 1)],
    },
    paramFields: {
      x: { type: "string", required: true },
      y: { type: "string", required: true },
      series: { type: "string" },
    },
    defaultParams: { x: "", y: "", series: "" },
    fragment: () => null,
    validate: validateBarConfig,
  },
  member_table: {
    kind: "member_table",
    displayName: "成员指标表",
    region: "analysis",
    ports: {
      inputs: [
        analysisPort("in", "table", "single", Number.POSITIVE_INFINITY),
        analysisPort("config", "table_config", "single", 1),
      ],
      outputs: [],
    },
    paramFields: {},
    defaultParams: {},
    fragment: () => null,
    validate: validateView,
  },
  timeline: {
    kind: "timeline",
    displayName: "单场时间轴",
    region: "analysis",
    ports: {
      inputs: [
        analysisPort("in", "table", "single", Number.POSITIVE_INFINITY),
        analysisPort("config", "timeline_config", "single", 1),
      ],
      outputs: [],
    },
    paramFields: {},
    defaultParams: {},
    fragment: () => null,
    validate: validateView,
  },
  pie: {
    kind: "pie",
    displayName: "占比饼图",
    region: "analysis",
    ports: {
      inputs: [
        analysisPort("in", "table", "single", Number.POSITIVE_INFINITY),
        analysisPort("config", "pie_config", "single", 1),
      ],
      outputs: [],
    },
    paramFields: {},
    defaultParams: {},
    fragment: () => null,
    validate: validateView,
  },
  bar: {
    kind: "bar",
    displayName: "指标柱状图",
    region: "analysis",
    ports: {
      inputs: [
        analysisPort("in", "table", "single", Number.POSITIVE_INFINITY),
        analysisPort("config", "bar_config", "single", 1),
      ],
      outputs: [],
    },
    paramFields: {},
    defaultParams: {},
    fragment: () => null,
    validate: validateView,
  },
};

function _operator(kind: NodeKind, displayName: string): NodeKindSpec {
  return {
    kind,
    displayName,
    region: "analysis",
    ports: {
      inputs: [
        { id: "in", cardinality: "single", dataLanguage: "table", connectionLimit: 1 },
      ],
      outputs: [
        { id: "out", cardinality: "single", dataLanguage: "table", connectionLimit: Number.POSITIVE_INFINITY },
      ],
    },
    paramFields: {},
    defaultParams: {},
    fragment: () => null,
    validate: () => [],
  };
}

/** 取数节点基础校验：来源与提取列结构在形状推导阶段深入检查。 */
function validateFetchNode(node: WorkflowNode): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const source = node.params.source;
  if (source !== "runs" && source !== "events") {
    diagnostics.push(paramError(node, "source", "source 必须是 runs 或 events"));
  }
  for (const key of ["snapshot_columns", "payload_columns"] as const) {
    const rows = node.params[key];
    if (rows !== undefined && !Array.isArray(rows)) {
      diagnostics.push(paramError(node, key, key + " 必须是数组"));
    }
  }
  const types = node.params.event_types;
  if (types !== undefined && !Array.isArray(types)) {
    diagnostics.push(paramError(node, "event_types", "event_types 必须是字符串数组"));
  }
  return diagnostics;
}

export function getNodeKindSpec(kind: string): NodeKindSpec | null {
  return (REGISTRY as Record<string, NodeKindSpec>)[kind] ?? null;
}

/** 枚举/区间节点的成员 item_id 列表；成员投影端口以 `out:<item_id>` 命名。 */
export function memberItemIds(node: WorkflowNode): string[] {
  if (node.kind === "enum") {
    const values = Array.isArray(node.params.values) ? (node.params.values as EnumValue[]) : [];
    return values.map((item) => item.item_id).filter((itemId) => itemId !== "");
  }
  if (node.kind === "range") {
    return groupFragments(node).map((fragment) => fragment.item_id);
  }
  return [];
}

export function isProjectionPort(node: WorkflowNode, portId: string): boolean {
  return (node.kind === "enum" || node.kind === "range") && portId.startsWith("out:");
}

export function projectionItemId(portId: string): string {
  return portId.slice("out:".length);
}

/** 前端创建节点时写入的默认参数；编译阶段在没有显式参数时沿用同一默认值。 */
export function createDefaultParams(kind: string): Record<string, unknown> {
  const spec = getNodeKindSpec(kind);
  return spec === null ? {} : structuredClone(spec.defaultParams);
}

/** 单值节点产出一个片段；根节点与模拟节点不产出来源。 */
export function singleFragment(
  node: WorkflowNode,
  definition: WorkflowDefinition,
): FragmentSource | null {
  const spec = getNodeKindSpec(node.kind);
  return spec === null ? null : spec.fragment(node, definition);
}

/** 枚举/区间节点产出按取值展开的多个片段来源。 */
export function groupFragments(node: WorkflowNode): FragmentSource[] {
  const spec = getNodeKindSpec(node.kind);
  return spec?.groupFragments?.(node) ?? [];
}

export function validateNode(node: WorkflowNode): Diagnostic[] {
  const spec = getNodeKindSpec(node.kind);
  return spec === null ? [] : spec.validate(node);
}

function checkCustomPath(node: WorkflowNode, diagnostics: Diagnostic[]): void {
  const path = node.params.path;
  if (typeof path !== "string" || path.trim() === "") {
    return;
  }
  try {
    parsePath(path);
  } catch {
    diagnostics.push(paramError(node, "path", "路径语法错误"));
  }
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

function isFiniteNumber(value: unknown): boolean {
  return typeof value === "number" && Number.isFinite(value);
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
