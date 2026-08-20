export interface AppState {
  workspaceInitialized: boolean;
  assetDbVersion: string;
  workflowId: string | null;
  workflowName: string;
}

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
