import type { AppSettings } from "../../state/settings";

export interface SettingsModalProps {
  settings: AppSettings;
  onChange: (settings: AppSettings) => void;
  onClose: () => void;
}

/** 设置弹窗：居中模态、单列分组表单；修改立即生效，无保存/取消按钮。 */
export function SettingsModal({ settings, onChange, onClose }: SettingsModalProps) {
  return (
    <div
      className="settings-overlay"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="settings-modal" role="dialog" aria-label="设置">
        <div className="settings-header">
          <span className="settings-title">设置</span>
          <button
            type="button"
            className="icon-button"
            title="关闭设置"
            aria-label="关闭设置"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <div className="settings-group">
          <h3 className="settings-group-title">工作区</h3>
          <div className="settings-row">
            <span className="settings-row-label">数据目录</span>
            <span className="settings-value" title={settings.workspaceDataDir ?? undefined}>
              {settings.workspaceDataDir ?? "—"}
            </span>
          </div>
          <p className="settings-row-hint">来自项目配置 config.toml，只读；修改需编辑配置文件</p>
        </div>
        <div className="settings-group">
          <h3 className="settings-group-title">运行</h3>
          <label className="settings-row">
            <span className="settings-row-label">运行动画</span>
            <input
              type="checkbox"
              className="settings-toggle"
              checked={settings.runAnimation}
              onChange={(event) => onChange({ ...settings, runAnimation: event.target.checked })}
            />
          </label>
          <p className="settings-row-hint">
            构建阶段逐节点限速推进（每步至少 150ms），运行过程按节点顺序可见
          </p>
        </div>
      </div>
    </div>
  );
}
