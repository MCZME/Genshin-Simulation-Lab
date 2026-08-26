import type { CompiledMember, Diagnostic, WorkflowDefinition, WorkflowNode } from "./types";
import { MAX_BATCH_MEMBERS, REGION_BOUNDARY_IN_PORT, REGION_BOUNDARY_OUT_PORT } from "./types";
import type { ValidateInputsResponse } from "../api/client";
import { expandConfigurationRegion } from "./compiler";
import type { MethodTrace } from "./compiler";
import { getNodeKindSpec } from "./registry";
import { hashValue } from "./fingerprint";

export interface BatchMember {
  item_id: string;
  input: Record<string, unknown>;
}

/** 一个模拟节点对应的一个批次计划（决策 2.32）。 */
export interface BatchPlan {
  nodeId: string;
  /** 批次名：取所连第一个区域元信息名称；缺省回退工作流名。 */
  name: string;
  /** 并发度：节点参数 1–16；null 表示「自动」（不传，后端 min(4, CPU)）。 */
  concurrency: number | null;
  sourceRegionIds: string[];
  members: BatchMember[];
}

/** 构建阶段的区域切片：方法轨迹 + 收拢成员数（决策 2.34）。 */
export interface RegionBuildSlice {
  regionId: string;
  regionName: string;
  methods: Array<MethodTrace & { label: string }>;
  memberCount: number;
}

export interface RunPlan {
  /** false 时存在构建错误，本次运行零批次提交（决策 2.33）。 */
  ok: boolean;
  errors: string[];
  participating: RegionBuildSlice[];
  /** 未连接模拟节点而被跳过的配置区域（对应 REGION_NOT_CONNECTED 警告）。 */
  skippedRegionIds: string[];
  batches: BatchPlan[];
}

/**
 * 规划工作流运行的构建阶段：图错误先行拦截；然后按画布顺序为每个模拟节点
 * 按输入连线收集所连配置区域的成员，合并成一个批次。
 */
export function planWorkflowRun(definition: WorkflowDefinition): RunPlan {
  const errors: string[] = [];
  const regionById = new Map(definition.regions.map((region) => [region.id, region]));
  const nodeById = new Map(definition.nodes.map((node) => [node.id, node]));

  const simulationNodes = definition.nodes.filter((node) => node.kind === "simulation");
  const connectedRegionIds = new Set<string>();
  for (const edge of definition.edges) {
    const target = nodeById.get(edge.target_node_id);
    if (
      target?.kind === "simulation" &&
      edge.target_port_id === "in" &&
      edge.source_port_id === REGION_BOUNDARY_OUT_PORT &&
      regionById.get(edge.source_node_id)?.kind === "configuration"
    ) {
      connectedRegionIds.add(edge.source_node_id);
    }
  }

  const skippedRegionIds = definition.regions
    .filter(
      (region) => region.kind === "configuration" && !connectedRegionIds.has(region.id),
    )
    .map((region) => region.id);

  const participating: RegionBuildSlice[] = [];
  const compiledByRegion = new Map<string, { members: CompiledMember[]; methods: MethodTrace[] }>();
  for (const regionId of connectedRegionIds) {
    const expanded = expandConfigurationRegion(definition, regionId);
    if (!expanded.ok) {
      errors.push(
        `区域 ${regionById.get(regionId)?.name ?? regionId} 无法编译：` +
          firstErrorMessage(expanded.diagnostics),
      );
      continue;
    }
    compiledByRegion.set(regionId, {
      members: expanded.members,
      methods: expanded.methods,
    });
    const region = regionById.get(regionId);
    participating.push({
      regionId,
      regionName: region?.name ?? regionId,
      methods: withNodeLabels(expanded.methods, definition),
      memberCount: expanded.members.length,
    });
  }

  const batches: BatchPlan[] = [];
  for (const node of simulationNodes) {
    const sourceRegionIds = orderedRegionSources(definition, node.id, connectedRegionIds);
    if (sourceRegionIds.length === 0) {
      errors.push(`模拟节点未连接配置区域，批次无法成立`);
      continue;
    }
    const members: BatchMember[] = [];
    let missingCompile = false;
    for (const regionId of sourceRegionIds) {
      const compiled = compiledByRegion.get(regionId);
      if (compiled === undefined) {
        missingCompile = true;
        continue;
      }
      members.push(...compiled.members.map((member) => ({ ...member, input: member.input })));
    }
    if (missingCompile) {
      continue;
    }
    const duplicate = firstDuplicateItemId(members);
    if (duplicate !== null) {
      errors.push(`批次内成员 item_id 重复：${duplicate}`);
      continue;
    }
    if (members.length > MAX_BATCH_MEMBERS) {
      errors.push(`批次成员数 ${members.length} 超过上限 ${MAX_BATCH_MEMBERS}`);
      continue;
    }
    batches.push({
      nodeId: node.id,
      name: batchName(definition, members),
      concurrency: concurrencyOf(node),
      sourceRegionIds,
      members,
    });
  }

  return {
    ok: errors.length === 0 && batches.length > 0,
    errors,
    participating,
    skippedRegionIds,
    batches,
  };
}

