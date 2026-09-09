/**
 * 变体扫描维度注册表：enum/range 节点的"常用维度"词汇表。
 * 每个维度声明目标路径模板、路径参数、值类型、约束与呈现方式；
 * 编译产物仍是 path+value 片段，与后端契约解耦。
 */
import type { EnumValueType } from "./types";
import { ELEMENT_LABELS } from "../theme/elements";
import {
  ARTIFACT_RAW_STAT_KEYS,
  ARTIFACT_STAT_KEYS,
  ARTIFACT_STAT_LABELS,
  RESISTANCE_ELEMENT_KEYS,
  TALENT_KEYS,
  TALENT_KEY_LABELS,
} from "./vocabularies";

export type ScanNodeKind = "enum" | "range";

/**
 * 路径参数规格：
 * - slot：1 起队伍槽位（1-4），模板 {slot} 解析为 0 起下标；
 * - target_index：0 起目标索引，模板 {target_index} 原样替换；
 * - choice：词汇表选择（天赋键/词条键/元素键），模板 {choice} 原样替换。
 */
export type ScanPathParamSpec =
  | { param: "slot"; label: string }
  | { param: "target_index"; label: string }
  | { param: "choice"; label: string; options: ReadonlyArray<{ value: string; label: string }> };

export interface ScanConstraintSpec {
  min?: number;
  max?: number;
  integer?: boolean;
  /** range 节点切入该维度时的默认区间；值为契约存储值（percent 维度按小数倍率）。 */
  rangeDefault?: { start: number; end: number; step: number };
}

export type ScanPresentation = "raw" | "percent";

export interface ScanDimensionSpec {
  dimension_key: string;
  displayName: string;
  category: "角色" | "武器" | "圣遗物" | "目标";
  /** 路径模板，占位符见 ScanPathParamSpec。 */
  pathTemplate: string;
  pathParams: ScanPathParamSpec[];
  valueType: EnumValueType;
  assetType?: "characters" | "weapons";
  constraints?: ScanConstraintSpec;
  /** percent：界面按百分比显示、存储小数倍率（与圣遗物/目标抗性编辑器一致）；可按路径参数决定。 */
  presentation: ScanPresentation | ((pathParams: Record<string, unknown>) => ScanPresentation);
  supports: ReadonlyArray<ScanNodeKind>;
}

const TALENT_OPTIONS = TALENT_KEYS.map((key) => ({
  value: key,
  label: TALENT_KEY_LABELS[key] ?? key,
}));

const ARTIFACT_STAT_OPTIONS = ARTIFACT_STAT_KEYS.map((key) => ({
  value: key,
  label: ARTIFACT_STAT_LABELS[key] ?? key,
}));

const RESISTANCE_ELEMENT_OPTIONS = RESISTANCE_ELEMENT_KEYS.map((key) => ({
  value: key,
  label: ELEMENT_LABELS[key] ?? key,
}));

/** 圣遗物词条按词条键决定呈现：固定值词条原值，百分比词条按百分比。 */
function artifactStatPresentation(
  pathParams: Record<string, unknown>,
): ScanPresentation {
  return ARTIFACT_RAW_STAT_KEYS.includes(String(pathParams.choice ?? ""))
    ? "raw"
    : "percent";
}

