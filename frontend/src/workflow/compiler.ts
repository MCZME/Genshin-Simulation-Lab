import type {
  CompiledMember,
  CompileResult,
  Diagnostic,
  DiagnosticSeverity,
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowNode,
} from "./types";
import { MAX_BATCH_MEMBERS, REGION_BOUNDARY_OUT_PORT } from "./types";
import {
  getNodeKindSpec,
  groupFragments,
  isProjectionPort,
  projectionItemId,
  singleFragment,
} from "./registry";
import { collectUpstreamNodes, orderedIncomingEdges } from "./chain";
import type { UpstreamNode } from "./chain";
import { setPath } from "./path";

interface FragmentVariant {
  item_id: string;
  path: string;
  value: unknown;
}

/**
 * 数据流中的一份“文档”：记录已应用的片段、变体来源与路径写入者。
 * 成员投影端口按 variants 过滤，覆盖警告按 writers 判定。
 */
interface FlowDoc {
  input: Record<string, unknown>;
  itemIds: string[];
  variants: Map<string, string>;
  writers: Map<string, { nodeId: string; edgeId: string }>;
}

export interface ExpandedRegion {
  ok: boolean;
  members: CompiledMember[];
  diagnostics: Diagnostic[];
  /** 方法应用轨迹（决策 2.34）：按「根 → 边界」拓扑序记录每个参与节点的应用信息。 */
  methods: MethodTrace[];
}

export interface MethodTrace {
  nodeId: string;
  /** 该节点写入的目标路径；root 与不产出片段的节点为空。 */
  paths: string[];
  /** 产出变体数：单值节点为 1，枚举/区间为成员数，不产出为 0。 */
  variants: number;
  /** 该节点的写入是否被后继节点覆盖（对应 PATH_OVERRIDE 诊断）。 */
  overridden: boolean;
}

export function createSimulationInputSkeleton(): Record<string, unknown> {
  return {
    schema_version: 2,
    kind: "simulation_input",
    meta: { name: "", description: "" },
    team: [],
    scene: {},
    input_trace: [],
    rules: { enabled: [] },
    run_options: { max_frames: 18000 },
  };
}