/** 构建阶段每个方法步骤保留的最小执行时长（ms）；保证逐节点过程可见。 */
export const MIN_METHOD_STEP_MS = 150;

export type MethodStepEvent = "running" | "done" | "skipped";

/**
 * 构建阶段逐节点限速推进（决策 2.34 修订）：运行过程按方法轨迹顺序逐步呈现，
 * 每个节点保留最小执行时长；不改变编译结果，只约束运行过程的节奏。
 * 取消时剩余步骤立即标记 skipped，不再等待。
 */
export async function paceBuildSteps(
  slices: Array<{ regionId: string; methods: Array<{ nodeId: string }> }>,
  options: {
    enabled: boolean;
    stepMs?: number;
    sleep?: (ms: number) => Promise<void>;
    shouldStop?: () => boolean;
    onMethodStatus: (regionId: string, nodeId: string, status: MethodStepEvent) => void;
  },
): Promise<void> {
  const stepMs = options.stepMs ?? MIN_METHOD_STEP_MS;
  const sleep =
    options.sleep ??
    ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  for (const slice of slices) {
    for (const method of slice.methods) {
      if (options.shouldStop?.()) {
        options.onMethodStatus(slice.regionId, method.nodeId, "skipped");
        continue;
      }
      options.onMethodStatus(slice.regionId, method.nodeId, "running");
      if (options.enabled) {
        await sleep(stepMs);
      }
      options.onMethodStatus(slice.regionId, method.nodeId, "done");
    }
  }
}

/** 轻量可运行判定：无图错误时，至少存在一个连接了配置区域的模拟节点。 */
export function hasRunnableBatch(definition: WorkflowDefinition): boolean {
  const configRegionIds = new Set(
    definition.regions.filter((region) => region.kind === "configuration").map((region) => region.id),
  );
  const simulationIds = new Set(
    definition.nodes.filter((node) => node.kind === "simulation").map((node) => node.id),
  );
  return definition.edges.some(
    (edge) =>
      edge.target_port_id === "in" &&
      edge.source_port_id === REGION_BOUNDARY_OUT_PORT &&
      configRegionIds.has(edge.source_node_id) &&
      simulationIds.has(edge.target_node_id),
  );
}

/**
 * 区域范围运行计划（决策 2.40）：区域运行 = 全部运行的区域子集。
 * 构建阶段只编译目标区域；批次为连接该区域的模拟节点（按节点顺序），成员仅来自该区域。
 */
export function planRegionRun(definition: WorkflowDefinition, regionId: string): RunPlan {
  const errors: string[] = [];
  const region = definition.regions.find((item) => item.id === regionId);
  if (region === undefined || region.kind !== "configuration") {
    return {
      ok: false,
      errors: ["只有配置区域可以运行"],
      participating: [],
      skippedRegionIds: [],
      batches: [],
    };
  }

  const expanded = expandConfigurationRegion(definition, regionId);
  if (!expanded.ok) {
    return {
      ok: false,
      errors: [`区域 ${region.name} 无法编译：${firstErrorMessage(expanded.diagnostics)}`],
      participating: [],
      skippedRegionIds: [],
      batches: [],
    };
  }

  const members: BatchMember[] = expanded.members.map((member) => ({
    ...member,
    input: member.input,
  }));
  const duplicate = firstDuplicateItemId(members);
  if (duplicate !== null) {
    errors.push(`批次内成员 item_id 重复：${duplicate}`);
  } else if (members.length > MAX_BATCH_MEMBERS) {
    errors.push(`批次成员数 ${members.length} 超过上限 ${MAX_BATCH_MEMBERS}`);
  }

  const batches: BatchPlan[] = [];
  if (errors.length === 0) {
    const connectedRegionIds = new Set<string>([regionId]);
    for (const node of definition.nodes.filter((item) => item.kind === "simulation")) {
      if (orderedRegionSources(definition, node.id, connectedRegionIds).length === 0) {
        continue;
      }
      batches.push({
        nodeId: node.id,
        name: batchName(definition, members),
        concurrency: concurrencyOf(node),
        sourceRegionIds: [regionId],
        members: members.map((member) => ({ ...member })),
      });
    }
    if (batches.length === 0) {
      errors.push("该区域未连接模拟节点，批次无法成立");
    }
  }

  return {
    ok: errors.length === 0 && batches.length > 0,
    errors,
    participating: [
      {
        regionId,
        regionName: region.name,
        methods: withNodeLabels(expanded.methods, definition),
        memberCount: members.length,
      },
    ],
    skippedRegionIds: [],
    batches,
  };
}

