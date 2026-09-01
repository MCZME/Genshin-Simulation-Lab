import type { WorkflowDefinition } from "../workflow/types";
import type { EditorState } from "./editor_state";

/**
 * 存量工作流迁移：
 * - 算子化重做（决策 2.32）后，processing 与 query_config 节点及其连线在加载时移除；
 * - 取数节点合并（2026-08-26 修订）后，fetch_runs / fetch_events 转为 fetch + source。
 * - 取数节点移除帧范围（2026-08-26 修订）后，旧 fetch 参数 frame_min/frame_max 丢弃。
 * - 表格宽度单模式化（决策 2.46）后，旧 table_config 参数 width_mode 丢弃；
 *   auto（或缺省）工作流中随高度拖拽写入的宽度快照一并丢弃，避免误判为手动拖宽。
 */
const RETIRED_NODE_KINDS = new Set(["processing", "query_config"]);
const FETCH_SOURCE_BY_KIND: Record<string, "runs" | "events"> = {
  fetch_runs: "runs",
  fetch_events: "events",
};

export function migrateWorkflowDefinition(
  definition: WorkflowDefinition,
): WorkflowDefinition {
  const hasRetired = definition.nodes.some((node) => RETIRED_NODE_KINDS.has(node.kind));
  const hasLegacyFetch = definition.nodes.some((node) => node.kind in FETCH_SOURCE_BY_KIND);
  const hasLegacyFrameParams = definition.nodes.some(
    (node) =>
      node.kind === "fetch" &&
      (node.params.frame_min !== undefined || node.params.frame_max !== undefined),
  );
  const hasLegacyWidthMode = definition.nodes.some(
    (node) => node.kind === "table_config" && node.params.width_mode !== undefined,
  );
  if (
    !hasRetired &&
    !hasLegacyFetch &&
    !hasLegacyFrameParams &&
    !hasLegacyWidthMode
  ) {
    return definition;
  }
  const retiredIds = new Set(
    definition.nodes
      .filter((node) => RETIRED_NODE_KINDS.has(node.kind))
      .map((node) => node.id),
  );
  // 旧表格配置的宽度模式：auto/缺省表示宽度未手动拖过；fixed 表示用户拖宽过。
  const legacyWidthModes = new Map<string, "auto" | "fixed">();
  for (const node of definition.nodes) {
    if (node.kind === "table_config" && node.params.width_mode === "fixed") {
      legacyWidthModes.set(node.id, "fixed");
    } else if (node.kind === "table_config") {
      legacyWidthModes.set(node.id, "auto");
    }
  }
  const viewWidthMode = new Map<string, "auto" | "fixed" | undefined>();
  for (const edge of definition.edges) {
    const mode = legacyWidthModes.get(edge.source_node_id);
    if (mode !== undefined && edge.target_port_id === "config") {
      viewWidthMode.set(edge.target_node_id, mode);
    }
  }
  const nodes = definition.nodes
    .filter((node) => !retiredIds.has(node.id))
    .map((node) => {
      if (
        node.kind === "member_table" &&
        viewWidthMode.get(node.id) !== "fixed" &&
        node.size?.width !== undefined
      ) {
        const size = { ...node.size };
        delete size.width;
        return {
          ...node,
          size: size.height === undefined ? undefined : size,
        };
      }
      if (node.kind === "table_config") {
        const params = { ...node.params };
        delete params.width_mode;
        return { ...node, params };
      }
      if (node.kind === "fetch") {
        const params = { ...node.params };
        delete params.frame_min;
        delete params.frame_max;
        return { ...node, params };
      }
      const source = FETCH_SOURCE_BY_KIND[node.kind];
      if (source === undefined) {
        return node;
      }
      return {
        ...node,
        kind: "fetch" as const,
        params: { source, ...node.params },
      };
    });
  return {
    ...definition,
    nodes,
    edges: definition.edges.filter(
      (edge) => !retiredIds.has(edge.source_node_id) && !retiredIds.has(edge.target_node_id),
    ),
  };
}

/**
 * 载荷提取列 event_type 回填（2026-08-26 契约修订）：
 * 目录内唯一路径匹配时自动填写；歧义或无匹配保持缺省（空），由编辑器强制选择。
 */
export function backfillPayloadEventTypes(
  definition: WorkflowDefinition,
  eventTypes: { name: string; fields: { path: string }[] }[],
): WorkflowDefinition {
  let changed = false;
  const nodes = definition.nodes.map((node) => {
    if (node.kind !== "fetch" || node.params.source !== "events") {
      return node;
    }
    const rows = Array.isArray(node.params.payload_columns)
      ? node.params.payload_columns
      : [];
    let rowChanged = false;
    const nextRows = rows.map((row) => {
      if (row === null || typeof row !== "object" || Array.isArray(row)) {
        return row;
      }
      const record = row as Record<string, unknown>;
      if (typeof record.event_type === "string") {
        return row;
      }
      const matches = eventTypes.filter((eventType) =>
        eventType.fields.some((field) => field.path === record.path),
      );
      if (matches.length !== 1) {
        return row;
      }
      rowChanged = true;
      return { ...record, event_type: matches[0].name };
    });
    if (!rowChanged) {
      return node;
    }
    changed = true;
    return { ...node, params: { ...node.params, payload_columns: nextRows } };
  });
  return changed ? { ...definition, nodes } : definition;
}

export function definitionToEditorState(definition: WorkflowDefinition): EditorState {
  const saved = deepClone(migrateWorkflowDefinition(definition));
  return {
    definition: saved,
    selection: { regions: [], nodes: [], edges: [] },
    dirty: false,
    past: [],
    future: [],
    saved,
  };
}

export function editorStateToDefinition(state: EditorState): WorkflowDefinition {
  return deepClone(state.definition);
}

export function cloneEditorState(state: EditorState): EditorState {
  return {
    definition: deepClone(state.definition),
    selection: {
      regions: [...state.selection.regions],
      nodes: [...state.selection.nodes],
      edges: [...state.selection.edges],
    },
    dirty: state.dirty,
    past: state.past.map((definition) => deepClone(definition)),
    future: state.future.map((definition) => deepClone(definition)),
    saved: state.saved === null ? null : deepClone(state.saved),
  };
}

function deepClone<T>(value: T): T {
  return structuredClone(value);
}