/** 按“节点=方法”语义展开配置区域：输入先合并，节点再应用自身片段，输出按边分发。 */
export function expandConfigurationRegion(
  definition: WorkflowDefinition,
  regionId: string,
): ExpandedRegion {
  const diagnostics: Diagnostic[] = [];
  const region = definition.regions.find((item) => item.id === regionId);
  if (region === undefined) {
    return fail([compileError("REGION_NOT_FOUND", `区域不存在：${regionId}`)]);
  }
  if (region.kind !== "configuration") {
    return fail([compileError("REGION_KIND_UNSUPPORTED", "只有配置区域可以编译成员")]);
  }

  const boundaryEdges = definition.edges.filter(
    (edge) => edge.target_node_id === regionId && edge.target_port_id === REGION_BOUNDARY_OUT_PORT,
  );
  if (boundaryEdges.length === 0) {
    return fail([compileError("EMPTY_REGION", "配置区域没有数据汇入，阻止运行")]);
  }

  for (const edge of boundaryEdges) {
    const tail = definition.nodes.find((node) => node.id === edge.source_node_id);
    if (tail === undefined || getNodeKindSpec(tail.kind) === null) {
      diagnostics.push(
        compileError("SOURCE_NODE_INVALID", `边界输入引用了无效节点：${edge.source_node_id}`),
      );
    }
  }
  if (diagnostics.some((item) => item.severity === "error")) {
    return fail(diagnostics);
  }

  const nodeById = new Map(definition.nodes.map((node) => [node.id, node]));
  const incomingByTarget = new Map<string, WorkflowEdge[]>();
  const outgoingBySource = new Map<string, WorkflowEdge[]>();
  for (const edge of definition.edges) {
    const incoming = incomingByTarget.get(edge.target_node_id) ?? [];
    incoming.push(edge);
    incomingByTarget.set(edge.target_node_id, incoming);
    const outgoing = outgoingBySource.get(edge.source_node_id) ?? [];
    outgoing.push(edge);
    outgoingBySource.set(edge.source_node_id, outgoing);
  }

  const upstream = collectUpstreamNodes(
    boundaryEdges.map((edge) => ({ nodeId: edge.source_node_id, edgeId: edge.id })),
    nodeById,
    incomingByTarget,
  );
  const upstreamIds = new Set(upstream.map((item) => item.node.id));
  const base = [baseDoc()];
  const nodeDocs = new Map<string, FlowDoc[]>();
  const edgeDocs = new Map<string, FlowDoc[]>();
  const boundarySets: FlowDoc[][] = [];
  const warningSeen = new Set<string>();

  for (const { node, edgeId } of upstream) {
    const inputSets = orderedIncomingEdges(node, incomingByTarget, nodeById)
      .map((edge) => edgeDocs.get(edge.id) ?? [])
      .filter((set) => set.length > 0);
    const inputDocs =
      inputSets.length === 0 ? base : mergeDocSets(inputSets, diagnostics, warningSeen);
    const variants = nodeVariants(node, definition);

    let outputDocs: FlowDoc[];
    if (variants.length === 0) {
      outputDocs = inputDocs;
    } else {
      const applied: FlowDoc[] = [];
      for (const doc of inputDocs) {
        for (const variant of variants) {
          applied.push(applyVariant(doc, node.id, edgeId, variant, diagnostics, warningSeen));
        }
      }
      outputDocs = dedupeDocs(applied);
    }
    nodeDocs.set(node.id, outputDocs);

    for (const edge of outgoingBySource.get(node.id) ?? []) {
      if (edge.target_node_id === region.id) {
        boundarySets.push(outputDocs);
      } else if (upstreamIds.has(edge.target_node_id)) {
        if (isProjectionPort(node, edge.source_port_id)) {
          const itemId = projectionItemId(edge.source_port_id);
          edgeDocs.set(
            edge.id,
            outputDocs.filter((doc) => doc.variants.get(node.id) === itemId),
          );
        } else {
          edgeDocs.set(edge.id, outputDocs);
        }
      }
    }
  }

  const finalDocs = mergeDocSets(
    boundarySets.filter((set) => set.length > 0),
    diagnostics,
    warningSeen,
  );
  if (finalDocs.length > MAX_BATCH_MEMBERS) {
    diagnostics.push(
      compileError(
        "MEMBER_LIMIT_EXCEEDED",
        `展开成员数 ${finalDocs.length} 超过上限 ${MAX_BATCH_MEMBERS}`,
      ),
    );
    return fail(diagnostics);
  }

  const members = finalDocs.map((doc) => {
    ensureTeamSlots(doc.input);
    return {
      item_id: doc.itemIds.length > 0 ? doc.itemIds.join("+") : "root",
      input: doc.input,
    };
  });
  return {
    ok: true,
    members,
    diagnostics,
    methods: methodTraces(upstream, definition, diagnostics),
  };
}

function methodTraces(
  upstream: UpstreamNode[],
  definition: WorkflowDefinition,
  diagnostics: Diagnostic[],
): MethodTrace[] {
  const overriddenNodeIds = new Set(
    diagnostics
      .filter((item) => item.code === "PATH_OVERRIDE" && item.node_id !== null)
      .map((item) => item.node_id as string),
  );
  return upstream.map(({ node }) => {
    const variants = nodeVariants(node, definition);
    const paths = [...new Set(variants.map((variant) => variant.path))];
    return {
      nodeId: node.id,
      paths,
      variants: variants.length,
      overridden: overriddenNodeIds.has(node.id),
    };
  });
}

export function compileConfigurationRegion(
  definition: WorkflowDefinition,
  regionId: string,
): CompileResult {
  const expanded = expandConfigurationRegion(definition, regionId);
  return {
    ok: expanded.ok,
    region_id: regionId,
    members: expanded.members,
    diagnostics: expanded.diagnostics,
  };
}

