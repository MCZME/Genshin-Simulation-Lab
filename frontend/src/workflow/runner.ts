import type { CompiledMember, Diagnostic, WorkflowDefinition, WorkflowNode } from "./types";
import { MAX_BATCH_MEMBERS, REGION_BOUNDARY_OUT_PORT } from "./types";
import { expandConfigurationRegion } from "./compiler";
import type { MethodTrace } from "./compiler";
import { getNodeKindSpec } from "./registry";

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

/** 单区域检查计划（决策 2.35）：编译该区域，供检查流程对成员做后端输入校验。 */
export interface RegionCheckPlan {
  ok: boolean;
  error: string | null;
  regionId: string;
  regionName: string;
  methods: Array<MethodTrace & { label: string }>;
  members: BatchMember[];
}

export function planRegionCheck(
  definition: WorkflowDefinition,
  regionId: string,
): RegionCheckPlan {
  const region = definition.regions.find((item) => item.id === regionId);
  if (region === undefined || region.kind !== "configuration") {
    return {
      ok: false,
      error: "只有配置区域可以检查",
      regionId,
      regionName: region?.name ?? regionId,
      methods: [],
      members: [],
    };
  }
  const expanded = expandConfigurationRegion(definition, regionId);
  if (!expanded.ok) {
    return {
      ok: false,
      error: `无法编译：${firstErrorMessage(expanded.diagnostics)}`,
      regionId,
      regionName: region.name,
      methods: [],
      members: [],
    };
  }
  return {
    ok: true,
    error: null,
    regionId,
    regionName: region.name,
    methods: withNodeLabels(expanded.methods, definition),
    members: expanded.members.map((member) => ({ ...member, input: member.input })),
  };
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
