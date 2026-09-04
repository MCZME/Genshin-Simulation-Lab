export interface AppState {
  workspaceInitialized: boolean;
  assetDbVersion: string;
  workflowId: string | null;
  workflowName: string;
}

const LAST_WORKFLOW_ID_KEY = "gsl.last-workflow-id";

export function createAppState(): AppState {
  return {
    workspaceInitialized: false,
    assetDbVersion: "",
    workflowId: null,
    workflowName: "未命名工作流",
  };
}

export function withWorkspace(
  state: AppState,
  workspace: { initialized: boolean; asset_db_version: string },
): AppState {
  return {
    ...state,
    workspaceInitialized: workspace.initialized,
    assetDbVersion: workspace.asset_db_version,
  };
}

export function withCurrentWorkflow(
  state: AppState,
  workflow: { id: string | null; name: string },
): AppState {
  return {
    ...state,
    workflowId: workflow.id,
    workflowName: workflow.name,
  };
}

export function rememberLastWorkflowId(workflowId: string | null): void {
  try {
    if (workflowId === null) {
      window.localStorage.removeItem(LAST_WORKFLOW_ID_KEY);
    } else {
      window.localStorage.setItem(LAST_WORKFLOW_ID_KEY, workflowId);
    }
  } catch {
    // localStorage 不可用（隐私模式等）时不阻断工作流切换
  }
}

export function readLastWorkflowId(): string | null {
  try {
    return window.localStorage.getItem(LAST_WORKFLOW_ID_KEY);
  } catch {
    return null;
  }
}
