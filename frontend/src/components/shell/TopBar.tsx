import { useEffect, useRef, useState } from "react";
import type { WorkflowListItem } from "../../api/client";

export interface TopBarProps {
  name: string;
  dirty: boolean;
  saving: boolean;
  running: boolean;
  canRun: boolean;
  canUndo: boolean;
  canRedo: boolean;
  workflows: WorkflowListItem[];
  workflowId: string | null;
  onRename: (name: string) => void;
  onUndo: () => void;
  onRedo: () => void;
  onSave: () => void;
  onRun: () => void;
  /** 运行期间双击运行按钮触发整次取消（决策 2.38）。 */
  onCancelRun: () => void;
  onCreate: () => void;
  onSaveAndCreate: () => void;
  onSwitch: (workflowId: string) => void;
  onSaveAndSwitch: (workflowId: string) => void;
  onDelete: (workflowId: string) => void;
  onRenameWorkflow: (workflowId: string, name: string) => void;
}

type PendingAction = { kind: "switch"; workflowId: string } | { kind: "create" };

export function TopBar({
  name,
  dirty,
  saving,
  running,
  canRun,
  canUndo,
  canRedo,
  workflows,
  workflowId,
  onRename,
  onUndo,
  onRedo,
  onSave,
  onRun,
  onCancelRun,
  onCreate,
  onSaveAndCreate,
  onSwitch,
  onSaveAndSwitch,
  onDelete,
  onRenameWorkflow,
}: TopBarProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    function handleMouseDown(event: MouseEvent) {
      if (
        rootRef.current !== null &&
        !rootRef.current.contains(event.target as Node)
      ) {
        closeMenu();
      }
    }
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") {
        return;
      }
      if (editingId !== null) {
        setEditingId(null);
        return;
      }
      if (deletingId !== null) {
        setDeletingId(null);
        return;
      }
      if (pending !== null) {
        setPending(null);
        return;
      }
      closeMenu();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [menuOpen, editingId, deletingId, pending]);

  function closeMenu() {
    setMenuOpen(false);
    setPending(null);
    setEditingId(null);
    setDeletingId(null);
  }

  function handleSelectWorkflow(targetId: string) {
    if (saving || running) {
      return;
    }
    if (targetId === workflowId) {
      closeMenu();
      return;
    }
    if (dirty) {
      setPending({ kind: "switch", workflowId: targetId });
      return;
    }
    onSwitch(targetId);
    closeMenu();
  }

  function handleCreate() {
    if (saving || running) {
      return;
    }
    if (dirty) {
      setPending({ kind: "create" });
      return;
    }
    onCreate();
    closeMenu();
  }

  function handleSaveAndContinue() {
    if (saving || running || pending === null) {
      return;
    }
    if (pending.kind === "switch") {
      onSaveAndSwitch(pending.workflowId);
    } else {
      onSaveAndCreate();
    }
    closeMenu();
  }

  function handleDiscardAndContinue() {
    if (saving || running || pending === null) {
      return;
    }
    if (pending.kind === "switch") {
      onSwitch(pending.workflowId);
    } else {
      onCreate();
    }
    closeMenu();
  }

  function startRename(item: WorkflowListItem) {
    if (saving || running) {
      return;
    }
    setDeletingId(null);
    setEditingId(item.id);
    setEditingName(item.name);
  }

  function commitRename() {
    if (editingId === null) {
      return;
    }
    const nextName = editingName.trim();
    if (nextName !== "") {
      if (editingId === workflowId) {
        onRename(nextName);
      } else {
        onRenameWorkflow(editingId, nextName);
      }
    }
    setEditingId(null);
  }

  function confirmDelete(item: WorkflowListItem) {
    if (saving || running) {
      return;
    }
    onDelete(item.id);
    closeMenu();
  }

  return (
    <header className="top-bar">
      <div className="top-bar-left">
        <span className="brand-mark">GSL</span>
        <div className="workflow-switcher" ref={rootRef}>
          <input
            className="workflow-name"
            value={name}
            aria-label="工作流名称"
            onChange={(event) => onRename(event.target.value)}
          />
          <button
            type="button"
            className="workflow-switcher-toggle"
            title="切换工作流"
            aria-label="切换工作流"
            aria-expanded={menuOpen}
            disabled={saving || running}
            onClick={() => {
              setMenuOpen((open) => !open);
              setPending(null);
              setEditingId(null);
              setDeletingId(null);
            }}
          >
            ▾
          </button>
          {menuOpen && (
            <div className="workflow-menu">
              {pending !== null ? (
                <div className="workflow-menu-confirm">
                  <p className="workflow-menu-confirm-title">
                    当前工作流有未保存改动
                  </p>
                  <div className="workflow-menu-confirm-actions">
                    <button
                      type="button"
                      className="action-button primary"
                      onClick={handleSaveAndContinue}
                    >
                      保存并{pending.kind === "switch" ? "切换" : "新建"}
                    </button>
                    <button
                      type="button"
                      className="action-button"
                      onClick={handleDiscardAndContinue}
                    >
                      不保存{pending.kind === "switch" ? "切换" : "新建"}
                    </button>
                    <button
                      type="button"
                      className="action-button"
                      onClick={() => setPending(null)}
                    >
                      取消
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="workflow-menu-header">工作流</div>
                  <ul className="workflow-menu-list">
                    {workflows.map((item) => (
                      <li
                        key={item.id}
                        className={`workflow-menu-item ${
                          item.id === workflowId ? "active" : ""
                        }`}
                      >
                        {editingId === item.id ? (
                          <input
                            autoFocus
                            className="workflow-menu-rename-input"
                            value={editingName}
                            aria-label="重命名工作流"
                            onChange={(event) => setEditingName(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") {
                                event.preventDefault();
                                commitRename();
                              }
                              if (event.key === "Escape") {
                                event.preventDefault();
                                setEditingId(null);
                              }
                            }}
                            onBlur={commitRename}
                          />
                        ) : deletingId === item.id ? (
                          <div className="workflow-menu-delete-confirm">
                            <span className="workflow-menu-delete-text">
                              删除「{item.name}」？
                            </span>
                            <button
                              type="button"
                              className="action-button danger"
                              onClick={() => confirmDelete(item)}
                            >
                              删除
                            </button>
                            <button
                              type="button"
                              className="action-button"
                              onClick={() => setDeletingId(null)}
                            >
                              取消
                            </button>
                          </div>
                        ) : (
                          <>
                            <button
                              type="button"
                              className="workflow-menu-item-main"
                              disabled={saving || running}
                              onClick={() => handleSelectWorkflow(item.id)}
                            >
                              <span className="workflow-menu-item-name">
                                {item.name}
                              </span>
                              <span className="workflow-menu-item-date">
                                {formatUpdatedAt(item.updated_at)}
                              </span>
                              {item.id === workflowId && (
                                <span className="workflow-menu-item-check">✓</span>
                              )}
                            </button>
                            <div className="workflow-menu-item-actions">
                              <button
                                type="button"
                                title="重命名"
                                aria-label={`重命名 ${item.name}`}
                                disabled={saving || running}
                                onClick={() => startRename(item)}
                              >
                                ✎
                              </button>
                              <button
                                type="button"
                                title="删除"
                                aria-label={`删除 ${item.name}`}
                                className="danger"
                                disabled={saving || running}
                                onClick={() => setDeletingId(item.id)}
                              >
                                🗑
                              </button>
                            </div>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                  <button
                    type="button"
                    className="workflow-menu-create"
                    disabled={saving || running}
                    onClick={handleCreate}
                  >
                    ＋ 新建工作流
                  </button>
                </>
              )}
            </div>
          )}
        </div>
        {dirty && <span className="dirty-badge">未保存</span>}
      </div>
      <div className="top-bar-right">
        <button
          type="button"
          className="action-button"
          title="撤销 (Ctrl+Z)"
          disabled={!canUndo || running}
          onClick={onUndo}
        >
          ↶
        </button>
        <button
          type="button"
          className="action-button"
          title="重做 (Ctrl+Shift+Z / Ctrl+Y)"
          disabled={!canRedo || running}
          onClick={onRedo}
        >
          ↷
        </button>
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
          className={`action-button primary ${running ? "running" : ""}`}
          disabled={!running && !canRun}
          title={running ? "双击取消整次运行" : undefined}
          onClick={() => {
            if (!running) {
              onRun();
            }
          }}
          onDoubleClick={() => {
            if (running) {
              onCancelRun();
            }
          }}
        >
          {running ? "运行中…" : "全部运行"}
        </button>
      </div>
    </header>
  );
}

function formatUpdatedAt(iso: string): string {
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) {
    return "";
  }
  const now = new Date();
  const today = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  const day = new Date(
    value.getFullYear(),
    value.getMonth(),
    value.getDate(),
  ).getTime();
  const diffDays = Math.round((today - day) / 86_400_000);
  if (diffDays <= 0) {
    return "今天";
  }
  if (diffDays === 1) {
    return "昨天";
  }
  if (diffDays < 7) {
    return `${diffDays} 天前`;
  }
  return `${value.getMonth() + 1}月${value.getDate()}日`;
}