/**
 * 分析区域运行的「获取输入」阶段计划（2026-08-26 定案）：
 * 收集边界输入连接且「未就绪」的模拟节点（缺会话、无输入指纹或指纹不匹配），
 * 按其连接的配置区域展开批次；就绪的模拟节点与数据提供节点不产生批次。
 * 返回的 RunPlan 批次为空时表示无需补跑模拟，可直接进入查询阶段。
 */
export function planAnalysisInputRun(
  definition: WorkflowDefinition,
  regionId: string,
): RunPlan {
  const errors: string[] = [];
  const regionById = new Map(definition.regions.map((region) => [region.id, region]));
  const status = analysisInputStatus(definition, regionId);
  const needsRun = definition.nodes.filter(
    (node) =>
      node.kind === "simulation" &&
      status.nodes.some(
        (item) => item.nodeId === node.id && item.status !== "ready",
      ),
  );
  if (needsRun.length === 0) {
    return { ok: true, errors: [], participating: [], skippedRegionIds: [], batches: [] };
  }

  const connectedRegionIds = new Set<string>();
  for (const node of needsRun) {
    for (const edge of definition.edges) {
      if (
        edge.target_node_id === node.id &&
        edge.target_port_id === "in" &&
        edge.source_port_id === REGION_BOUNDARY_OUT_PORT &&
        regionById.get(edge.source_node_id)?.kind === "configuration"
      ) {
        connectedRegionIds.add(edge.source_node_id);
      }
    }
  }

  const participating: RegionBuildSlice[] = [];
  const compiledByRegion = new Map<
    string,
    { members: CompiledMember[]; methods: MethodTrace[] }
  >();
  for (const connectedRegionId of connectedRegionIds) {
    const expanded = expandConfigurationRegion(definition, connectedRegionId);
    if (!expanded.ok) {
      errors.push(
        `区域 ${regionById.get(connectedRegionId)?.name ?? connectedRegionId} 无法编译：` +
          firstErrorMessage(expanded.diagnostics),
      );
      continue;
    }
    compiledByRegion.set(connectedRegionId, {
      members: expanded.members,
      methods: expanded.methods,
    });
    const region = regionById.get(connectedRegionId);
    participating.push({
      regionId: connectedRegionId,
      regionName: region?.name ?? connectedRegionId,
      methods: withNodeLabels(expanded.methods, definition),
      memberCount: expanded.members.length,
    });
  }

  const batches: BatchPlan[] = [];
  for (const node of needsRun) {
    const sourceRegionIds = orderedRegionSources(definition, node.id, connectedRegionIds);
    if (sourceRegionIds.length === 0) {
      errors.push(`模拟节点未连接配置区域，批次无法成立`);
      continue;
    }
    const members: BatchMember[] = [];
    let missingCompile = false;
    for (const sourceRegionId of sourceRegionIds) {
      const compiled = compiledByRegion.get(sourceRegionId);
      if (compiled === undefined) {
        missingCompile = true;
        continue;
      }
      members.push(...compiled.members.map((member) => ({ ...member, input: member.input })));
    }
    if (missingCompile) {
      continue;
    }
    const duplicate = firstDuplicateItemId(members);
    if (duplicate !== null) {
      errors.push(`批次内成员 item_id 重复：${duplicate}`);
      continue;
    }
    if (members.length > MAX_BATCH_MEMBERS) {
      errors.push(`批次成员数 ${members.length} 超过上限 ${MAX_BATCH_MEMBERS}`);
      continue;
    }
    batches.push({
      nodeId: node.id,
      name: batchName(definition, members),
      concurrency: concurrencyOf(node),
      sourceRegionIds,
      members,
    });
  }

  return {
    ok: errors.length === 0 && batches.length > 0,
    errors,
    participating,
    skippedRegionIds: [],
    batches,
  };
}

/** 单个模拟节点批次的输入指纹（数据源真值：有序来源区域 + 有序成员输入）。 */
export function batchInputFingerprint(
  batch: Pick<BatchPlan, "sourceRegionIds" | "members">,
): string {
  return hashValue({
    sourceRegionIds: batch.sourceRegionIds,
    members: batch.members.map((member) => [member.item_id, member.input]),
  });
}

