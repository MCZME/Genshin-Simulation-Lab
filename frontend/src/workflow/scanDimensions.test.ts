import { describe, expect, it } from "vitest";

import {
  SCAN_DIMENSIONS,
  defaultPathParamValues,
  dimensionPresentation,
  getScanDimension,
  resolveScanPath,
  scanDimensionOptions,
  toDisplayValue,
  toStoredValue,
  validatePathParamValues,
} from "./scanDimensions";
import { ARTIFACT_STAT_KEYS, RESISTANCE_ELEMENT_KEYS, TALENT_KEYS } from "./vocabularies";
import { singleFragment } from "./registry";
import type { WorkflowNode } from "./types";

function nodeOf(kind: string, params: Record<string, unknown>): WorkflowNode {
  return { id: "node-1", kind, region_id: null, position: { x: 0, y: 0 }, params };
}

describe("扫描维度注册表", () => {
  it("dimension_key 唯一", () => {
    const keys = SCAN_DIMENSIONS.map((spec) => spec.dimension_key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("路径模板与现有片段默认路径一致", () => {
    // 维度路径必须与 registry 中 character/weapon/artifact/target 片段的默认路径同构。
    expect(
      resolveScanPath(getScanDimension("character.asset_key")!, { slot: 1 }),
    ).toBe("team[0].character.asset_key");
    expect(
      resolveScanPath(getScanDimension("character.level")!, { slot: 1 }),
    ).toBe("team[0].character.level");
    expect(
      resolveScanPath(getScanDimension("weapon.refinement")!, { slot: 3 }),
    ).toBe("team[2].weapon.refinement");
    expect(
      resolveScanPath(getScanDimension("artifact.stats")!, {
        slot: 1,
        choice: "crit_rate",
      }),
    ).toBe("team[0].artifacts.stats.crit_rate");
    expect(
      resolveScanPath(getScanDimension("target.resistance")!, {
        target_index: 2,
        choice: "pyro",
      }),
    ).toBe("scene.targets[2].resistance.pyro");
  });

  it("resolveScanPath 对缺失参数回退默认值", () => {
    expect(resolveScanPath(getScanDimension("character.talents")!, {})).toBe(
      "team[0].character.talents.normal_attack",
    );
    expect(resolveScanPath(getScanDimension("target.level")!, {})).toBe(
      "scene.targets[0].level",
    );
  });

  it("词汇表选项覆盖全部词条、元素与天赋键", () => {
    const stats = getScanDimension("artifact.stats")!;
    const choiceParam = stats.pathParams.find((param) => param.param === "choice")!;
    expect(choiceParam.options.map((option) => option.value)).toEqual([
      ...ARTIFACT_STAT_KEYS,
    ]);

    const resistance = getScanDimension("target.resistance")!;
    const elementParam = resistance.pathParams.find(
      (param) => param.param === "choice",
    )!;
    expect(elementParam.options.map((option) => option.value)).toEqual([
      ...RESISTANCE_ELEMENT_KEYS,
    ]);

    const talents = getScanDimension("character.talents")!;
    const talentParam = talents.pathParams.find((param) => param.param === "choice")!;
    expect(talentParam.options.map((option) => option.value)).toEqual([
      ...TALENT_KEYS,
    ]);
  });

  it("scanDimensionOptions 按节点类型过滤资产维度", () => {
    const enumKeys = scanDimensionOptions("enum").map((option) => option.value);
    const rangeKeys = scanDimensionOptions("range").map((option) => option.value);
    expect(enumKeys).toContain("character.asset_key");
    expect(rangeKeys).not.toContain("character.asset_key");
    expect(rangeKeys).not.toContain("weapon.asset_key");
    expect(rangeKeys).toContain("character.level");
  });

  it("defaultPathParamValues 提供槽位、目标索引与首选项", () => {
    expect(defaultPathParamValues(getScanDimension("character.level")!)).toEqual({
      slot: 1,
    });
    expect(
      defaultPathParamValues(getScanDimension("target.resistance")!),
    ).toEqual({ target_index: 0, choice: "physical" });
  });

  it("dimensionPresentation 按词条键区分原值与百分比呈现", () => {
    const stats = getScanDimension("artifact.stats")!;
    expect(dimensionPresentation(stats, { choice: "flat_atk" })).toBe("raw");
    expect(dimensionPresentation(stats, { choice: "crit_rate" })).toBe("percent");
    expect(
      dimensionPresentation(getScanDimension("target.resistance")!, {
        choice: "pyro",
      }),
    ).toBe("percent");
    expect(
      dimensionPresentation(getScanDimension("character.level")!, {}),
    ).toBe("raw");
  });

  it("validatePathParamValues 校验槽位、目标索引与词汇表取值", () => {
    const level = getScanDimension("character.level")!;
    expect(validatePathParamValues(level, { slot: 1 })).toBeNull();
    expect(validatePathParamValues(level, { slot: 0 })).toContain("槽位");
    expect(validatePathParamValues(level, { slot: 5 })).toContain("槽位");
    expect(validatePathParamValues(level, { slot: 1.5 })).toContain("槽位");

    const targetLevel = getScanDimension("target.level")!;
    expect(validatePathParamValues(targetLevel, { target_index: 0 })).toBeNull();
    expect(validatePathParamValues(targetLevel, { target_index: -1 })).toContain(
      "目标索引",
    );

    const stats = getScanDimension("artifact.stats")!;
    expect(
      validatePathParamValues(stats, { slot: 1, choice: "crit_rate" }),
    ).toBeNull();
    expect(
      validatePathParamValues(stats, { slot: 1, choice: "unknown_stat" }),
    ).toContain("不在支持范围内");
  });

  it("百分比呈现的显示与存储换算", () => {
    expect(toDisplayValue("percent", 0.4)).toBe(40);
    expect(toDisplayValue("percent", 0.125)).toBe(12.5);
    expect(toStoredValue("percent", 40)).toBe(0.4);
    expect(toStoredValue("percent", 12.5)).toBe(0.125);
    expect(toDisplayValue("raw", 42)).toBe(42);
    expect(toStoredValue("raw", 42)).toBe(42);
  });

  it("维度路径以对应配置节点片段的默认路径为前缀", () => {
    // 联动锁定：registry 片段默认路径变更时此测试必须同步失败，
    // 防止维度路径模板与片段构造漂移。
    const cases: Array<{
      dimension: string;
      kind: string;
      params: Record<string, unknown>;
      pathParams: Record<string, unknown>;
    }> = [
      {
        dimension: "character.constellation",
        kind: "character",
        params: { slot: 2, asset: "character:barbara" },
        pathParams: { slot: 2 },
      },
      {
        dimension: "weapon.level",
        kind: "weapon",
        params: { slot: 4, asset: "weapon:11512" },
        pathParams: { slot: 4 },
      },
      {
        dimension: "artifact.stats",
        kind: "artifact",
        params: { slot: 1, sets: [{ asset_key: "artifact-set:x", pieces: 4 }] },
        pathParams: { slot: 1, choice: "crit_rate" },
      },
      {
        dimension: "target.resistance",
        kind: "target",
        params: { index: 3 },
        pathParams: { target_index: 3, choice: "pyro" },
      },
    ];
    for (const { dimension, kind, params, pathParams } of cases) {
      const spec = getScanDimension(dimension)!;
      const node = nodeOf(kind, params);
      const fragment = singleFragment(node, {
        schema_version: 1,
        meta: { name: "" },
        regions: [],
        nodes: [node],
        edges: [],
        layout: {},
      });
      expect(fragment).not.toBeNull();
      expect(resolveScanPath(spec, pathParams).startsWith(fragment!.path)).toBe(
        true,
      );
    }
  });
});
