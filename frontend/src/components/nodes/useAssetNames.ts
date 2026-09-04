/** 资产显示名解析：按 asset_key 批量请求并做模块级缓存，缺失键回退原文。 */

import { useEffect, useMemo, useState } from "react";
import { resolveAssets } from "../../api/client";

const nameCache = new Map<string, string>();
// 请求在途期间新挂载实例的缺失键先入队，当前请求结束后统一续发，
// 避免并发挂载时只有第一个调用方发起请求。
const queuedKeys = new Set<string>();
const listeners = new Set<() => void>();
let inflight: Promise<void> | null = null;
let cacheVersion = 0;

function notifyListeners(): void {
  for (const listener of listeners) {
    listener();
  }
}

function startNextRequest(): void {
  if (inflight !== null || queuedKeys.size === 0) {
    return;
  }
  const keys = Array.from(queuedKeys).filter((key) => !nameCache.has(key));
  queuedKeys.clear();
  if (keys.length === 0) {
    return;
  }
  inflight = resolveAssets(keys)
    .then((response) => {
      let changed = false;
      for (const item of response.items ?? []) {
        if (nameCache.get(item.asset_key) !== item.name) {
          nameCache.set(item.asset_key, item.name);
          changed = true;
        }
      }
      if (changed) {
        cacheVersion += 1;
      }
    })
    .catch(() => {
      // 解析失败不阻断显示，单元格回退原始 asset_key。
    })
    .finally(() => {
      inflight = null;
      startNextRequest();
      notifyListeners();
    });
}

export function useAssetNames(keys: string[]): Map<string, string> {
  const uniqueKeys = useMemo(
    () => Array.from(new Set(keys.filter((key) => key !== ""))),
    [keys],
  );
  const [snapshot, setSnapshot] = useState(() => ({
    version: cacheVersion,
    names: new Map(nameCache),
  }));

  useEffect(() => {
    let active = true;
    const update = () => {
      if (!active) {
        return;
      }
      setSnapshot((current) => {
        if (current.version === cacheVersion) {
          return current;
        }
        return { version: cacheVersion, names: new Map(nameCache) };
      });
    };
    listeners.add(update);
    const missing = uniqueKeys.filter((key) => !nameCache.has(key));
    for (const key of missing) {
      queuedKeys.add(key);
    }
    startNextRequest();
    update();
    return () => {
      active = false;
      listeners.delete(update);
    };
  }, [uniqueKeys]);

  return snapshot.names;
}