/**
 * 模拟节点当前配置区域的期望输入指纹；未连接配置区域或区域无法编译时返回 null。
 * 与批次写入的 last_input_fingerprint 比对，用于判断 last_sessions 是否过期。
 */
export function expectedInputFingerprint(
  definition: WorkflowDefinition,
  nodeId: string,
): string | null {
  const sourceRegionIds = configRegionIdsOf(definition, nodeId);
  if (sourceRegionIds.length === 0) {
    return null;
  }
  const members = mergedMembersFor(definition, sourceRegionIds);
  return members === null
    ? null
    : batchInputFingerprint({ sourceRegionIds, members });
}

export interface AnalysisInputNodeStatus {
  nodeId: string;
  status: "ready" | "missing" | "stale";
  /** 是否连接了配置区域（可计算期望指纹/可补跑）。 */
  hasConfigRegion: boolean;
}

export interface AnalysisInputStatus {
  nodes: AnalysisInputNodeStatus[];
  /** 存在需要补跑或会话过期的模拟节点。 */
  needsRun: boolean;
}

/**
 * 分析区域边界输入的就绪状态（2026-08-26 定案）：
 * - 缺会话（last_sessions 缺失/为空）→ missing；
 * - 有会话但无 last_input_fingerprint 或与当前配置区域指纹不一致 → stale；
 * - 有会话且指纹一致 → ready。
 * 未连接配置区域的模拟节点无法核对/补跑：有会话视为 ready，无会话视为 missing。
 */
export function analysisInputStatus(
  definition: WorkflowDefinition,
  regionId: string,
): AnalysisInputStatus {
  const nodeById = new Map(definition.nodes.map((node) => [node.id, node]));
  const boundarySimulationIds = new Set<string>();
  for (const edge of definition.edges) {
    if (
      edge.target_node_id === regionId &&
      edge.target_port_id === REGION_BOUNDARY_IN_PORT
    ) {
      const source = nodeById.get(edge.source_node_id);
      if (source?.kind === "simulation") {
        boundarySimulationIds.add(source.id);
      }
    }
  }

  const nodes: AnalysisInputNodeStatus[] = [];
  for (const node of definition.nodes) {
    if (node.kind !== "simulation" || !boundarySimulationIds.has(node.id)) {
      continue;
    }
    const sessions = sessionIdsOf(node);
    const sourceRegionIds = configRegionIdsOf(definition, node.id);
    if (sourceRegionIds.length === 0) {
      nodes.push({
        nodeId: node.id,
        status: sessions.length > 0 ? "ready" : "missing",
        hasConfigRegion: false,
      });
      continue;
    }
    if (sessions.length === 0) {
      nodes.push({ nodeId: node.id, status: "missing", hasConfigRegion: true });
      continue;
    }
    const expected = expectedInputFingerprint(definition, node.id);
    const stored = node.params.last_input_fingerprint;
    const ready =
      expected !== null && typeof stored === "string" && stored === expected;
    nodes.push({
      nodeId: node.id,
      status: ready ? "ready" : "stale",
      hasConfigRegion: true,
    });
  }
  return { nodes, needsRun: nodes.some((item) => item.status !== "ready") };
}

/** 模拟节点输入侧连接的配置区域 id（按连线顺序）。 */
function configRegionIdsOf(definition: WorkflowDefinition, nodeId: string): string[] {
  const regionById = new Map(definition.regions.map((region) => [region.id, region]));
  const ordered: string[] = [];
  for (const edge of definition.edges) {
    if (
      edge.target_node_id === nodeId &&
      edge.target_port_id === "in" &&
      edge.source_port_id === REGION_BOUNDARY_OUT_PORT &&
      regionById.get(edge.source_node_id)?.kind === "configuration" &&
      !ordered.includes(edge.source_node_id)
    ) {
      ordered.push(edge.source_node_id);
    }
  }
  return ordered;
}

/** 按来源区域顺序合并展开成员；任一区域编译失败返回 null。 */
function mergedMembersFor(
  definition: WorkflowDefinition,
  sourceRegionIds: string[],
): BatchMember[] | null {
  const members: BatchMember[] = [];
  for (const sourceRegionId of sourceRegionIds) {
    const expanded = expandConfigurationRegion(definition, sourceRegionId);
    if (!expanded.ok) {
      return null;
    }
    members.push(
      ...expanded.members.map((member) => ({ ...member, input: member.input })),
    );
  }
  return members;
}

