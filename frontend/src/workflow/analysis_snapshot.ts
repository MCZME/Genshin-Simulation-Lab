/** 分析区域自动重算快照：查询计划 + 区域节点/连线 + 输入就绪状态 → 稳定指纹。 */

import { buildAnalysisPlanRequest } from "./analysis_runner";
import { analysisInputStatus } from "./runner";
import { hashValue } from "./fingerprint";
import type { WorkflowDefinition } from "./types";

/**
 * 分析区域可重算快照指纹：
 * - 查询计划请求（会话组 + 表节点 + 输出）覆盖取数/算子/边界数据源变化；
 * - 区域内全部节点参数覆盖视图与展示配置变化（v1 统一触发重算）；
 * - 区域内/边界连线顺序覆盖多源合并与算子输入顺序；
 * - 输入就绪状态覆盖配置区域参数变化（期望指纹变化 → 会话过期提示）。
 */
export function regionAnalysisSnapshot(
  definition: WorkflowDefinition,
  regionId: string,
): string {
  const regionNodeIds = new Set(
    definition.nodes
      .filter((node) => node.region_id === regionId)
      .map((node) => node.id),
  );
  const request = buildAnalysisPlanRequest(definition, regionId);
  const regionNodes = definition.nodes
    .filter((node) => node.region_id === regionId)
    .map((node) => ({ id: node.id, kind: node.kind, params: node.params }))
    .sort((left, right) => left.id.localeCompare(right.id));
  const regionEdges = definition.edges
    .filter((edge) => {
      const sourceInRegion =
        regionNodeIds.has(edge.source_node_id) || edge.source_node_id === regionId;
      const targetInRegion =
        regionNodeIds.has(edge.target_node_id) || edge.target_node_id === regionId;
      return sourceInRegion || targetInRegion;
    })
    .map((edge) => [
      edge.source_node_id,
      edge.source_port_id,
      edge.target_node_id,
      edge.target_port_id,
    ]);
  return hashValue({
    request,
    regionNodes,
    regionEdges,
    input: analysisInputStatus(definition, regionId),
  });
}
