/** 数据提供节点：节点卡摘要 + 画布内历史会话选择弹层（2026-08-25）。 */

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { listResults } from "../../api/client";
import type { RunListResponse, RunListItem } from "../../api/client";
import type { WorkflowNode } from "../../workflow/types";

const PROVIDER_PAGE_SIZE = 50;
const PICKER_WIDTH = 680;
const PICKER_HEIGHT = 520;
const FILTER_DEBOUNCE_MS = 250;

type ProviderState = "" | "completed" | "failed" | "cancelled";
type TimeRange = "all" | "today" | "7d" | "30d" | "custom";

interface ProviderFilters {
  q: string;
  state: ProviderState;
  timeRange: TimeRange;
  createdFrom: string;
  createdTo: string;
}

const DEFAULT_FILTERS: ProviderFilters = {
  q: "",
  state: "",
  timeRange: "all",
  createdFrom: "",
  createdTo: "",
};

const STATE_OPTIONS: { value: ProviderState; label: string }[] = [
  { value: "", label: "全部" },
  { value: "completed", label: "成功" },
  { value: "failed", label: "失败" },
  { value: "cancelled", label: "已取消" },
];

const TIME_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "all", label: "全部时间" },
  { value: "today", label: "今天" },
  { value: "7d", label: "最近 7 天" },
  { value: "30d", label: "最近 30 天" },
  { value: "custom", label: "自定义" },
];

interface EditorProps {
  node: WorkflowNode;
  onChange: (params: Record<string, unknown>) => void;
  fieldErrors?: Record<string, string[]>;
}

