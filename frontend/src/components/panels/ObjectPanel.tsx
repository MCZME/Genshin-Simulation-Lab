import { getNodeKindSpec } from "../../workflow/registry";
import { CONFIG_NODE_KINDS, nodeKindColor } from "../nodes/registry";

export interface ObjectPanelProps {
  onDragStart: (kind: string) => void;
}

export function ObjectPanel({ onDragStart }: ObjectPanelProps) {
  return (
    <aside className="tool-panel">
      <div className="panel-section">
        <h2 className="panel-title">区域</h2>
        <DraggableObject
          kind="region"
          label="配置区域"
          color={nodeKindColor("region")}
          onDragStart={onDragStart}
        />
      </div>
      <div className="panel-section">
        <h2 className="panel-title">配置节点</h2>
        {CONFIG_NODE_KINDS.map((kind) => (
          <DraggableObject
            key={kind}
            kind={kind}
            label={getNodeKindSpec(kind)?.displayName ?? kind}
            color={nodeKindColor(kind)}
            onDragStart={onDragStart}
          />
        ))}
      </div>
      <div className="panel-section">
        <h2 className="panel-title">桥</h2>
        <DraggableObject
          kind="simulation"
          label="模拟桥"
          color={nodeKindColor("simulation")}
          onDragStart={onDragStart}
        />
      </div>
    </aside>
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
