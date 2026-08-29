import type { components } from "./schema";

type Schema = components["schemas"];

export type WorkspaceResponse = Schema["WorkspaceResponse"];
export type UiSettingsResponse = Schema["UiSettingsResponse"];
export type WorkflowListResponse = Schema["WorkflowListResponse"];
export type WorkflowListItem = Schema["WorkflowListItem"];
export type WorkflowResponse = Schema["WorkflowResponse"];
export type ValidateInputsResponse = Schema["ValidateInputsResponse"];
export type RunStatusResponse = Schema["RunStatusResponse"];
export type RunMemberStatus = Schema["RunMemberStatus"];
export type RunListResponse = Schema["RunListResponse"];
export type RunListItem = Schema["RunListItem"];
export type RunDetailResponse = Schema["RunDetailResponse"];
/** 分析查询计划节点（契约 v2：结构化计划，不含 SQL 文本）。 */
export interface AnalysisPlanNodeDto {
  id: string;
  kind: string;
  params: Record<string, unknown>;
  inputs: string[];
}

export interface ExecutePlanRequest {
  session_ids: string[];
  nodes: AnalysisPlanNodeDto[];
  outputs: string[];
}

export interface AnalysisColumnDto {
  name: string;
  type: string;
}

export interface AnalysisTableResponse {
  columns: AnalysisColumnDto[];
  rows: unknown[][];
  truncated: boolean;
}

export interface ExecutePlanResponse {
  tables: Record<string, AnalysisTableResponse>;
}

/** 输入快照结构树节点：对象 / 列表 / 标量；列表不枚举位置。 */
export interface AnalysisSchemaNodeDto {
  key: string;
  label: string;
  kind: "object" | "list" | "scalar";
  type?: string;
  description?: string;
  value_kind?: string;
  default_name?: string;
  default_name_template?: string;
  children?: AnalysisSchemaNodeDto[];
}

export interface AnalysisSchemaResponse {
  tables: {
    name: string;
    columns: { name: string; type: string; description: string; value_kind: string }[];
  }[];
  event_types: {
    name: string;
    fields: { path: string; type: string; description: string; value_kind: string }[];
  }[];
  snapshot_tree: AnalysisSchemaNodeDto | null;
}
export type AssetListResponse = Schema["AssetListResponse"];
export type AssetResponse = Schema["AssetResponse"];
export type Diagnostic = Schema["Diagnostic"];

export interface BatchMemberPayload {
  item_id: string;
  input: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly code: string;
  readonly details: unknown[];
  readonly status: number;

  constructor(code: string, message: string, details: unknown[], status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.details = details;
    this.status = status;
  }
}

interface ErrorBody {
  code?: string;
  message?: string;
  details?: unknown[];
}

export async function getWorkspace(): Promise<WorkspaceResponse> {
  return request<WorkspaceResponse>("/workspace");
}

/** 界面偏好设置持久化在后端项目配置（config.toml 的 ui 节）。 */
export async function getUiSettings(): Promise<UiSettingsResponse> {
  return request<UiSettingsResponse>("/settings");
}

export async function saveUiSettings(runAnimation: boolean): Promise<UiSettingsResponse> {
  return request<UiSettingsResponse>("/settings", {
    method: "PUT",
    body: JSON.stringify({ run_animation: runAnimation }),
  });
}

export async function listWorkflows(): Promise<WorkflowListResponse> {
  return request<WorkflowListResponse>("/workflows");
}

