import { useState } from "react";

export interface IncomingOrderItem {
  edgeId: string;
  label: string;
  path: string | null;
}

export interface IncomingOrderGroup {
  portId: string;
  items: IncomingOrderItem[];
}

export interface InputOrderPopoverProps {
  targetNodeId: string;
  groups: IncomingOrderGroup[];
  onMoveEdgeOrder: (
    targetNodeId: string,
    targetPortId: string,
    edgeId: string,
    direction: "up" | "down",
  ) => void;
}

/** 目标端口的多条入线顺序；端口旁显示数量徽标，点击弹出画布内顺序列表。 */
export function InputOrderPopover({
  targetNodeId,
  groups,
  onMoveEdgeOrder,
}: InputOrderPopoverProps) {
  const visibleGroups = groups.filter((group) => group.items.length > 1);
  const [openPort, setOpenPort] = useState<string | null>(null);
  if (visibleGroups.length === 0) {
    return null;
  }

  return (
    <div className="order-controls">
      {visibleGroups.map((group) => (
        <div className="order-control" key={group.portId}>
          <button
            type="button"
            className={`order-badge ${openPort === group.portId ? "open" : ""}`}
            title={`${group.items.length} 条入线，点击调整顺序`}
            onClick={() => setOpenPort(openPort === group.portId ? null : group.portId)}
          >
            {group.items.length}
          </button>
          {openPort === group.portId && (
            <div className="order-popover">
              <ul className="order-list">
                {group.items.map((item, index) => (
                  <li className="order-row" key={item.edgeId}>
                    <div className="order-row-text">
                      <span className="order-index">{index + 1}</span>
                      <span className="order-label">{item.label}</span>
                      {overrideNote(group.items, item) !== null && (
                        <span className="order-note">{overrideNote(group.items, item)}</span>
                      )}
                    </div>
                    <div className="order-actions">
                      <button
                        type="button"
                        className="icon-button"
                        title="上移"
                        disabled={index === 0}
                        onClick={() => onMoveEdgeOrder(targetNodeId, group.portId, item.edgeId, "up")}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="icon-button"
                        title="下移"
                        disabled={index === group.items.length - 1}
                        onClick={() =>
                          onMoveEdgeOrder(targetNodeId, group.portId, item.edgeId, "down")
                        }
                      >
                        ↓
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function overrideNote(items: IncomingOrderItem[], item: IncomingOrderItem): string | null {
  if (item.path === null) {
    return null;
  }
  const samePath = items.filter((candidate) => candidate.path === item.path);
  if (samePath.length < 2) {
    return null;
  }
  let lastIndex = -1;
  items.forEach((candidate, index) => {
    if (candidate.path === item.path) {
      lastIndex = index;
    }
  });
  const currentIndex = items.indexOf(item);
  return currentIndex === lastIndex ? "覆盖前序同路径" : "将被后序覆盖";
}
