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

/** 历史运行列表（结果库浏览器，决策 2.37）；后端按 created_at 倒序返回。 */
export async function listResults(
  options: { limit?: number; offset?: number; state?: "completed" | "failed" | "cancelled" } = {},
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
  const query = params.toString();
  return request<RunListResponse>(`/results${query === "" ? "" : `?${query}`}`);
}

/** 运行详情概要（不含事件流、指标数值，决策 2.37）。 */
export async function getResultDetail(sessionId: string): Promise<RunDetailResponse> {
  return request<RunDetailResponse>(`/results/${encodeURIComponent(sessionId)}`);
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
