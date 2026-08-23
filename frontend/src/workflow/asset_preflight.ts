import type { Diagnostic, WorkflowDefinition } from "./types";

/**
 * 节点校验的资产预检（决策 2.40）：工作流加载/切换时对图中全部资产引用
 * 做一次批量后端核对；编辑时不做逐次校验（选择器入口已保证选取时存在）。
 */

export type AssetListKind = "characters" | "weapons" | "artifact-sets";

/** 携带资产引用的节点类型与对应资产列表类型。 */
const ASSET_NODE_KINDS: Record<string, AssetListKind> = {
  character: "characters",
  weapon: "weapons",
  artifact: "artifact-sets",
};

export interface AssetReference {
  nodeId: string;
  assetKey: string;
  assetType: AssetListKind;
  sourceId: string | null;
  /** 诊断定位路径：角色/武器为 "asset"，圣遗物为 "sets[i].asset_key"。 */
  path: string;
}

/** 收集图中全部资产引用；asset 为空或格式无效的节点交给编译诊断处理。 */
export function collectAssetReferences(definition: WorkflowDefinition): AssetReference[] {
  const references: AssetReference[] = [];
  for (const node of definition.nodes) {
    const assetType = ASSET_NODE_KINDS[node.kind];
    if (assetType === undefined) {
      continue;
    }
    if (node.kind === "artifact") {
      const sets = Array.isArray(node.params.sets) ? node.params.sets : [];
      sets.forEach((raw, index) => {
        const entry = raw as Record<string, unknown> | null;
        if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
          return;
        }
        const assetKey = typeof entry.asset_key === "string" ? entry.asset_key : null;
        if (assetKey === null || assetKey === "") {
          return;
        }
        references.push({
          nodeId: node.id,
          assetKey,
          assetType,
          sourceId: sourceIdOf(assetKey),
          path: `sets[${index}].asset_key`,
        });
      });
      continue;
    }
    const assetKey = typeof node.params.asset === "string" ? node.params.asset : null;
    if (assetKey === null || assetKey === "") {
      continue;
    }
    references.push({
      nodeId: node.id,
      assetKey,
      assetType,
      sourceId: sourceIdOf(assetKey),
      path: "asset",
    });
  }
  return references;
}

/**
 * 逐个核对资产引用是否存在：按 source_id 搜索并精确匹配 asset_key。
 * 请求失败按“无法判定”跳过——运行期的区域校验仍是权威闸门（决策 2.40）。
 */
export async function preflightAssetReferences(
  references: AssetReference[],
  search: (
    assetType: AssetListKind,
    sourceId: string,
  ) => Promise<{ items?: Array<{ asset_key: string }> }>,
): Promise<string[]> {
  const missing: string[] = [];
  const checked = new Set<string>();
  for (const reference of references) {
    if (reference.sourceId === null || checked.has(reference.assetKey)) {
      continue;
    }
    checked.add(reference.assetKey);
    try {
      const result = await search(reference.assetType, reference.sourceId);
      if (!(result.items ?? []).some((item) => item.asset_key === reference.assetKey)) {
        missing.push(reference.assetKey);
      }
    } catch {
      // 无法判定资产是否存在，跳过；不因网络问题产生误报。
    }
  }
  return missing;
}

/** 失效资产引用 → 节点级诊断（severity error，阻断运行并进入问题面板）。 */
export function assetMissingDiagnostics(
  definition: WorkflowDefinition,
  missingAssetKeys: string[],
): Diagnostic[] {
  const missing = new Set(missingAssetKeys);
  return collectAssetReferences(definition)
    .filter((reference) => missing.has(reference.assetKey))
    .map((reference) => ({
      severity: "error" as const,
      code: "ASSET_NOT_FOUND",
      message: `资产不存在：${reference.assetKey}`,
      node_id: reference.nodeId,
      edge_id: null,
      region_id: null,
      path: reference.path,
    }));
}

function sourceIdOf(assetKey: string): string | null {
  const index = assetKey.indexOf(":");
  if (index === -1 || index === assetKey.length - 1) {
    return null;
  }
  return assetKey.slice(index + 1);
}
