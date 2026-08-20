import type { WorkflowEdge, WorkflowNode } from "./types";

/**
 * 从尾节点沿输入端口反向收集线性节点链。
 * MVP 中链上配置节点每个输入端口只允许一条入线（连接数约束见 registry），
 * 因此链是线性的；多条边界汇入由调用方按连线顺序分别从各自尾节点收集。
 */
export function collectChain(
  tailId: string,
  nodeById: Map<string, WorkflowNode>,
  incomingByTarget: Map<string, WorkflowEdge[]>,
): WorkflowNode[] {
  const chain: WorkflowNode[] = [];
  const seen = new Set<string>();
  let current = nodeById.get(tailId);
  while (current !== undefined && !seen.has(current.id)) {
    seen.add(current.id);
    chain.unshift(current);
    const incoming = (incomingByTarget.get(current.id) ?? []).filter(
      (edge) => edge.target_port_id === "in",
    );
    if (incoming.length === 0) {
      break;
    }
    current = nodeById.get(incoming[0].source_node_id);
  }
  return chain;
}
