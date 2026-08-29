/** 单项详情节点内容区：消费 item（表格行/取单项结果）并渲染详情。 */

import { useEffect, useState } from "react";
import { getFrameState, getResultEvent } from "../../api/client";
import type { AnalysisNodeResult } from "../../workflow/analysis_runner";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { useAnalysisResults, useAnalysisSelection } from "../analysis_context";

type DetailKind = "frame_state" | "damage_detail" | "state_detail" | "attribute_detail";

export function isAnalysisDetailKind(kind: string): kind is DetailKind {
  return (
    kind === "frame_state" ||
    kind === "damage_detail" ||
    kind === "state_detail" ||
    kind === "attribute_detail"
  );
}

export function AnalysisDetailBody({
  node,
  definition,
}: {
  node: WorkflowNode;
  definition: WorkflowDefinition;
}) {
  const item = useUpstreamItem(node, definition);
  if (item === null) {
    return <div className="analysis-view-state">未连接 item 源（视图选择或取单项）</div>;
  }
  if (item === undefined) {
    return <div className="analysis-view-state">未选择（点击上游表格行）</div>;
  }
  if (!isRecord(item)) {
    return <div className="analysis-view-state">上游 item 不是数据对象</div>;
  }
  switch (node.kind) {
    case "damage_detail":
      return <DamageDetailView item={item} />;
    case "frame_state":
      return <FrameStateView item={item} />;
    default:
      return <KeyValueView title={node.kind === "state_detail" ? "状态实例" : "属性值"} data={item} />;
  }
}

/** 取单项节点卡：显示上游表第一行的内容预览。 */
export function SingleItemBody({ result }: { result: AnalysisNodeResult | undefined }) {
  if (result === undefined || result.status === "idle") {
    return <div className="analysis-view-state">未执行（连接数据后运行工作流）</div>;
  }
  if (result.status === "loading") {
    return <div className="analysis-view-state analysis-view-loading" role="status">加载中…</div>;
  }
  if (result.status === "error") {
    return <div className="analysis-view-state analysis-view-error">{result.error}</div>;
  }
  const item = result.item;
  if (item === undefined) {
    return <div className="analysis-view-state">无数据（上游为空）</div>;
  }
  if (isRecord(item)) {
    return <KeyValueView title="第一行" data={item} />;
  }
  return <pre className="detail-item-pre">{JSON.stringify(item, null, 2)}</pre>;
}

function useUpstreamItem(
  node: WorkflowNode,
  definition: WorkflowDefinition,
): unknown | null | undefined {
  const selections = useAnalysisSelection();
  const results = useAnalysisResults();
  const upstream = definition.edges
    .filter((edge) => edge.target_node_id === node.id && edge.target_port_id === "in")
    .map((edge) => definition.nodes.find((candidate) => candidate.id === edge.source_node_id))
    .find((candidate) => candidate !== undefined);
  if (upstream === undefined) {
    return null;
  }
  if (upstream.kind === "single") {
    const result = results?.get(upstream.id) as { item?: unknown } | undefined;
    return result?.item;
  }
  return selections?.selections.get(upstream.id);
}

function DamageDetailView({ item }: { item: Record<string, unknown> }) {
  const sessionId = readString(item, "session_id");
  const ordinal = readNumber(item, "ordinal");
  const key = sessionId !== null && ordinal !== null ? `${sessionId}#${ordinal}` : null;
  const loaded = useAsyncDetail(key, () => {
    return getResultEvent(sessionId as string, ordinal as number);
  });

  if (key === null) {
    return (
      <div className="analysis-view-state">item 缺少 session_id / ordinal 列（事件表取数行）</div>
    );
  }
  if (loaded === null || loaded.status === "loading") {
    return <div className="analysis-view-state analysis-view-loading" role="status">加载中…</div>;
  }
  if (loaded.status === "error") {
    return <div className="analysis-view-state analysis-view-error">{loaded.error}</div>;
  }
  const detail = loaded.data;
  const damage = detail.damage;
  return (
    <div className="detail-body">
      <div className="detail-section-title">
        伤害 #{detail.ordinal}（帧 {detail.frame}）
      </div>
      {damage === null || damage === undefined ? (
        <div className="analysis-view-state">该事件没有伤害摘要</div>
      ) : (
        <>
          <KeyValueView title="摘要" data={damage.summary} />
          <KeyValueView title="完整审计" data={damage.audit} />
        </>
      )}
    </div>
  );
}

function FrameStateView({ item }: { item: Record<string, unknown> }) {
  const sessionId = readString(item, "session_id");
  const frame = readNumber(item, "frame");
  const key = sessionId !== null && frame !== null ? `${sessionId}#${frame}` : null;
  const loaded = useAsyncDetail(key, () => {
    return getFrameState(sessionId as string, frame as number);
  });

  if (key === null) {
    return <div className="analysis-view-state">item 缺少 session_id / frame 列</div>;
  }
  if (loaded === null || loaded.status === "loading") {
    return <div className="analysis-view-state analysis-view-loading" role="status">加载中…</div>;
  }
  if (loaded.status === "error") {
    return <div className="analysis-view-state analysis-view-error">{loaded.error}</div>;
  }
  const frameState = loaded.data;
  return (
    <div className="detail-body">
      <div className="detail-section-title">
        帧 {frameState.frame}（{frameState.time_seconds.toFixed(2)} 秒） · 场上槽位{" "}
        {frameState.team.active_slot ?? "—"}
      </div>
      {frameState.characters.map((character) => (
        <KeyValueView
          key={character.combat_entity_id}
          title={`${character.slot}. ${character.character_key}${character.active ? "（场上）" : ""}`}
          data={{
            health: character.health,
            energy: character.energy,
            buffs: character.buffs?.length ?? 0,
            shields: character.shields?.length ?? 0,
            infusion: character.infusion?.length ?? 0,
            cooldowns: character.cooldowns?.length ?? 0,
            content_states: character.content_states?.length ?? 0,
            attributes: character.attributes,
          }}
        />
      ))}
    </div>
  );
}

/** 按稳定 key 拉取详情：异步回调内才 setState，key 变化前复用缓存。 */
function useAsyncDetail<T>(
  key: string | null,
  fetcher: (key: string) => Promise<T>,
): { status: "loading" } | { status: "error"; error: string } | { status: "ready"; data: T } | null {
  const [loaded, setLoaded] = useState<{ key: string; state: { status: "ready"; data: T } | { status: "error"; error: string } } | null>(
    null,
  );

  useEffect(() => {
    if (key === null) {
      return;
    }
    let cancelled = false;
    fetcher(key)
      .then((data) => {
        if (!cancelled) {
          setLoaded({ key, state: { status: "ready", data } });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoaded({
            key,
            state: { status: "error", error: error instanceof Error ? error.message : String(error) },
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetcher 由调用方按 key 稳定提供
  }, [key]);

  if (loaded === null || loaded.key !== key) {
    return null;
  }
  return loaded.state;
}

function KeyValueView({ title, data }: { title: string; data: unknown }) {
  if (data === null || data === undefined) {
    return (
      <div className="detail-body">
        <div className="detail-section-title">{title}</div>
        <div className="analysis-view-state">无数据</div>
      </div>
    );
  }
  return (
    <div className="detail-body">
      <div className="detail-section-title">{title}</div>
      <pre className="detail-item-pre">{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(item: Record<string, unknown>, key: string): string | null {
  const value = item[key];
  return typeof value === "string" && value !== "" ? value : null;
}

function readNumber(item: Record<string, unknown>, key: string): number | null {
  const value = item[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
