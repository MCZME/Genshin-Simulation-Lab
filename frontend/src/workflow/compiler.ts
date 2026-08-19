import type {
  CompileResult,
  Diagnostic,
  DiagnosticSeverity,
  WorkflowDefinition,
} from "./types";
import {
  MAX_BATCH_MEMBERS,
  REGION_BOUNDARY_IN_PORT,
} from "./types";
import { getNodeKindSpec, groupFragments, singleFragment } from "./registry";
import { setPath } from "./path";

interface BoundaryEntry {
  edgeId: string;
  nodeId: string;
  path: string;
  variants: { item_id: string; path: string; value: unknown }[];
}

interface PartialInput {
  input: Record<string, unknown>;
  itemIds: string[];
}

export function createSimulationInputSkeleton(name: string): Record<string, unknown> {
  return {
    schema_version: 2,
    kind: "simulation_input",
    meta: { name, description: "" },
    team: [],
    scene: {},
    input_trace: [],
    rules: { enabled: [] },
    run_options: { max_frames: 18000 },
  };
}

export function compileConfigurationRegion(
  definition: WorkflowDefinition,
  regionId: string,
): CompileResult {
  const diagnostics: Diagnostic[] = [];
  const region = definition.regions.find((item) => item.id === regionId);
  if (region === undefined) {
    return fail(regionId, [compileError("REGION_NOT_FOUND", `区域不存在：${regionId}`)]);
  }
  if (region.kind !== "configuration") {
    return fail(regionId, [compileError("REGION_KIND_UNSUPPORTED", "只有配置区域可以编译成员")]);
  }

  const boundaryEdges = definition.edges.filter(
    (edge) => edge.target_node_id === regionId && edge.target_port_id === REGION_BOUNDARY_IN_PORT,
  );
  if (boundaryEdges.length === 0) {
    return fail(regionId, [compileError("EMPTY_REGION", "配置区域没有数据汇入，阻止运行")]);
  }

  const entries: BoundaryEntry[] = [];
  for (const edge of boundaryEdges) {
    const node = definition.nodes.find((item) => item.id === edge.source_node_id);
    if (node === undefined || getNodeKindSpec(node.kind) === null) {
      diagnostics.push(
        compileError("SOURCE_NODE_INVALID", `边界输入引用了无效节点：${edge.source_node_id}`),
      );
      continue;
    }
    const single = singleFragment(node, definition);
    const variants =
      node.kind === "enum" || node.kind === "range" ? groupFragments(node) : single !== null ? [single] : [];
    if (variants.length === 0) {
      continue;
    }
    entries.push({
      edgeId: edge.id,
      nodeId: node.id,
      path: variants[0].path,
      variants,
    });
  }

  if (diagnostics.some((item) => item.severity === "error")) {
    return fail(regionId, diagnostics);
  }

  const orderedEntries = keepLastWriterPerPath(entries, diagnostics);
  const base = createSimulationInputSkeleton(definition.meta.name);
  let partials: PartialInput[] = [{ input: base, itemIds: [] }];
  for (const entry of orderedEntries) {
    const next: PartialInput[] = [];
    for (const partial of partials) {
      for (const variant of entry.variants) {
        const input = structuredClone(partial.input);
        setPath(input, variant.path, variant.value);
        next.push({ input, itemIds: [...partial.itemIds, variant.item_id] });
      }
    }
    partials = next;
  }

  if (partials.length > MAX_BATCH_MEMBERS) {
    diagnostics.push(
      compileError(
        "MEMBER_LIMIT_EXCEEDED",
        `展开成员数 ${partials.length} 超过上限 ${MAX_BATCH_MEMBERS}`,
      ),
    );
    return fail(regionId, diagnostics);
  }

  const members = partials.map((partial) => {
    ensureTeamSlots(partial.input);
    return {
      item_id: partial.itemIds.length > 0 ? partial.itemIds.join("+") : "root",
      input: partial.input,
    };
  });
  return { ok: true, region_id: regionId, members, diagnostics };
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

function keepLastWriterPerPath(
  entries: BoundaryEntry[],
  diagnostics: Diagnostic[],
): BoundaryEntry[] {
  const lastWriter = new Map<string, number>();
  entries.forEach((entry, index) => {
    lastWriter.set(entry.path, index);
  });

  const ordered: BoundaryEntry[] = [];
  entries.forEach((entry, index) => {
    if (lastWriter.get(entry.path) !== index) {
      diagnostics.push(
        compileWarning(
          "PATH_OVERRIDE",
          `同路径片段被后写入者覆盖：${entry.path}`,
          entry.nodeId,
          entry.edgeId,
          entry.path,
        ),
      );
      return;
    }
    ordered.push(entry);
  });
  return ordered;
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

function fail(regionId: string, diagnostics: Diagnostic[]): CompileResult {
  return { ok: false, region_id: regionId, members: [], diagnostics };
}
