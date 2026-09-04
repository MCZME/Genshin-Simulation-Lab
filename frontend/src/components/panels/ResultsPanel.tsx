import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  getResultDetail,
  listResults,
  type RunDetailResponse,
  type RunListItem,
} from "../../api/client";

const PAGE_SIZE = 50;

/** 契约口径：帧转秒固定 60 fps（UI API 契约 / 分析系统契约）。 */
const FRAMES_PER_SECOND = 60;

type ResultStateFilter = "all" | "completed" | "failed" | "cancelled";

const FILTERS: Array<{ value: ResultStateFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "completed", label: "成功" },
  { value: "failed", label: "失败" },
  { value: "cancelled", label: "已取消" },
];

const STATE_LABELS: Record<string, string> = {
  completed: "成功",
  failed: "失败",
  cancelled: "已取消",
};

export interface ResultsPanelProps {
  /** 定位请求（决策 2.37 运行联动）：刷新列表并打开该 session 的详情。 */
  focusSessionId: string | null;
  onFocusHandled: () => void;
  onCollapse: () => void;
}

interface DetailView {
  sessionId: string;
  loading: boolean;
  error: string | null;
  detail: RunDetailResponse | null;
}

/**
 * 结果面板（决策 2.37）：结果库历史浏览器。
 * 列表 + 概要详情两级；不展示任何指标数值，指标出口在模拟节点成员行。
 */