export const SCAN_DIMENSIONS: ReadonlyArray<ScanDimensionSpec> = [
  {
    dimension_key: "character.asset_key",
    displayName: "角色",
    category: "角色",
    // asset 值类型产出 { asset_key } 对象，路径为 character 对象本身。
    pathTemplate: "team[{slot}].character",
    pathParams: [{ param: "slot", label: "槽位" }],
    valueType: "asset",
    assetType: "characters",
    presentation: "raw",
    supports: ["enum"],
  },
  {
    dimension_key: "character.level",
    displayName: "角色等级",
    category: "角色",
    pathTemplate: "team[{slot}].character.level",
    pathParams: [{ param: "slot", label: "槽位" }],
    valueType: "number",
    constraints: {
      min: 1,
      max: 100,
      integer: true,
      rangeDefault: { start: 1, end: 90, step: 1 },
    },
    presentation: "raw",
    supports: ["enum", "range"],
  },
  {
    dimension_key: "character.constellation",
    displayName: "命座",
    category: "角色",
    pathTemplate: "team[{slot}].character.constellation",
    pathParams: [{ param: "slot", label: "槽位" }],
    valueType: "number",
    constraints: {
      min: 0,
      max: 6,
      integer: true,
      rangeDefault: { start: 0, end: 6, step: 1 },
    },
    presentation: "raw",
    supports: ["enum", "range"],
  },
  {
    dimension_key: "character.talents",
    displayName: "天赋等级",
    category: "角色",
    pathTemplate: "team[{slot}].character.talents.{choice}",
    pathParams: [
      { param: "slot", label: "槽位" },
      { param: "choice", label: "天赋", options: TALENT_OPTIONS },
    ],
    valueType: "number",
    constraints: {
      min: 1,
      max: 10,
      integer: true,
      rangeDefault: { start: 1, end: 10, step: 1 },
    },
    presentation: "raw",
    supports: ["enum", "range"],
  },
  {
    dimension_key: "weapon.asset_key",
    displayName: "武器",
    category: "武器",
    // asset 值类型产出 { asset_key } 对象，路径为 weapon 对象本身。
    pathTemplate: "team[{slot}].weapon",
    pathParams: [{ param: "slot", label: "槽位" }],
    valueType: "asset",
    assetType: "weapons",
    presentation: "raw",
    supports: ["enum"],
  },
  {
    dimension_key: "weapon.level",
    displayName: "武器等级",
    category: "武器",
    pathTemplate: "team[{slot}].weapon.level",
    pathParams: [{ param: "slot", label: "槽位" }],
    valueType: "number",
    constraints: {
      min: 1,
      max: 100,
      integer: true,
      rangeDefault: { start: 1, end: 90, step: 1 },
    },
    presentation: "raw",
    supports: ["enum", "range"],
  },
  {
    dimension_key: "weapon.refinement",
    displayName: "精炼",
    category: "武器",
    pathTemplate: "team[{slot}].weapon.refinement",
    pathParams: [{ param: "slot", label: "槽位" }],
    valueType: "number",
    constraints: {
      min: 1,
      max: 5,
      integer: true,
      rangeDefault: { start: 1, end: 5, step: 1 },
    },
    presentation: "raw",
    supports: ["enum", "range"],
  },
  {
    dimension_key: "artifact.stats",
    displayName: "圣遗物词条",
    category: "圣遗物",
    pathTemplate: "team[{slot}].artifacts.stats.{choice}",
    pathParams: [
      { param: "slot", label: "槽位" },
      { param: "choice", label: "词条", options: ARTIFACT_STAT_OPTIONS },
    ],
    valueType: "number",
    constraints: { min: 0 },
    presentation: artifactStatPresentation,
    supports: ["enum", "range"],
  },
  {
    dimension_key: "target.level",
    displayName: "目标等级",
    category: "目标",
    pathTemplate: "scene.targets[{target_index}].level",
    pathParams: [{ param: "target_index", label: "目标索引" }],
    valueType: "number",
    constraints: {
      min: 1,
      integer: true,
      rangeDefault: { start: 1, end: 90, step: 1 },
    },
    presentation: "raw",
    supports: ["enum", "range"],
  },
  {
    dimension_key: "target.resistance",
    displayName: "目标抗性",
    category: "目标",
    pathTemplate: "scene.targets[{target_index}].resistance.{choice}",
    pathParams: [
      { param: "target_index", label: "目标索引" },
      { param: "choice", label: "元素", options: RESISTANCE_ELEMENT_OPTIONS },
    ],
    valueType: "number",
    constraints: { rangeDefault: { start: 0, end: 0.4, step: 0.1 } },
    presentation: "percent",
    supports: ["enum", "range"],
  },
];