export async function createWorkflow(name = "未命名工作流"): Promise<WorkflowResponse> {
  return request<WorkflowResponse>("/workflows", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function getWorkflow(workflowId: string): Promise<WorkflowResponse> {
  return request<WorkflowResponse>(`/workflows/${encodeURIComponent(workflowId)}`);
}

export async function saveWorkflow(
  workflowId: string,
  definition: unknown,
): Promise<WorkflowResponse> {
  return request<WorkflowResponse>(`/workflows/${encodeURIComponent(workflowId)}`, {
    method: "PUT",
    body: JSON.stringify(definition),
  });
}

export async function deleteWorkflow(workflowId: string): Promise<void> {
  await request<undefined>(`/workflows/${encodeURIComponent(workflowId)}`, {
    method: "DELETE",
  });
}

export async function validateInputs(
  members: BatchMemberPayload[],
): Promise<ValidateInputsResponse> {
  return request<ValidateInputsResponse>("/inputs/validate", {
    method: "POST",
    body: JSON.stringify({ members }),
  });
}

export async function submitRun(
  members: BatchMemberPayload[],
  options: { name?: string; concurrency?: number } = {},
): Promise<RunStatusResponse> {
  const body: Record<string, unknown> = {
    name: options.name ?? "",
    members,
  };
  if (options.concurrency !== undefined) {
    body.concurrency = options.concurrency;
  }
  return request<RunStatusResponse>("/runs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getRun(runId: string): Promise<RunStatusResponse> {
  return request<RunStatusResponse>(`/runs/${encodeURIComponent(runId)}`);
}

export async function cancelRun(runId: string): Promise<RunStatusResponse> {
  return request<RunStatusResponse>(`/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
  });
}

/** 历史运行列表（结果库浏览器与数据提供节点编辑器）；后端按 created_at 倒序返回。 */
export async function listResults(
  options: {
    limit?: number;
    offset?: number;
    state?: "completed" | "failed" | "cancelled";
    q?: string;
    createdFrom?: string;
    createdTo?: string;
    ids?: string[];
  } = {},
): Promise<RunListResponse> {
  const params = new URLSearchParams();
  if (options.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  if (options.offset !== undefined) {
    params.set("offset", String(options.offset));
  }
  if (options.state !== undefined) {
    params.set("state", options.state);
  }
  if (options.q !== undefined && options.q.trim() !== "") {
    params.set("q", options.q.trim());
  }
  if (options.createdFrom !== undefined) {
    params.set("created_from", options.createdFrom);
  }
  if (options.createdTo !== undefined) {
    params.set("created_to", options.createdTo);
  }
  if (options.ids !== undefined && options.ids.length > 0) {
    params.set("ids", options.ids.join(","));
  }
  const query = params.toString();
  return request<RunListResponse>(`/results${query === "" ? "" : `?${query}`}`);
}

/** 运行详情概要（不含事件流、指标数值，决策 2.37）。 */
export async function getResultDetail(sessionId: string): Promise<RunDetailResponse> {
  return request<RunDetailResponse>(`/results/${encodeURIComponent(sessionId)}`);
}

export type EventItem = Schema["EventItem"];
export type EventPageResponse = Schema["EventPageResponse"];
export type DamageEventView = Schema["DamageEventView"];
export type EventDetailResponse = Schema["EventDetailResponse"];
export type FrameStateResponse = Schema["FrameStateResponse"];
export type FrameCharacterState = Schema["FrameCharacterState"];

/** 事件分页（帧状态与伤害事件详情的 ordinal 入口）。 */
export async function getResultEvents(
  sessionId: string,
  options: {
    frameMin?: number;
    frameMax?: number;
    eventType?: string;
    offset?: number;
    limit?: number;
  } = {},
): Promise<EventPageResponse> {
  const params = new URLSearchParams();
  if (options.frameMin !== undefined) params.set("frame_min", String(options.frameMin));
  if (options.frameMax !== undefined) params.set("frame_max", String(options.frameMax));
  if (options.eventType !== undefined) params.set("event_type", options.eventType);
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  const query = params.toString();
  return request<EventPageResponse>(
    `/results/${encodeURIComponent(sessionId)}/events${query === "" ? "" : `?${query}`}`,
  );
}

/** 单条事件详情；DAMAGE_RESOLVED 携带规范化伤害视图。 */
export async function getResultEvent(
  sessionId: string,
  ordinal: number,
): Promise<EventDetailResponse> {
  return request<EventDetailResponse>(
    `/results/${encodeURIComponent(sessionId)}/events/${encodeURIComponent(String(ordinal))}`,
  );
}

/** 指定帧的帧末角色状态。 */
export async function getFrameState(
  sessionId: string,
  frame: number,
): Promise<FrameStateResponse> {
  return request<FrameStateResponse>(
    `/results/${encodeURIComponent(sessionId)}/frames/${encodeURIComponent(String(frame))}`,
  );
}

/** 执行分析查询计划，返回输出表集合（契约 v2）。 */
export async function executeAnalysisQuery(
  payload: ExecutePlanRequest,
): Promise<ExecutePlanResponse> {
  return request<ExecutePlanResponse>("/analysis/query", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 取数节点编辑器的可读 schema：表列、事件类型与载荷字段。 */
export async function getAnalysisSchema(): Promise<AnalysisSchemaResponse> {
  return request<AnalysisSchemaResponse>("/analysis/schema");
}


export async function searchAssets(
  assetType: "characters" | "weapons" | "artifact-sets",
  query = "",
  limit = 50,
  offset = 0,
  filters?: {
    element?: string | null;
    weapon_type?: string | null;
    rarity?: number | null;
    usable?: number | null;
  },
): Promise<AssetListResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) });
  if (filters?.element != null) { params.set("element", filters.element); }
  if (filters?.weapon_type != null) { params.set("weapon_type", filters.weapon_type); }
  if (filters?.rarity != null) { params.set("rarity", String(filters.rarity)); }
  if (filters?.usable != null) { params.set("usable", String(filters.usable)); }
  return request<AssetListResponse>(`/assets/${assetType}?${params.toString()}`);
}

export async function getAsset(
  assetType: "characters" | "weapons" | "artifact-sets",
  sourceId: string,
): Promise<AssetResponse> {
  return request<AssetResponse>(
    `/assets/${assetType}/${encodeURIComponent(sourceId)}`,
  );
}

/** 按完整 asset_key 批量解析资产显示名；缺失的键不返回。 */
export async function resolveAssets(keys: string[]): Promise<AssetListResponse> {
  return request<AssetListResponse>("/assets/resolve", {
    method: "POST",
    body: JSON.stringify({ keys }),
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const body = (await response.json().catch(() => null)) as
    | ErrorBody
    | T
    | null;
  if (!response.ok) {
    const errorBody = body as ErrorBody | null;
    throw new ApiError(
      errorBody?.code ?? "http_error",
      errorBody?.message ?? `HTTP ${response.status}`,
      errorBody?.details ?? [],
      response.status,
    );
  }
  return body as T;
}
