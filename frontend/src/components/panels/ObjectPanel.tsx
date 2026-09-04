import { getNodeKindSpec } from "../../workflow/registry";
import {
  ANALYSIS_DETAIL_KINDS,
  ANALYSIS_DISPLAY_CONFIG_KINDS,
  ANALYSIS_FETCH_KINDS,
  ANALYSIS_OPERATOR_KINDS,
  ANALYSIS_VIEW_KINDS,
  CONFIG_INPUT_KINDS,
  CONFIG_RUN_SETTING_KINDS,
  CONFIG_TARGET_KINDS,
  CONFIG_TEAM_KINDS,
  CONFIG_VARIANT_KINDS,
  nodeKindColor,
} from "../nodes/registry";

export interface ObjectPanelProps {
  onDragStart: (kind: string) => void;
  onCollapse: () => void;
}

export function ObjectPanel({ onDragStart, onCollapse }: ObjectPanelProps) {
  return (
    <aside className="tool-panel">
      <div className="tool-panel-header">
        <span className="tool-panel-title">节点库</span>
        <button
          type="button"
          className="tool-panel-collapse"
          title="收起面板"
          aria-label="收起节点面板"
          onClick={onCollapse}
        >
          ‹
        </button>
      </div>
      <div className="panel-section">
        <h2 className="panel-title">区域</h2>
        <DraggableObject
          kind="region"
          label="配置区域"
          color={nodeKindColor("region")}
          onDragStart={onDragStart}
        />
        <DraggableObject
          kind="analysis_region"
          label="分析区域"
          color={nodeKindColor("analysis_region")}
          onDragStart={onDragStart}
        />
      </div>
      <div className="panel-section">
        <h2 className="panel-title">配置节点</h2>
        <h3 className="panel-subtitle">运行设置</h3>
        {CONFIG_RUN_SETTING_KINDS.map((kind) => (
          <PanelItem key={kind} kind={kind} onDragStart={onDragStart} />
        ))}
        <h3 className="panel-subtitle">队伍配置</h3>
        {CONFIG_TEAM_KINDS.map((kind) => (
          <PanelItem key={kind} kind={kind} onDragStart={onDragStart} />
        ))}
        <h3 className="panel-subtitle">目标配置</h3>
        {CONFIG_TARGET_KINDS.map((kind) => (
          <PanelItem key={kind} kind={kind} onDragStart={onDragStart} />
        ))}
        <h3 className="panel-subtitle">操作输入</h3>
        {CONFIG_INPUT_KINDS.map((kind) => (
          <PanelItem key={kind} kind={kind} onDragStart={onDragStart} />
        ))}
        <h3 className="panel-subtitle">变体扫描</h3>
        {CONFIG_VARIANT_KINDS.map((kind) => (
          <PanelItem key={kind} kind={kind} onDragStart={onDragStart} />
        ))}
      </div>
      <div className="panel-section">
        <h2 className="panel-title">画布节点</h2>
        <DraggableObject
          kind="simulation"
          label="模拟节点"
          color={nodeKindColor("simulation")}
          onDragStart={onDragStart}
        />
        <DraggableObject
          kind="data_provider"
          label="数据提供"
          color={nodeKindColor("data_provider")}
          onDragStart={onDragStart}
        />
      </div>
      <div className="panel-section">
        <h2 className="panel-title">分析节点</h2>
        <h3 className="panel-subtitle">数据获取</h3>
        {ANALYSIS_FETCH_KINDS.map((kind) => (
          <PanelItem key={kind} kind={kind} onDragStart={onDragStart} />
        ))}
        <h3 className="panel-subtitle">数据加工</h3>
        {ANALYSIS_OPERATOR_KINDS.map((kind) => (
          <PanelItem key={kind} kind={kind} onDragStart={onDragStart} />
        ))}
        <h3 className="panel-subtitle">展示配置</h3>
        {ANALYSIS_DISPLAY_CONFIG_KINDS.map((kind) => (
          <PanelItem key={kind} kind={kind} onDragStart={onDragStart} />
        ))}
        <h3 className="panel-subtitle">展示视图</h3>
        {ANALYSIS_VIEW_KINDS.map((kind) => (
          <PanelItem key={kind} kind={kind} onDragStart={onDragStart} />
        ))}
        <h3 className="panel-subtitle">单项详情</h3>
        {ANALYSIS_DETAIL_KINDS.map((kind) => (
          <PanelItem key={kind} kind={kind} onDragStart={onDragStart} />
        ))}
      </div>
    </aside>
  );
}

function PanelItem({
  kind,
  onDragStart,
}: {
  kind: string;
  onDragStart: (kind: string) => void;
}) {
  return (
    <DraggableObject
      kind={kind}
      label={getNodeKindSpec(kind)?.displayName ?? kind}
      color={nodeKindColor(kind)}
      onDragStart={onDragStart}
    />
  );
}

function DraggableObject({
  kind,
  label,
  color,
  onDragStart,
}: {
  kind: string;
  label: string;
  color: string;
  onDragStart: (kind: string) => void;
}) {
  return (
    <div
      className="panel-action draggable"
      draggable
      title={`拖入画布创建${label}`}
      onDragStart={(event) => {
        event.dataTransfer.setData("application/x-workflow-object", kind);
        event.dataTransfer.effectAllowed = "copy";
        onDragStart(kind);
      }}
      onDragEnd={() => onDragStart("")}
    >
      <span className="node-dot" style={{ background: color }} />
      <span className="panel-action-label">{label}</span>
    </div>
  );
}
