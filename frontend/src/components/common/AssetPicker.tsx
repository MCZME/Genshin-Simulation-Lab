import { useEffect, useRef, useState } from "react";
import { getAsset, searchAssets } from "../../api/client";
import type { AssetResponse } from "../../api/client";
import { ELEMENT_COLORS, ELEMENT_LABELS } from "../../theme/elements";

interface AssetPickerProps {
  assetType: "characters" | "weapons" | "artifact-sets";
  value: string;
  onChange: (assetKey: string) => void;
}

type AssetFilters = {
  query: string;
  elementFilter: string | null;
  weaponTypeFilter: string | null;
  rarityFilter: number | null;
  usableFilter: number | null;
};

const WEAPON_LABELS: Record<string, string> = {
  bow: "弓",
  catalyst: "法器",
  claymore: "双手剑",
  polearm: "长柄",
  sword: "单手剑",
};

/** 资产详情缓存：同一资产在多个节点中选择时不重复请求；失败结果也缓存为 null。 */
const detailCache = new Map<string, Promise<AssetResponse | null>>();

function sourceIdFromAssetKey(assetKey: string): string | null {
  const index = assetKey.indexOf(":");
  if (index === -1 || index === assetKey.length - 1) {
    return null;
  }
  return assetKey.slice(index + 1);
}

/** 解析单个资产详情；无效引用或请求失败返回 null（触发按钮回退显示 asset_key）。 */
function fetchAssetDetail(
  assetType: "characters" | "weapons" | "artifact-sets",
  assetKey: string,
): Promise<AssetResponse | null> {
  const cached = detailCache.get(assetKey);
  if (cached !== undefined) {
    return cached;
  }
  const sourceId = sourceIdFromAssetKey(assetKey);
  const promise =
    sourceId === null
      ? Promise.resolve(null)
      : getAsset(assetType, sourceId).catch(() => null);
  detailCache.set(assetKey, promise);
  return promise;
}