/** 模拟节点参数中的会话 ID 列表（非法值忽略）。 */
function sessionIdsOf(node: WorkflowNode): string[] {
  const raw = node.params.last_sessions;
  return Array.isArray(raw)
    ? raw.filter((item): item is string => typeof item === "string")
    : [];
}

/** 区域校验失败的聚合错误（决策 2.40）：成员级诊断拼进批次失败原因。 */
export function validationErrorMessage(
  response: ValidateInputsResponse,
): string {
  const failed = response.members.filter((member) => !member.ok);
  const parts = failed.map((member) => {
    const detail = member.details?.[0]?.message;
    return detail === undefined ? member.item_id : `${member.item_id}：${detail}`;
  });
  return `区域校验未通过（${failed.length} 个成员）——${parts.join("；")}`;
}

/**
 * 区域运行只保留目标区域相关的图/节点诊断（决策 2.40：节点校验只看节点自身）。
 * 无对象引用的全局诊断（schema/meta 等）仍保留，避免在坏图上继续运行。
 */
export function scopedDiagnostics(
  definition: WorkflowDefinition,
  diagnostics: Diagnostic[],
  regionIds: Set<string>,
): Diagnostic[] {
  const nodeById = new Map(definition.nodes.map((node) => [node.id, node]));
  const edgeById = new Map(definition.edges.map((edge) => [edge.id, edge]));
  return diagnostics.filter((item) => {
    if (item.region_id != null) {
      return regionIds.has(item.region_id);
    }
    if (item.node_id != null) {
      const node = nodeById.get(item.node_id);
      if (node === undefined) {
        return false;
      }
      if (node.region_id != null) {
        return regionIds.has(node.region_id);
      }
      return (
        node.kind === "simulation" &&
        orderedRegionSources(definition, node.id, regionIds).length > 0
      );
    }
    if (item.edge_id != null) {
      const edge = edgeById.get(item.edge_id);
      if (edge === undefined) {
        return false;
      }
      const sourceRegion = endpointRegion(definition, nodeById, edge.source_node_id);
      const targetRegion = endpointRegion(definition, nodeById, edge.target_node_id);
      return (
        (sourceRegion !== null && regionIds.has(sourceRegion)) ||
        (targetRegion !== null && regionIds.has(targetRegion))
      );
    }
    return true;
  });
}

/** 方法轨迹补充节点显示名，供轨迹面板与画布状态展示。 */
function withNodeLabels(
  methods: MethodTrace[],
  definition: WorkflowDefinition,
): Array<MethodTrace & { label: string }> {
  return methods.map((method) => {
    const node = definition.nodes.find((item) => item.id === method.nodeId);
    const spec = node === undefined ? null : getNodeKindSpec(node.kind);
    return { ...method, label: spec?.displayName ?? node?.kind ?? method.nodeId };
  });
}

/** 批次输入连线上的来源区域，按连线顺序去重。 */
function orderedRegionSources(
  definition: WorkflowDefinition,
  simulationNodeId: string,
  connectedRegionIds: Set<string>,
): string[] {
  const ordered: string[] = [];
  for (const edge of definition.edges) {
    if (
      edge.target_node_id === simulationNodeId &&
      edge.target_port_id === "in" &&
      connectedRegionIds.has(edge.source_node_id) &&
      !ordered.includes(edge.source_node_id)
    ) {
      ordered.push(edge.source_node_id);
    }
  }
  return ordered;
}

function endpointRegion(
  definition: WorkflowDefinition,
  nodeById: Map<string, WorkflowNode>,
  endpointId: string,
): string | null {
  if (definition.regions.some((region) => region.id === endpointId)) {
    return endpointId;
  }
  return nodeById.get(endpointId)?.region_id ?? null;
}

function batchName(definition: WorkflowDefinition, members: BatchMember[]): string {
  for (const member of members) {
    const meta = member.input.meta as Record<string, unknown> | undefined;
    if (meta !== undefined && typeof meta.name === "string" && meta.name.trim() !== "") {
      return meta.name;
    }
  }
  return definition.meta.name;
}

function concurrencyOf(node: WorkflowNode): number | null {
  const value = node.params.concurrency;
  return typeof value === "number" && Number.isInteger(value) && value >= 1 && value <= 16
    ? value
    : null;
}

function firstDuplicateItemId(members: BatchMember[]): string | null {
  const seen = new Set<string>();
  for (const member of members) {
    if (seen.has(member.item_id)) {
      return member.item_id;
    }
    seen.add(member.item_id);
  }
  return null;
}

function firstErrorMessage(diagnostics: Diagnostic[]): string {
  const first = diagnostics.find((item) => item.severity === "error") ?? diagnostics[0];
  return first?.message ?? "未知错误";
}
