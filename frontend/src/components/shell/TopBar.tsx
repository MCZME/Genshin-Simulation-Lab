export interface TopBarProps {
  name: string;
  dirty: boolean;
  saving: boolean;
  running: boolean;
  canRun: boolean;
  onRename: (name: string) => void;
  onSave: () => void;
  onRun: () => void;
}

export function TopBar({
  name,
  dirty,
  saving,
  running,
  canRun,
  onRename,
  onSave,
  onRun,
}: TopBarProps) {
  return (
    <header className="top-bar">
      <div className="top-bar-left">
        <span className="brand-mark">GSL</span>
        <input
          className="workflow-name"
          value={name}
          aria-label="工作流名称"
          onChange={(event) => onRename(event.target.value)}
        />
        {dirty && <span className="dirty-badge">未保存</span>}
      </div>
      <div className="top-bar-right">
        <button
          type="button"
          className="action-button"
          disabled={!dirty || saving || running}
          onClick={onSave}
        >
          {saving ? "保存中…" : "保存"}
        </button>
        <button
          type="button"
          className="action-button primary"
          disabled={running || !canRun}
          onClick={onRun}
        >
          {running ? "运行中…" : "全部运行"}
        </button>
      </div>
    </header>
  );
}