export function AssetPicker({ assetType, value, onChange }: AssetPickerProps) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<AssetResponse[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [elementFilter, setElementFilter] = useState<string | null>(null);
  const [weaponTypeFilter, setWeaponTypeFilter] = useState<string | null>(null);
  const [rarityFilter, setRarityFilter] = useState<number | null>(null);
  const [usableFilter, setUsableFilter] = useState<number | null>(null);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  /** 当前列表页未包含的选中资产，按详情端点回补显示。 */
  const [fallback, setFallback] = useState<AssetResponse | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  function updateCriteria(next: Partial<AssetFilters>) {
    if (next.query !== undefined) {
      setQuery(next.query);
    }
    if (next.elementFilter !== undefined) {
      setElementFilter(next.elementFilter);
    }
    if (next.weaponTypeFilter !== undefined) {
      setWeaponTypeFilter(next.weaponTypeFilter);
    }
    if (next.rarityFilter !== undefined) {
      setRarityFilter(next.rarityFilter);
    }
    if (next.usableFilter !== undefined) {
      setUsableFilter(next.usableFilter);
    }
    setOffset(0);
    setHasMore(true);
  }

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (offset === 0) {
        setLoading(true);
      } else {
        setLoadingMore(true);
      }
      void searchAssets(assetType, query, 50, offset, { element: elementFilter, weapon_type: weaponTypeFilter, rarity: rarityFilter, usable: usableFilter })
        .then((response) => {
          if (!cancelled) {
            const next = response.items ?? [];
            if (offset === 0) {
              setItems(next);
              setActiveIndex(0);
              setLoading(false);
            } else {
              setItems((prev) => [...prev, ...next]);
              setLoadingMore(false);
            }
            setHasMore(next.length >= 50);
          }
        })
        .catch(() => {
          if (!cancelled) {
            if (offset === 0) {
              setItems([]);
              setLoading(false);
            } else {
              setLoadingMore(false);
            }
          }
        });
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [assetType, query, offset, elementFilter, weaponTypeFilter, rarityFilter, usableFilter]);

  // 选中资产不在当前列表页（初始仅 50 条）时，按详情端点解析名称与元数据；
  // 旧值残留由 selected 的派生校验挡掉，不在 effect 里同步清状态。
  useEffect(() => {
    if (value === "") {
      return;
    }
    let cancelled = false;
    void fetchAssetDetail(assetType, value).then((asset) => {
      if (!cancelled && asset !== null) {
        setFallback(asset);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [assetType, value]);

  useEffect(() => {
    if (!open) {
      return;
    }
    function handleMouseDown(event: MouseEvent) {
      if (
        rootRef.current !== null &&
        !rootRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, [open]);

  const selectedFromList = items.find((item) => item.asset_key === value) ?? null;
  const selected =
    selectedFromList ?? (fallback !== null && fallback.asset_key === value ? fallback : null);
  const elementColor =
    assetType === "characters" && selected !== null && selected.element != null
      ? (ELEMENT_COLORS[selected.element] ?? null)
      : null;
  const filteredItems = items.filter((item) => {
    if (elementFilter !== null && item.element !== elementFilter) {
      return false;
    }
    if (weaponTypeFilter !== null && item.weapon_type !== weaponTypeFilter) {
      return false;
    }
    if (rarityFilter !== null && item.rarity !== rarityFilter) {
      return false;
    }
    if (usableFilter !== null && item.usable !== (usableFilter === 1)) {
      return false;
    }
    return true;
  });

  function select(item: AssetResponse) {
    onChange(item.asset_key);
    setOpen(false);
    updateCriteria({
      query: "",
      elementFilter: null,
      weaponTypeFilter: null,
      rarityFilter: null,
      usableFilter: null,
    });
  }

  function toggleOpen() {
    if (!open) {
      setActiveIndex(
        Math.max(
          0,
          items.findIndex((item) => item.asset_key === value),
        ),
      );
    }
    setOpen((current) => !current);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) =>
        Math.min(current + 1, Math.max(filteredItems.length - 1, 0)),
      );
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const item = filteredItems[activeIndex];
      if (item !== undefined) {
        select(item);
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
    }
  }

  function handleListScroll() {
    const el = listRef.current;
    if (el === null || loadingMore || !hasMore || loading) {
      return;
    }
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 100) {
      setOffset((prev) => prev + 50);
    }
  }

  return (
    <div
      className={`asset-picker ${open ? "dropdown-open" : ""}`}
      ref={rootRef}
    >
      <button
        type="button"
        className="asset-trigger"
        title={selected?.status ?? undefined}
        style={
          elementColor !== null
            ? {
                borderColor: elementColor,
                boxShadow: `inset 3px 0 0 ${elementColor}`,
              }
            : undefined
        }
        onClick={toggleOpen}
      >
        {selected !== null && selected.rarity != null && (
          <span
            className="asset-rarity-badge"
            style={
              elementColor !== null ? { background: elementColor } : undefined
            }
          >
            ★{selected.rarity}
          </span>
        )}
        {selected !== null && !selected.usable && (
          <span className="asset-status-badge">{selected.status ?? "不可用"}</span>
        )}
        <span className="asset-trigger-main">
          <span className="asset-name">
            {selected?.name ?? (value !== "" ? value : "选择资产")}
          </span>
          {selected !== null && (
            <span className="asset-trigger-meta">
              {assetType === "weapons" && selected.weapon_type != null && (
                <span className="asset-tag">
                  {WEAPON_LABELS[selected.weapon_type] ?? selected.weapon_type}
                </span>
              )}
            </span>
          )}
        </span>
        <span className="asset-caret">▾</span>
      </button>
      {open && (
        <div className="asset-dropdown nowheel">
          <input
            className="field nowheel"
            type="text"
            value={query}
            placeholder="搜索资产"
            autoFocus
            onChange={(event) => updateCriteria({ query: event.target.value })}
            onKeyDown={handleKeyDown}
          />
          {assetType !== "artifact-sets" && (
            <div className="asset-filters">
              {assetType === "characters" && (
                <FilterRow
                  label="元素"
                  options={Object.entries(ELEMENT_LABELS).map(([value, label]) => ({
                    value,
                    label,
                  }))}
                  value={elementFilter}
                  onSelect={(value) => {
                    updateCriteria({ elementFilter: value });
                    setActiveIndex(0);
                  }}
                />
              )}
              {(assetType === "characters" || assetType === "weapons") && (
                <FilterRow
                  label="类型"
                  options={Object.entries(WEAPON_LABELS).map(([value, label]) => ({
                    value,
                    label,
                  }))}
                  value={weaponTypeFilter}
                  onSelect={(value) => {
                    updateCriteria({ weaponTypeFilter: value });
                    setActiveIndex(0);
                  }}
                />
              )}
              <FilterRow
                label="星级"
                options={[5, 4, 3, 2, 1].map((value) => ({
                  value,
                  label: `${value}★`,
                }))}
                value={rarityFilter}
                onSelect={(value) => {
                  updateCriteria({ rarityFilter: value });
                  setActiveIndex(0);
                }}
              />
              <FilterRow
                label="状态"
                options={[
                  { value: 1, label: "已实现" },
                  { value: 0, label: "未实现" },
                ]}
                value={usableFilter}
                onSelect={(value) => {
                  updateCriteria({ usableFilter: value });
                  setActiveIndex(0);
                }}
              />
            </div>
          )}
          <ul className="asset-list" ref={listRef} onScroll={handleListScroll}>
            {loading ? (
              <li className="asset-empty">加载中…</li>
            ) : filteredItems.length === 0 ? (
              <li className="asset-empty">没有匹配资产</li>
            ) : (
              filteredItems.map((item, index) => (
                <li key={item.asset_key}>
                  <button
                    type="button"
                    className={`asset-option ${
                      index === activeIndex ? "active" : ""
                    }`}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => select(item)}
                  >
                    <span className="asset-option-main">
                      <span className="asset-option-title">
                        <span className="asset-name">{item.name}</span>
                        {item.rarity != null && (
                          <span className="asset-rarity">
                            {"★".repeat(item.rarity)}
                          </span>
                        )}
                        {!item.usable && (
                          <span className="asset-status">
                            {item.status ?? "不可用"}
                          </span>
                        )}
                      </span>
                      {(item.element != null || item.weapon_type != null) && (
                        <span className="asset-option-tags">
                          {item.element != null && (
                            <span className="asset-tag">
                              {ELEMENT_LABELS[item.element] ?? item.element}
                            </span>
                          )}
                          {item.weapon_type != null && (
                            <span className="asset-tag">
                              {WEAPON_LABELS[item.weapon_type] ??
                                item.weapon_type}
                            </span>
                          )}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              ))
            )}
            {loadingMore && <li className="asset-empty">加载更多…</li>}
            {!hasMore && !loadingMore && filteredItems.length > 0 && (
              <li className="asset-empty">没有更多资产</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

function FilterRow<T extends string | number>({
  label,
  options,
  value,
  onSelect,
}: {
  label: string;
  options: Array<{ value: T; label: string }>;
  value: T | null;
  onSelect: (value: T | null) => void;
}) {
  return (
    <div className="asset-filter-row">
      <span className="asset-filter-label">{label}</span>
      <button
        type="button"
        className={`asset-filter-chip ${value === null ? "active" : ""}`}
        aria-label={`${label}：全部`}
        onClick={() => onSelect(null)}
      >
        全部
      </button>
      {options.map((option) => (
        <button
          key={String(option.value)}
          type="button"
          className={`asset-filter-chip ${
            value === option.value ? "active" : ""
          }`}
          aria-label={`${label}：${option.label}`}
          onClick={() => onSelect(value === option.value ? null : option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