export function DataProviderEditor({ node, onChange }: EditorProps) {
  const selected = Array.isArray(node.params.session_ids)
    ? (node.params.session_ids as unknown[]).filter(
        (item): item is string => typeof item === "string",
      )
    : [];
  const selectedKey = selected.join(",");
  const [knownRuns, setKnownRuns] = useState<Map<string, RunListItem>>(new Map());
  const [existingIds, setExistingIds] = useState<Set<string> | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerPosition, setPickerPosition] = useState(computePopoverPosition(null));
  const anchorRef = useRef<HTMLButtonElement | null>(null);

  const staleCount =
    existingIds === null
      ? 0
      : selected.filter((sessionId) => !existingIds.has(sessionId)).length;

  useEffect(() => {
    if (selected.length === 0) {
      return;
    }
    let alive = true;
    (async () => {
      await Promise.resolve();
      if (!alive) {
        return;
      }
      try {
        const response = await listResults({ ids: selected });
        if (!alive) {
          return;
        }
        setKnownRuns(
          new Map(response.items.map((item) => [item.session_id, item])),
        );
        setExistingIds(new Set(response.items.map((item) => item.session_id)));
      } catch {
        if (!alive) {
          return;
        }
        setKnownRuns(new Map());
        setExistingIds(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [selectedKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const openPicker = () => {
    const rect = anchorRef.current?.getBoundingClientRect() ?? null;
    setPickerPosition(computePopoverPosition(rect));
    setPickerOpen(true);
  };

  const commit = (sessionIds: string[]) => {
    setPickerOpen(false);
    onChange({ session_ids: sessionIds });
  };

  const clearStale = () => {
    if (existingIds === null) {
      return;
    }
    onChange({
      session_ids: selected.filter((sessionId) => existingIds.has(sessionId)),
    });
  };

  return (
    <div className="analysis-editor data-provider-summary">
      <div className="data-provider-status">
        <span>已选 {selected.length} 场</span>
        {staleCount > 0 ? (
          <span className="data-provider-warning">{staleCount} 场已不存在</span>
        ) : null}
      </div>
      {selected.length > 0 ? (
        <ul className="data-provider-chips">
          {selected.slice(0, 5).map((sessionId) => {
            const run = knownRuns.get(sessionId);
            const stale =
              existingIds !== null && !existingIds.has(sessionId);
            return (
              <li
                key={sessionId}
                className={`data-provider-chip${stale ? " data-provider-chip-stale" : ""}`}
                title={run?.name}
              >
                {run?.name ?? (stale ? "已不存在" : "…")}
              </li>
            );
          })}
          {selected.length > 5 ? (
            <li className="data-provider-chip">+{selected.length - 5}</li>
          ) : null}
        </ul>
      ) : (
        <p className="data-provider-hint">未选择会话，分析结果将为空。</p>
      )}
      {staleCount > 0 ? (
        <button type="button" className="text-button danger" onClick={clearStale}>
          清除失效
        </button>
      ) : null}
      <button
        ref={anchorRef}
        type="button"
        className="action-button primary data-provider-open"
        onClick={openPicker}
      >
        选择会话
      </button>
      {pickerOpen ? (
        <DataProviderPicker
          initialSelected={selected}
          position={pickerPosition}
          onCommit={commit}
          onClose={() => setPickerOpen(false)}
        />
      ) : null}
    </div>
  );
}

function DataProviderPicker({
  initialSelected,
  position,
  onCommit,
  onClose,
}: {
  initialSelected: string[];
  position: { left: number; top: number; width: number; height: number };
  onCommit: (sessionIds: string[]) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<string[]>(initialSelected);
  const draftKey = draft.join(",");
  const [filters, setFilters] = useState<ProviderFilters>(DEFAULT_FILTERS);
  const debouncedFilters = useDebouncedValue(filters, FILTER_DEBOUNCE_MS);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [existingRuns, setExistingRuns] = useState<Map<string, RunListItem>>(
    new Map(),
  );
  const [existingIds, setExistingIds] = useState<Set<string> | null>(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    let alive = true;
    (async () => {
      await Promise.resolve();
      if (!alive) {
        return;
      }
      const seq = ++requestSeq.current;
      setLoading(true);
      setError(null);
      try {
        const response = await fetchPage(debouncedFilters, 0);
        if (!alive || seq !== requestSeq.current) {
          return;
        }
        setRuns(response.items);
        setHasMore(response.items.length === PROVIDER_PAGE_SIZE);
      } catch (err) {
        if (!alive || seq !== requestSeq.current) {
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
        setRuns([]);
      } finally {
        if (alive && seq === requestSeq.current) {
          setLoading(false);
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [debouncedFilters]);

  useEffect(() => {
    if (draft.length === 0) {
      return;
    }
    let alive = true;
    (async () => {
      await Promise.resolve();
      if (!alive) {
        return;
      }
      try {
        const response = await listResults({ ids: draft });
        if (!alive) {
          return;
        }
        const runsById = new Map(
          response.items.map((item) => [item.session_id, item]),
        );
        setExistingRuns(runsById);
        setExistingIds(new Set(runsById.keys()));
      } catch {
        if (!alive) {
          return;
        }
        setExistingRuns(new Map());
        setExistingIds(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [draftKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(
    async (offset: number, replace: boolean) => {
      const seq = ++requestSeq.current;
      setLoading(true);
      setError(null);
      try {
        const response = await fetchPage(debouncedFilters, offset);
        if (seq !== requestSeq.current) {
          return;
        }
        setRuns((previous) =>
          replace ? response.items : [...previous, ...response.items],
        );
        setHasMore(response.items.length === PROVIDER_PAGE_SIZE);
      } catch (err) {
        if (seq !== requestSeq.current) {
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
        if (replace) {
          setRuns([]);
        }
      } finally {
        if (seq === requestSeq.current) {
          setLoading(false);
        }
      }
    },
    [debouncedFilters],
  );

  const selectedSet = new Set(draft);
  const pageAllSelected =
    runs.length > 0 &&
    runs.every((run) => selectedSet.has(run.session_id));

  const toggle = (sessionId: string) => {
    setDraft((previous) =>
      previous.includes(sessionId)
        ? previous.filter((item) => item !== sessionId)
        : [...previous, sessionId],
    );
  };

  const togglePage = () => {
    setDraft((previous) => {
      const set = new Set(previous);
      const pageIds = runs.map((run) => run.session_id);
      if (pageAllSelected) {
        return previous.filter((item) => !pageIds.includes(item));
      }
      return [...previous, ...pageIds.filter((item) => !set.has(item))];
    });
  };

  const move = (index: number, direction: -1 | 1) => {
    setDraft((previous) => {
      const target = index + direction;
      if (target < 0 || target >= previous.length) {
        return previous;
      }
      const next = [...previous];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const remove = (sessionId: string) => {
    setDraft((previous) => previous.filter((item) => item !== sessionId));
  };

  const customTimeVisible = filters.timeRange === "custom";
  const defaultFiltersActive =
    filters.q.trim() === "" &&
    filters.state === "" &&
    filters.timeRange === "all";

  return createPortal(
    <>
      <div className="data-provider-backdrop" onMouseDown={onClose} />
      <section
        className="data-provider-popover"
        style={position}
        role="dialog"
        aria-modal="true"
        aria-label="选择历史会话"
      >
        <header className="data-provider-header">
          <span className="data-provider-title">选择历史会话</span>
          <button
            type="button"
            className="icon-button"
            title="关闭"
            aria-label="关闭"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="data-provider-toolbar">
          <input
            className="field data-provider-search"
            placeholder="按名称搜索…"
            value={filters.q}
            autoFocus
            onChange={(event) =>
              setFilters((previous) => ({ ...previous, q: event.target.value }))
            }
          />
          <div className="data-provider-segments" role="group" aria-label="状态筛选">
            {STATE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`data-provider-segment${filters.state === option.value ? " active" : ""}`}
                onClick={() =>
                  setFilters((previous) => ({
                    ...previous,
                    state: option.value,
                  }))
                }
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="data-provider-segments" role="group" aria-label="时间筛选">
            {TIME_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`data-provider-segment${filters.timeRange === option.value ? " active" : ""}`}
                onClick={() =>
                  setFilters((previous) => ({
                    ...previous,
                    timeRange: option.value,
                  }))
                }
              >
                {option.label}
              </button>
            ))}
          </div>
          {customTimeVisible ? (
            <div className="data-provider-time-custom">
              <input
                type="datetime-local"
                aria-label="开始时间"
                value={filters.createdFrom}
                onChange={(event) =>
                  setFilters((previous) => ({
                    ...previous,
                    createdFrom: event.target.value,
                  }))
                }
              />
              <span>至</span>
              <input
                type="datetime-local"
                aria-label="结束时间"
                value={filters.createdTo}
                onChange={(event) =>
                  setFilters((previous) => ({
                    ...previous,
                    createdTo: event.target.value,
                  }))
                }
              />
            </div>
          ) : null}
        </div>
        <div className="data-provider-body">
          <div className="data-provider-results">
            <div className="data-provider-results-header">
              <label className="data-provider-page-select">
                <input
                  type="checkbox"
                  checked={pageAllSelected}
                  onChange={togglePage}
                />
                本页全选
              </label>
              {hasMore ? (
                <span className="data-provider-page-hint">已加载 {runs.length} 条</span>
              ) : null}
            </div>
            {loading && runs.length === 0 ? (
              <div className="analysis-editor-empty">加载中…</div>
            ) : error !== null ? (
              <div className="analysis-editor-empty">
                {error}
                <button type="button" onClick={() => void load(0, true)}>
                  重试
                </button>
              </div>
            ) : runs.length === 0 ? (
              <div className="analysis-editor-empty">
                {defaultFiltersActive
                  ? "还没有历史运行，先去模拟节点跑一批。"
                  : "没有匹配的会话，调整筛选条件试试。"}
              </div>
            ) : (
              <ul className="data-provider-run-list">
                {runs.map((run) => (
                  <li key={run.session_id} className="data-provider-run-row">
                    <input
                      type="checkbox"
                      checked={selectedSet.has(run.session_id)}
                      onChange={() => toggle(run.session_id)}
                    />
                    <span className="data-provider-run-name" title={run.name}>
                      {run.name}
                    </span>
                    <span className={`status-badge status-${run.state}`}>
                      {STATE_LABELS[run.state] ?? run.state}
                    </span>
                    <span className="data-provider-run-time">
                      {formatRunTime(run.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {hasMore && !loading ? (
              <button
                type="button"
                className="data-provider-more"
                onClick={() => void load(runs.length, false)}
              >
                加载更多
              </button>
            ) : null}
          </div>
          <aside className="data-provider-selected">
            <div className="data-provider-selected-header">
              <span>已选 {draft.length} 场</span>
              {draft.length > 0 ? (
                <button
                  type="button"
                  className="text-button danger"
                  onClick={() => setDraft([])}
                >
                  清空
                </button>
              ) : null}
            </div>
            {draft.length === 0 ? (
              <p className="data-provider-selected-empty">
                还没有选择会话，列表顺序即输出顺序。
              </p>
            ) : (
              <ol className="data-provider-selected-list">
                {draft.map((sessionId, index) => {
                  const run = existingRuns.get(sessionId);
                  const stale =
                    existingIds !== null && !existingIds.has(sessionId);
                  return (
                    <li key={sessionId} className="data-provider-selected-row">
                      <span className="data-provider-selected-index">
                        {index + 1}
                      </span>
                      <span
                        className={`data-provider-selected-name${stale ? " stale" : ""}`}
                        title={run?.name}
                      >
                        {run?.name ?? (stale ? "已不存在" : "…")}
                      </span>
                      <span className="data-provider-selected-actions">
                        <button
                          type="button"
                          className="icon-button"
                          title="上移"
                          disabled={index === 0}
                          onClick={() => move(index, -1)}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          className="icon-button"
                          title="下移"
                          disabled={index === draft.length - 1}
                          onClick={() => move(index, 1)}
                        >
                          ↓
                        </button>
                        <button
                          type="button"
                          className="icon-button danger"
                          title="移除"
                          onClick={() => remove(sessionId)}
                        >
                          ×
                        </button>
                      </span>
                    </li>
                  );
                })}
              </ol>
            )}
          </aside>
        </div>
        <footer className="data-provider-footer">
          <button type="button" className="action-button" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="action-button primary"
            onClick={() => onCommit(draft)}
          >
            完成
          </button>
        </footer>
      </section>
    </>,
    document.body,
  );
}

const STATE_LABELS: Record<string, string> = {
  completed: "成功",
  failed: "失败",
  cancelled: "已取消",
};

function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function fetchPage(
  filters: ProviderFilters,
  offset: number,
): Promise<RunListResponse> {
  return listResults(filterOptions(filters, offset));
}

function filterOptions(
  filters: ProviderFilters,
  offset: number,
): {
  limit: number;
  offset: number;
  q?: string;
  state?: "completed" | "failed" | "cancelled";
  createdFrom?: string;
  createdTo?: string;
} {
  const now = new Date();
  let createdFrom: string | undefined;
  let createdTo: string | undefined;
  if (filters.timeRange === "today") {
    createdFrom = toUtcIso(
      new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString(),
    );
  } else if (filters.timeRange === "7d") {
    createdFrom = toUtcIso(
      new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString(),
    );
  } else if (filters.timeRange === "30d") {
    createdFrom = toUtcIso(
      new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString(),
    );
  } else if (filters.timeRange === "custom") {
    createdFrom = toUtcIso(filters.createdFrom);
    createdTo = toUtcIso(filters.createdTo);
  }
  return {
    limit: PROVIDER_PAGE_SIZE,
    offset,
    q: filters.q.trim() !== "" ? filters.q.trim() : undefined,
    state: filters.state === "" ? undefined : filters.state,
    createdFrom,
    createdTo,
  };
}

function toUtcIso(value: string): string | undefined {
  if (value === "") {
    return undefined;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return undefined;
  }
  return date.toISOString().slice(0, 19) + "+00:00";
}

function formatRunTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function computePopoverPosition(rect: DOMRect | null): {
  left: number;
  top: number;
  width: number;
  height: number;
} {
  const width = Math.min(PICKER_WIDTH, window.innerWidth - 16);
  const height = Math.min(PICKER_HEIGHT, window.innerHeight - 16);
  if (rect === null) {
    return { left: 8, top: 8, width, height };
  }
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
  const below = rect.bottom + 8;
  const above = rect.top - height - 8;
  const top =
    below + height > window.innerHeight && above >= 8 ? above : below;
  return { left, top, width, height };
}
