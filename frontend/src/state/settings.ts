import { getUiSettings, saveUiSettings } from "../api/client";

/**
 * 界面偏好设置：持久化在后端项目配置（config.toml 的 `ui` 节，见 UI API 契约
 * GET/PUT /api/v1/settings）；默认值在前端定义，后端缺节时回退默认。
 */
export interface AppSettings {
  /** 运行动画：构建阶段逐节点限速推进，保留最小执行时长（默认启用）。 */
  runAnimation: boolean;
  /** 工作区数据目录（config.toml 的 workspace 节）；只读展示，加载失败为 null。 */
  workspaceDataDir: string | null;
}

export function createAppSettings(): AppSettings {
  return { runAnimation: true, workspaceDataDir: null };
}

/** 把后端设置视图合并到默认值上；字段缺失或非法时回退默认。 */
export function coerceAppSettings(raw: unknown): AppSettings {
  const defaults = createAppSettings();
  if (typeof raw !== "object" || raw === null) {
    return defaults;
  }
  const record = raw as Record<string, unknown>;
  const workspace =
    typeof record.workspace === "object" && record.workspace !== null
      ? (record.workspace as Record<string, unknown>)
      : {};
  return {
    runAnimation:
      typeof record.run_animation === "boolean" ? record.run_animation : defaults.runAnimation,
    workspaceDataDir:
      typeof workspace.data_dir === "string" && workspace.data_dir !== ""
        ? workspace.data_dir
        : defaults.workspaceDataDir,
  };
}

export function toSettingsPayload(settings: AppSettings): { run_animation: boolean } {
  return { run_animation: settings.runAnimation };
}

/** 从后端读取设置；请求失败或工作区未初始化时回退默认值。 */
export async function loadAppSettingsFromApi(): Promise<AppSettings> {
  try {
    return coerceAppSettings(await getUiSettings());
  } catch {
    return createAppSettings();
  }
}

/** 保存设置到后端项目配置；失败时抛出，由调用方提示。 */
export async function saveAppSettingsToApi(settings: AppSettings): Promise<void> {
  await saveUiSettings(settings.runAnimation);
}
