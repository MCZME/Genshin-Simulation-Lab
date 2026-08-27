/** 资产显示名解析：按 asset_key 批量请求并做模块级缓存，缺失键回退原文。 */

import { useEffect, useMemo, useState } from "react";
import { resolveAssets } from "../../api/client";

const nameCache = new Map<string, string>();
let inflight: Promise<void> | null = null;

export function useAssetNames(keys: string[]): Map<string, string> {
  const uniqueKeys = useMemo(
    () => Array.from(new Set(keys.filter((key) => key !== ""))),
    [keys],
  );
  const [names, setNames] = useState<Map<string, string>>(
    () => new Map(nameCache),
  );

  useEffect(() => {
    let cancelled = false;
    const missing = uniqueKeys.filter((key) => !nameCache.has(key));
    if (missing.length > 0 && inflight === null) {
      inflight = resolveAssets(missing)
        .then((response) => {
          for (const item of response.items ?? []) {
            nameCache.set(item.asset_key, item.name);
          }
        })
        .catch(() => {
          // 解析失败不阻断显示，单元格回退原始 asset_key。
        })
        .finally(() => {
          inflight = null;
        });
    }
    void (inflight ?? Promise.resolve()).then(() => {
      if (!cancelled) {
        setNames(new Map(nameCache));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [uniqueKeys]);

  return names;
}
