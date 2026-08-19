import { useEffect, useState } from "react";
import { searchAssets } from "../../api/client";
import type { AssetResponse } from "../../api/client";

interface AssetPickerProps {
  assetType: "characters" | "weapons" | "artifact-sets";
  value: string;
  onChange: (assetKey: string) => void;
}

export function AssetPicker({ assetType, value, onChange }: AssetPickerProps) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<AssetResponse[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void searchAssets(assetType, query)
      .then((response) => {
        if (!cancelled) {
          setItems(response.items ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setItems([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [assetType, query]);

  const selected = items.find((item) => item.asset_key === value) ?? null;

  return (
    <div className="asset-picker">
      <button
        type="button"
        className="asset-trigger"
        onClick={() => setOpen((current) => !current)}
      >
        <span className="asset-name">{selected?.name ?? (value !== "" ? value : "选择资产")}</span>
        {selected !== null && !selected.usable && (
          <span className="asset-status">{selected.status ?? "不可用"}</span>
        )}
      </button>
      {open && (
        <div className="asset-dropdown">
          <input
            className="field"
            type="text"
            value={query}
            placeholder="搜索资产"
            autoFocus
            onChange={(event) => setQuery(event.target.value)}
          />
          <ul className="asset-list">
            {items.map((item) => (
              <li key={item.asset_key}>
                <button
                  type="button"
                  className="asset-option"
                  onClick={() => {
                    onChange(item.asset_key);
                    setOpen(false);
                  }}
                >
                  <span>{item.name}</span>
                  {!item.usable && (
                    <span className="asset-status">{item.status ?? "不可用"}</span>
                  )}
                </button>
              </li>
            ))}
            {items.length === 0 && <li className="asset-empty">没有匹配资产</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