function baseDoc(): FlowDoc {
  return {
    input: createSimulationInputSkeleton(),
    itemIds: [],
    variants: new Map(),
    writers: new Map(),
  };
}

function nodeVariants(node: WorkflowNode, definition: WorkflowDefinition): FragmentVariant[] {
  if (node.kind === "enum" || node.kind === "range") {
    return groupFragments(node);
  }
  const single = singleFragment(node, definition);
  return single === null ? [] : [single];
}

function applyVariant(
  doc: FlowDoc,
  nodeId: string,
  edgeId: string,
  variant: FragmentVariant,
  diagnostics: Diagnostic[],
  warningSeen: Set<string>,
): FlowDoc {
  const previous = doc.writers.get(variant.path);
  const overriddenNodes = new Set<string>();
  if (previous !== undefined && previous.nodeId !== nodeId) {
    overriddenNodes.add(previous.nodeId);
    emitOverride(diagnostics, warningSeen, variant.path, previous, { nodeId, edgeId });
  }
  const input = structuredClone(doc.input);
  setPath(input, variant.path, variant.value);
  const writers = new Map(doc.writers);
  writers.set(variant.path, { nodeId, edgeId });
  const itemIds = dropItemIds(doc, overriddenNodes);
  itemIds.push(variant.item_id);
  return {
    input,
    itemIds,
    variants: new Map(doc.variants).set(nodeId, variant.item_id),
    writers,
  };
}

function mergeDocSets(
  sets: FlowDoc[][],
  diagnostics: Diagnostic[],
  warningSeen: Set<string>,
): FlowDoc[] {
  let result = sets[0] ?? [];
  for (let index = 1; index < sets.length; index += 1) {
    result = mergeTwo(result, sets[index], diagnostics, warningSeen);
  }
  return result;
}

/**
 * 两路输入合并：不同写入者的同路径片段后生效者覆盖（并警告）；
 * 同一节点的不同变体视为互斥备选，保持为独立文档而不是互相覆盖。
 */
function mergeTwo(
  left: FlowDoc[],
  right: FlowDoc[],
  diagnostics: Diagnostic[],
  warningSeen: Set<string>,
): FlowDoc[] {
  const merged: FlowDoc[] = [];
  for (const leftDoc of left) {
    for (const rightDoc of right) {
      if (hasAlternativeConflict(leftDoc, rightDoc)) {
        merged.push(leftDoc, rightDoc);
        continue;
      }
      const writers = new Map(leftDoc.writers);
      const overriddenNodes = new Set<string>();
      for (const [path, writer] of rightDoc.writers) {
        const previous = writers.get(path);
        if (previous !== undefined && previous.nodeId !== writer.nodeId) {
          overriddenNodes.add(previous.nodeId);
          emitOverride(diagnostics, warningSeen, path, previous, writer);
        }
        writers.set(path, writer);
      }
      const sharedNodeIds = [...leftDoc.variants.keys()].filter((nodeId) =>
        rightDoc.variants.has(nodeId),
      );
      const rightItemIds = rightDoc.itemIds.filter((itemId) =>
        sharedNodeIds.every((nodeId) => rightDoc.variants.get(nodeId) !== itemId),
      );
      merged.push({
        input: deepMerge(leftDoc.input, rightDoc.input),
        itemIds: [...dropItemIds(leftDoc, overriddenNodes), ...rightItemIds],
        variants: new Map([...leftDoc.variants, ...rightDoc.variants]),
        writers,
      });
    }
  }
  return dedupeDocs(merged);
}

function dropItemIds(doc: FlowDoc, nodeIds: Set<string>): string[] {
  if (nodeIds.size === 0) {
    return [...doc.itemIds];
  }
  const removed = new Set<string>();
  for (const nodeId of nodeIds) {
    const itemId = doc.variants.get(nodeId);
    if (itemId !== undefined) {
      removed.add(itemId);
    }
  }
  return doc.itemIds.filter((itemId) => !removed.has(itemId));
}

