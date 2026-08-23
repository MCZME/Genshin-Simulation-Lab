import { describe, expect, it, vi } from "vitest";
import type { WorkflowDefinition, WorkflowNode } from "./types";
import {
  assetMissingDiagnostics,
  collectAssetReferences,
  preflightAssetReferences,
} from "./asset_preflight";

function makeNode(
  id: string,
  kind: string,
  params: Record<string, unknown> = {},
): WorkflowNode {
  return {
    id,
    kind,
    region_id: null,
    position: { x: 0, y: 0 },
    params,
  };
}

function makeDefinition(nodes: WorkflowNode[]): WorkflowDefinition {
  return {
    schema_version: 1,
    meta: { name: "测试工作流" },
    regions: [],
    nodes,
    edges: [],
    layout: {},
  };
}

describe("collectAssetReferences", () => {
  it("收集角色、武器、圣遗物引用并跳过无效与无关节点", () => {
    const definition = makeDefinition([
      makeNode("c", "character", { asset: "character:amber" }),
      makeNode("w", "weapon", { asset: "weapon:sword" }),
      makeNode("a", "artifact", {
        sets: [{ asset_key: "artifact-set:glad", pieces: 4 }],
      }),
      makeNode("sim", "simulation"),
      makeNode("empty", "character", { asset: "" }),
    ]);
    expect(collectAssetReferences(definition)).toEqual([
      {
        nodeId: "c",
        assetKey: "character:amber",
        assetType: "characters",
        sourceId: "amber",
        path: "asset",
      },
      {
        nodeId: "w",
        assetKey: "weapon:sword",
        assetType: "weapons",
        sourceId: "sword",
        path: "asset",
      },
      {
        nodeId: "a",
        assetKey: "artifact-set:glad",
        assetType: "artifact-sets",
        sourceId: "glad",
        path: "sets[0].asset_key",
      },
    ]);
  });

  it("圣遗物节点按套装条目收集多个引用并跳过空行", () => {
    const definition = makeDefinition([
      makeNode("a", "artifact", {
        sets: [
          { asset_key: "artifact-set:glad", pieces: 4 },
          { asset_key: "artifact-set:shime", pieces: 2 },
          { asset_key: "", pieces: 2 },
        ],
      }),
    ]);
    expect(collectAssetReferences(definition)).toEqual([
      {
        nodeId: "a",
        assetKey: "artifact-set:glad",
        assetType: "artifact-sets",
        sourceId: "glad",
        path: "sets[0].asset_key",
      },
      {
        nodeId: "a",
        assetKey: "artifact-set:shime",
        assetType: "artifact-sets",
        sourceId: "shime",
        path: "sets[1].asset_key",
      },
    ]);
  });
});

describe("preflightAssetReferences", () => {
  it("按 source_id 搜索结果精确匹配 asset_key，缺失资产进入结果", async () => {
    const search = vi.fn(async () => ({
      items: [{ asset_key: "character:amber" }],
    }));
    const missing = await preflightAssetReferences(
      [
        {
          nodeId: "c",
          assetKey: "character:amber",
          assetType: "characters",
          sourceId: "amber",
          path: "asset",
        },
        {
          nodeId: "d",
          assetKey: "character:kaeya",
          assetType: "characters",
          sourceId: "kaeya",
          path: "asset",
        },
      ],
      search,
    );
    expect(missing).toEqual(["character:kaeya"]);
  });

  it("相同 asset_key 去重，请求失败按无法判定跳过", async () => {
    const search = vi
      .fn()
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({ items: undefined });
    const missing = await preflightAssetReferences(
      [
        {
          nodeId: "a",
          assetKey: "character:amber",
          assetType: "characters",
          sourceId: "amber",
          path: "asset",
        },
        {
          nodeId: "b",
          assetKey: "character:amber",
          assetType: "characters",
          sourceId: "amber",
          path: "asset",
        },
        {
          nodeId: "w",
          assetKey: "weapon:sword",
          assetType: "weapons",
          sourceId: "sword",
          path: "asset",
        },
      ],
      search,
    );
    expect(search).toHaveBeenCalledTimes(2);
    expect(missing).toEqual(["weapon:sword"]);
  });
});

describe("assetMissingDiagnostics", () => {
  it("失效引用生成节点级 ASSET_NOT_FOUND 诊断", () => {
    const definition = makeDefinition([
      makeNode("c", "character", { asset: "character:amber" }),
      makeNode("a", "artifact", {
        sets: [{ asset_key: "artifact-set:glad", pieces: 4 }],
      }),
    ]);
    expect(
      assetMissingDiagnostics(definition, ["character:amber", "artifact-set:glad"]),
    ).toEqual([
      {
        severity: "error",
        code: "ASSET_NOT_FOUND",
        message: "资产不存在：character:amber",
        node_id: "c",
        edge_id: null,
        region_id: null,
        path: "asset",
      },
      {
        severity: "error",
        code: "ASSET_NOT_FOUND",
        message: "资产不存在：artifact-set:glad",
        node_id: "a",
        edge_id: null,
        region_id: null,
        path: "sets[0].asset_key",
      },
    ]);
  });
});