export function ResultsPanel({ focusSessionId, onFocusHandled, onCollapse }: ResultsPanelProps) {
  const [filter, setFilter] = useState<ResultStateFilter>("all");
  const [items, setItems] = useState<RunListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [detailView, setDetailView] = useState<DetailView | null>(null);
  /** 请求序号：只有最新请求可以落状态，避免快速切换筛选/记录时旧响应覆盖新响应。 */
  const listSeqRef = useRef(0);
  const detailSeqRef = useRef(0);

  const loadPage = useCallback(
    async (offset: number, append: boolean) => {
      const requestId = listSeqRef.current + 1;
      listSeqRef.current = requestId;
      setLoading(true);
      setError(null);
      try {
        const response = await listResults({
          state: filter === "all" ? undefined : filter,
          limit: PAGE_SIZE,
          offset,
        });
        if (listSeqRef.current !== requestId) {
          return;
        }
        setItems((current) => (append ? [...current, ...response.items] : response.items));
        setHasMore(response.items.length === PAGE_SIZE);
      } catch (cause) {
        if (listSeqRef.current !== requestId) {
          return;
        }
        setError(toMessage(cause));
        if (!append) {
          setItems([]);
          setHasMore(false);
        }
      } finally {
        if (listSeqRef.current === requestId) {
          setLoading(false);
        }
      }
    },
    [filter],
  );

  const openDetail = useCallback(async (sessionId: string) => {
    const requestId = detailSeqRef.current + 1;
    detailSeqRef.current = requestId;
    setDetailView({ sessionId, loading: true, error: null, detail: null });
    try {
      const detail = await getResultDetail(sessionId);
      if (detailSeqRef.current !== requestId) {
        return;
      }
      setDetailView({ sessionId, loading: false, error: null, detail });
    } catch (cause) {
      if (detailSeqRef.current !== requestId) {
        return;
      }
      setDetailView({ sessionId, loading: false, error: toMessage(cause), detail: null });
    }
  }, []);

  // 初次挂载与筛选变化时回到第一页（延迟到异步回调中更新状态，避免 effect 内联 setState）。
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadPage(0, false);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadPage]);

  // 定位请求：刷新列表并打开对应记录详情（决策 2.37）。
  useEffect(() => {
    if (focusSessionId === null) {
      return;
    }
    const sessionId = focusSessionId;
    const timer = window.setTimeout(() => {
      onFocusHandled();
      void loadPage(0, false);
      void openDetail(sessionId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [focusSessionId, loadPage, openDetail, onFocusHandled]);

  if (detailView !== null) {
    const detail = detailView.detail;
    return (
      <aside className="tool-panel results-panel">
        <div className="tool-panel-header">
          <button
            type="button"
            className="result-back"
            onClick={() => setDetailView(null)}
          >
            ‹ 返回
          </button>
          <button
            type="button"
            className="tool-panel-collapse"
            title="收起面板"
            aria-label="收起结果面板"
            onClick={onCollapse}
          >
            ‹
          </button>
        </div>
        {detailView.loading && <p className="result-hint">加载中…</p>}
        {detailView.error !== null && <p className="result-hint danger">{detailView.error}</p>}
        {detail !== null && (
          <div className="result-detail">
            <DetailRow label="名称" value={displayName(detail.name)} />
            <DetailRow
              label="状态"
              value={
                <span className={`status-badge status-${detail.state}`}>
                  {STATE_LABELS[detail.state] ?? detail.state}
                </span>
              }
            />
            <DetailRow label="结束原因" value={detail.summary?.stop_reason ?? "—"} />
            <DetailRow label="时长" value={formatDuration(detail)} />
            <DetailRow label="事件数" value={String(detail.event_count)} />
            <DetailRow label="创建时间" value={formatTime(detail.created_at)} />
            <DetailRow label="开始时间" value={formatTime(detail.started_at)} />
            <DetailRow label="结束时间" value={formatTime(detail.finished_at)} />
            <div className="result-detail-row">
              <span className="result-detail-label">session_id</span>
              <span className="result-detail-value result-session-id">{detail.session_id}</span>
            </div>
            <button
              type="button"
              className="text-button"
              title="复制 session_id"
              onClick={() => void copySessionId(detail.session_id)}
            >
              复制 session_id
            </button>
            {(detail.error_code !== null || detail.error_message !== null) && (
              <div className="result-detail-error">
                {detail.error_code !== null && <p>{detail.error_code}</p>}
                {detail.error_message !== null && <p>{detail.error_message}</p>}
              </div>
            )}
          </div>
        )}
      </aside>
    );
  }

  return (
    <aside className="tool-panel results-panel">
      <div className="tool-panel-header">
        <span className="tool-panel-title">运行结果</span>
        <span className="tool-panel-actions">
          <button
            type="button"
            className="tool-panel-collapse"
            title="刷新列表"
            aria-label="刷新结果列表"
            disabled={loading}
            onClick={() => void loadPage(0, false)}
          >
            ↻
          </button>
          <button
            type="button"
            className="tool-panel-collapse"
            title="收起面板"
            aria-label="收起结果面板"
            onClick={onCollapse}
          >
            ‹
          </button>
        </span>
      </div>
      <div className="panel-filters">
        {FILTERS.map((option) => (
          <button
            type="button"
            key={option.value}
            className={`filter-button ${filter === option.value ? "active" : ""}`}
            onClick={() => setFilter(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      <ul className="result-run-list">
        {items.map((item) => (
          <li key={item.session_id}>
            <button
              type="button"
              className="result-run-row"
              title={`session ${item.session_id}`}
              onClick={() => void openDetail(item.session_id)}
            >
              <span className="result-run-main">
                <span className="result-run-name">{displayName(item.name)}</span>
                <span className={`status-badge status-${item.state}`}>
                  {STATE_LABELS[item.state] ?? item.state}
                </span>
              </span>
              <span className="result-run-meta">
                {formatTime(item.created_at)} · {item.frames_run} 帧 · {item.event_count} 事件
              </span>
            </button>
          </li>
        ))}
      </ul>
      {loading && <p className="result-hint">加载中…</p>}
      {error !== null && <p className="result-hint danger">{error}</p>}
      {!loading && error === null && items.length === 0 && (
        <p className="result-hint">暂无运行结果</p>
      )}
      {hasMore && !loading && (
        <button
          type="button"
          className="result-more"
          onClick={() => void loadPage(items.length, true)}
        >
          加载更多
        </button>
      )}
    </aside>
  );
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="result-detail-row">
      <span className="result-detail-label">{label}</span>
      <span className="result-detail-value">{value}</span>
    </div>
  );
}

function displayName(name: string): string {
  return name === "" ? "未命名运行" : name;
}

function formatDuration(detail: RunDetailResponse): string {
  const frames = detail.summary?.frames_run;
  if (frames === undefined || frames === null) {
    return "—";
  }
  const seconds = frames / FRAMES_PER_SECOND;
  return `${seconds.toFixed(1)} 秒（${frames} 帧）`;
}

function formatTime(iso: string | null): string {
  if (iso === null || iso === "") {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function copySessionId(sessionId: string): Promise<void> {
  try {
    await navigator.clipboard?.writeText(sessionId);
  } catch {
    // 剪贴板不可用（本地 http 环境等）时静默跳过；session_id 本身仍可见可选中。
  }
}

function toMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