function hasAlternativeConflict(left: FlowDoc, right: FlowDoc): boolean {
  for (const [path, writer] of right.writers) {
    const leftWriter = left.writers.get(path);
    if (leftWriter === undefined || leftWriter.nodeId !== writer.nodeId) {
      continue;
    }
    if (left.variants.get(writer.nodeId) !== right.variants.get(writer.nodeId)) {
      return true;
    }
  }
  return false;
}

function emitOverride(
  diagnostics: Diagnostic[],
  warningSeen: Set<string>,
  path: string,
  overridden: { nodeId: string; edgeId: string },
  overriding: { nodeId: string; edgeId: string },
): void {
  const key = `${path}|${overridden.nodeId}|${overriding.nodeId}`;
  if (warningSeen.has(key)) {
    return;
  }
  warningSeen.add(key);
  diagnostics.push(
    compileWarning(
      "PATH_OVERRIDE",
      `同路径片段被后写入者覆盖：${path}`,
      overridden.nodeId,
      overridden.edgeId,
      path,
    ),
  );
}

function deepMerge(
  base: Record<string, unknown>,
  override: Record<string, unknown>,
): Record<string, unknown> {
  const result = structuredClone(base);
  mergeInto(result, override);
  return result;
}

function mergeInto(
  target: Record<string, unknown>,
  source: Record<string, unknown>,
): void {
  for (const [key, value] of Object.entries(source)) {
    if (isPlainObject(value) && isPlainObject(target[key])) {
      mergeInto(target[key] as Record<string, unknown>, value);
    } else if (Array.isArray(value) && Array.isArray(target[key])) {
      mergeArrays(target[key] as unknown[], value);
    } else {
      target[key] = structuredClone(value);
    }
  }
}

function mergeArrays(target: unknown[], source: unknown[]): void {
  const length = Math.max(target.length, source.length);
  for (let index = 0; index < length; index += 1) {
    const targetValue = target[index];
    const sourceValue = source[index];
    if (index >= target.length) {
      target.push(structuredClone(sourceValue));
    } else if (sourceValue === undefined) {
      // 源数组的未写入槽位保留目标槽位（跳号索引写入产生的空洞）。
      continue;
    } else if (isPlainObject(targetValue) && isPlainObject(sourceValue)) {
      mergeInto(targetValue as Record<string, unknown>, sourceValue as Record<string, unknown>);
    } else {
      target[index] = structuredClone(sourceValue);
    }
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function dedupeDocs(docs: FlowDoc[]): FlowDoc[] {
  const seen = new Set<string>();
  const result: FlowDoc[] = [];
  for (const doc of docs) {
    const key = JSON.stringify([doc.itemIds, doc.input]);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(doc);
  }
  return result;
}

/**
 * team 是 1 起始槽位列表；片段写入 team[i] 后，
 * 若条目缺少 slot 字段则按数组下标 + 1 补齐，避免后端校验拒绝。
 */
function ensureTeamSlots(input: Record<string, unknown>): void {
  const team = input.team;
  if (!Array.isArray(team)) {
    return;
  }
  team.forEach((entry, index) => {
    if (entry !== null && typeof entry === "object") {
      const record = entry as Record<string, unknown>;
      if (record.slot === undefined) {
        record.slot = index + 1;
      }
    }
  });
}

function compileError(code: string, message: string): Diagnostic {
  return compileDiagnostic("error", code, message);
}

function compileWarning(
  code: string,
  message: string,
  nodeId: string | null,
  edgeId: string | null,
  path: string | null,
): Diagnostic {
  return compileDiagnostic("warning", code, message, nodeId, edgeId, path);
}

function compileDiagnostic(
  severity: DiagnosticSeverity,
  code: string,
  message: string,
  nodeId: string | null = null,
  edgeId: string | null = null,
  path: string | null = null,
): Diagnostic {
  return { severity, code, message, node_id: nodeId, edge_id: edgeId, region_id: null, path };
}

function fail(diagnostics: Diagnostic[]): ExpandedRegion {
  return { ok: false, members: [], diagnostics, methods: [] };
}
