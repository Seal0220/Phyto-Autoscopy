"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useMainNavigationContext } from "../components/MainNavigationProvider";

export default function useAnalysisSecondaryNavigation({
  canOpenResults = false,
  navigationLocked = false,
  resultsLocked = false,
} = {}) {
  const pathname = usePathname();
  const { setRegistration } = useMainNavigationContext();
  useEffect(() => {
    const owner = {};
    setRegistration({
      owner,
      pathname,
      options: {
        canOpenResults,
        navigationLocked,
        resultsLocked,
      },
    });
    return () => setRegistration((current) => current?.owner === owner ? null : current);
  }, [
    pathname,
    setRegistration,
    canOpenResults,
    navigationLocked,
    resultsLocked,
  ]);
}
