import { getNodeKindSpec } from "../../workflow/registry";
import { CONFIG_NODE_KINDS, nodeKindColor } from "../nodes/registry";

export interface ObjectPanelProps {
  onAddNode: (kind: string) => void;
  onAddRegion: () => void;
  onLoadExample: () => void;
}

export function ObjectPanel({ onAddNode, onAddRegion, onLoadExample }: ObjectPanelProps) {
  return (
    <aside className="tool-panel">
      <div className="panel-section">
        <h2 className="panel-title">工作流</h2>
        <button type="button" className="panel-action" onClick={onLoadExample}>
          载入示例链路
        </button>
      </div>
      <div className="panel-section">
        <h2 className="panel-title">区域</h2>
        <button type="button" className="panel-action" onClick={onAddRegion}>
          + 配置区域
        </button>
      </div>
      <div className="panel-section">
        <h2 className="panel-title">配置节点</h2>
        {CONFIG_NODE_KINDS.map((kind) => (
          <button
            type="button"
            key={kind}
            className="panel-action"
            onClick={() => onAddNode(kind)}
          >
            <span className="node-dot" style={{ background: nodeKindColor(kind) }} />
            {getNodeKindSpec(kind)?.displayName ?? kind}
          </button>
        ))}
      </div>
      <div className="panel-section">
        <h2 className="panel-title">桥</h2>
        <button type="button" className="panel-action" onClick={() => onAddNode("simulation")}>
          <span className="node-dot" style={{ background: nodeKindColor("simulation") }} />
          模拟桥
        </button>
      </div>
    </aside>
  );
}
