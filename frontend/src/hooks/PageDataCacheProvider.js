"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { createPageDataCache, PAGE_CACHE_INVALIDATED_EVENT } from "@/lib/pageDataCache";

const PageDataCacheContext = createContext(null);

export default function PageDataCacheProvider({ children }) {
  const [cache] = useState(() => createPageDataCache());
  useEffect(() => {
    const invalidate = (event) => cache.invalidate(event.detail?.prefix, event.detail);
    window.addEventListener(PAGE_CACHE_INVALIDATED_EVENT, invalidate);
    return () => {
      window.removeEventListener(PAGE_CACHE_INVALIDATED_EVENT, invalidate);
      cache.clear();
    };
  }, [cache]);
  return <PageDataCacheContext.Provider value={cache}>{children}</PageDataCacheContext.Provider>;
}

export function usePageDataCache() {
  const cache = useContext(PageDataCacheContext);
  if (!cache) throw new Error("usePageDataCache 必須在 PageDataCacheProvider 內使用。");
  return cache;
}