export function getScanDimension(key: string): ScanDimensionSpec | null {
  return SCAN_DIMENSIONS.find((spec) => spec.dimension_key === key) ?? null;
}

/** 指定节点类型可用的维度下拉选项，按注册顺序（类别分组）排列。 */
export function scanDimensionOptions(kind: ScanNodeKind): Array<{
  value: string;
  label: string;
}> {
  return SCAN_DIMENSIONS.filter((spec) => spec.supports.includes(kind)).map(
    (spec) => ({ value: spec.dimension_key, label: spec.displayName }),
  );
}

/** 维度的路径参数默认值：槽位 1、目标索引 0、choice 取词汇表首项。 */
export function defaultPathParamValues(
  spec: ScanDimensionSpec,
): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const param of spec.pathParams) {
    if (param.param === "slot") {
      values.slot = 1;
    } else if (param.param === "target_index") {
      values.target_index = 0;
    } else if (param.options.length > 0) {
      values.choice = param.options[0].value;
    }
  }
  return values;
}

/** 解析维度路径模板为具体输入契约路径。 */
export function resolveScanPath(
  spec: ScanDimensionSpec,
  pathParams: Record<string, unknown>,
): string {
  return spec.pathTemplate.replace(/\{(\w+)\}/g, (_match, name: string) => {
    if (name === "slot") {
      const slot = Number(pathParams.slot ?? 1);
      return String((Number.isFinite(slot) ? slot : 1) - 1);
    }
    if (name === "target_index") {
      const index = Number(pathParams.target_index ?? 0);
      return String(Number.isFinite(index) ? Math.max(0, Math.trunc(index)) : 0);
    }
    if (name === "choice") {
      const choice = String(pathParams.choice ?? "");
      if (choice !== "") {
        return choice;
      }
      const choiceParam = spec.pathParams.find(
        (param) => param.param === "choice",
      );
      return choiceParam !== undefined && choiceParam.options.length > 0
        ? choiceParam.options[0].value
        : "";
    }
    return name;
  });
}

/** 解析维度在当前路径参数下的值呈现方式。 */
export function dimensionPresentation(
  spec: ScanDimensionSpec,
  pathParams: Record<string, unknown>,
): ScanPresentation {
  return typeof spec.presentation === "function"
    ? spec.presentation(pathParams)
    : spec.presentation;
}

/** 校验路径参数取值；返回错误消息或 null。 */
export function validatePathParamValues(
  spec: ScanDimensionSpec,
  pathParams: Record<string, unknown>,
): string | null {
  for (const param of spec.pathParams) {
    if (param.param === "slot") {
      const slot = pathParams.slot;
      if (
        typeof slot !== "number" ||
        !Number.isInteger(slot) ||
        slot < 1 ||
        slot > 4
      ) {
        return "槽位必须是 1 到 4 之间的整数";
      }
    } else if (param.param === "target_index") {
      const index = pathParams.target_index;
      if (typeof index !== "number" || !Number.isInteger(index) || index < 0) {
        return "目标索引必须是 >= 0 的整数";
      }
    } else {
      const choice = pathParams.choice;
      if (
        typeof choice !== "string" ||
        !param.options.some((option) => option.value === choice)
      ) {
        return `${param.label}取值不在支持范围内`;
      }
    }
  }
  return null;
}

/** 存储值 → 界面显示值：percent 维度按百分比显示。 */
export function toDisplayValue(
  presentation: ScanPresentation,
  stored: number,
): number {
  return presentation === "percent"
    ? Math.round(stored * 10000) / 100
    : stored;
}

/** 界面显示值 → 存储值：percent 维度换算为小数倍率。 */
export function toStoredValue(
  presentation: ScanPresentation,
  display: number,
): number {
  return presentation === "percent" ? display / 100 : display;
}
