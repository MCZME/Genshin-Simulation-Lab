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
 * 数据流中的一份载荷，分两种血缘：
 * - 文档血缘（根节点可达）：input 携带根数据骨架与已应用写入；
 * - 方法血缘（无根数据输入）：input 只含自身链的写入结果，不携带根数据骨架。
 * 成员投影端口按 variants 过滤，覆盖警告与合并重放按 writers 判定。
 */
interface FlowDoc {
  input: Record<string, unknown>;
  itemIds: string[];
  variants: Map<string, string>;
  writers: Map<string, { nodeId: string; edgeId: string; value: unknown }>;
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
    rules: { active: [] },
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
  // 血缘分类按拓扑序传播：从根可达的节点承载文档，其余节点是方法（D-093）。
  const docLineageNodes = new Set<string>();
  const base = [baseDoc()];
  const edgeDocs = new Map<string, FlowDoc[]>();
  const edgeMethods = new Map<string, FlowDoc[]>();
  const boundarySets: FlowDoc[][] = [];
  const boundaryMethodSets: FlowDoc[][] = [];
  const warningSeen = new Set<string>();

  for (const { node, edgeId } of upstream) {
    const docSets: FlowDoc[][] = [];
    const methodSets: FlowDoc[][] = [];
    for (const edge of orderedIncomingEdges(node, incomingByTarget, nodeById)) {
      const sourceIsDoc = docLineageNodes.has(edge.source_node_id);
      const payload = sourceIsDoc ? edgeDocs.get(edge.id) : edgeMethods.get(edge.id);
      if (payload === undefined || payload.length === 0) {
        continue;
      }
      (sourceIsDoc ? docSets : methodSets).push(payload);
    }
    const isDocLineage = node.kind === "root" || docSets.length > 0;
    if (isDocLineage) {
      docLineageNodes.add(node.id);
    }
    const variants = nodeVariants(node, definition);

    let outputDocs: FlowDoc[];
    if (!isDocLineage && docSets.length === 0 && methodSets.length === 0) {
      // 独立方法节点：载荷只含自身写入，不携带文档状态。
      outputDocs = applyNodeVariants(
        [emptyPartialDoc()],
        node.id,
        edgeId,
        variants,
        diagnostics,
        warningSeen,
      );
    } else {
      // 文档载荷在前、方法载荷在后：方法在接触点修改收到的文档（同路径时节点自身片段最后生效）。
      const seed = docSets.length > 0 ? [...docSets, ...methodSets] : methodSets;
      const inputDocs =
        seed.length > 0 ? mergeDocSets(seed, diagnostics, warningSeen) : base;
      outputDocs = applyNodeVariants(
        inputDocs,
        node.id,
        edgeId,
        variants,
        diagnostics,
        warningSeen,
      );
    }

    for (const edge of outgoingBySource.get(node.id) ?? []) {
      if (edge.target_node_id === region.id) {
        if (isDocLineage) {
          boundarySets.push(outputDocs);
        } else {
          boundaryMethodSets.push(outputDocs);
        }
      } else if (upstreamIds.has(edge.target_node_id)) {
        const store = isDocLineage ? edgeDocs : edgeMethods;
        if (isProjectionPort(node, edge.source_port_id)) {
          const itemId = projectionItemId(edge.source_port_id);
          store.set(
            edge.id,
            outputDocs.filter((doc) => doc.variants.get(node.id) === itemId),
          );
        } else {
          store.set(edge.id, outputDocs);
        }
      }
    }
  }

  // 边界汇入：文档集在前、方法载荷在后；边界只收到方法时，方法作用于区域隐式初始文档。
  const effectiveBoundarySets =
    boundarySets.length === 0 && boundaryMethodSets.length > 0 ? [base] : boundarySets;
  const finalDocs = mergeDocSets(
    [...effectiveBoundarySets, ...boundaryMethodSets].filter((set) => set.length > 0),
    diagnostics,
    warningSeen,
  );
  if (finalDocs.length === 0) {
    diagnostics.push(
      compileError("EMPTY_REGION", "配置区域没有产出有效输入文档，阻止运行"),
    );
    return fail(diagnostics);
  }
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

/** 根数据初始形态：根节点出发的文档与「边界只收到方法」时的隐式初始文档都从这里开始。 */
function baseDoc(): FlowDoc {
  return {
    input: createSimulationInputSkeleton(),
    itemIds: [],
    variants: new Map(),
    writers: new Map(),
  };
}

/** 方法载荷的空种子：只承载写入，不携带根数据骨架。 */
function emptyPartialDoc(): FlowDoc {
  return { input: {}, itemIds: [], variants: new Map(), writers: new Map() };
}

function nodeVariants(node: WorkflowNode, definition: WorkflowDefinition): FragmentVariant[] {
  if (node.kind === "enum" || node.kind === "range") {
    return groupFragments(node);
  }
  const single = singleFragment(node, definition);
  return single === null ? [] : [single];
}

/** 节点自身片段按变体应用到每份输入载荷；无片段时原样透传。 */
function applyNodeVariants(
  inputDocs: FlowDoc[],
  nodeId: string,
  edgeId: string,
  variants: FragmentVariant[],
  diagnostics: Diagnostic[],
  warningSeen: Set<string>,
): FlowDoc[] {
  if (variants.length === 0) {
    return inputDocs;
  }
  const applied: FlowDoc[] = [];
  for (const doc of inputDocs) {
    for (const variant of variants) {
      applied.push(applyVariant(doc, nodeId, edgeId, variant, diagnostics, warningSeen));
    }
  }
  return dedupeDocs(applied);
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
  writers.set(variant.path, { nodeId, edgeId, value: variant.value });
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
    const nextSet = sets[index];
    if (nextSet !== undefined) {
      result = mergeTwo(result, nextSet, diagnostics, warningSeen);
    }
  }
  return result;
}

/**
 * 两路载荷合并：右侧有写入者记录的路径按记录整值重放到左侧（后写入者覆盖并警告）；
 * 未被写入的骨架状态不参与跨载荷传播，方法载荷因此不会把空默认值带进文档。
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
      merged.push(mergeWrites(leftDoc, rightDoc, diagnostics, warningSeen));
    }
  }
  return dedupeDocs(merged);
}

/** 把 right 的全部写入重放到 left 上，产出合并文档；两侧输入均不被修改。 */
function mergeWrites(
  left: FlowDoc,
  right: FlowDoc,
  diagnostics: Diagnostic[],
  warningSeen: Set<string>,
): FlowDoc {
  const writers = new Map(left.writers);
  const overriddenNodes = new Set<string>();
  for (const [path, writer] of right.writers) {
    const previous = writers.get(path);
    if (previous !== undefined && previous.nodeId !== writer.nodeId) {
      overriddenNodes.add(previous.nodeId);
      emitOverride(diagnostics, warningSeen, path, previous, writer);
    }
    writers.set(path, writer);
  }
  const input = structuredClone(left.input);
  for (const [path, writer] of right.writers) {
    setPath(input, path, writer.value);
  }
  const sharedNodeIds = [...left.variants.keys()].filter((nodeId) =>
    right.variants.has(nodeId),
  );
  const rightItemIds = right.itemIds.filter((itemId) =>
    sharedNodeIds.every((nodeId) => right.variants.get(nodeId) !== itemId),
  );
  return {
    input,
    itemIds: [...dropItemIds(left, overriddenNodes), ...rightItemIds],
    variants: new Map([...left.variants, ...right.variants]),
    writers,
  };
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
