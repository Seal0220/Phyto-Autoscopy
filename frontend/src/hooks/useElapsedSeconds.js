"use client";

import { useEffect, useRef, useState } from "react";

export default function useElapsedSeconds({
  elapsedSeconds,
  resetKey,
  status,
}) {
  const reportedElapsed = Math.max(0, Number(elapsedSeconds) || 0);
  const [elapsed, setElapsed] = useState(reportedElapsed);
  const anchorRef = useRef({
    elapsed: reportedElapsed,
    resetKey,
    updatedAt: Date.now(),
  });

  useEffect(() => {
    const updatedAt = Date.now();
    const resetElapsed = anchorRef.current.resetKey !== resetKey;
    const currentElapsed = (
      anchorRef.current.elapsed
      + (updatedAt - anchorRef.current.updatedAt) / 1000
    );
    const nextElapsed = resetElapsed
      ? reportedElapsed
      : status === "running"
        ? Math.max(reportedElapsed, currentElapsed)
        : reportedElapsed;

    anchorRef.current = {
      elapsed: nextElapsed,
      resetKey,
      updatedAt,
    };
    setElapsed(nextElapsed);
  }, [reportedElapsed, resetKey, status]);

  useEffect(() => {
    if (status !== "running") return undefined;

    const tick = () => {
      const updatedAt = Date.now();
      const nextElapsed = anchorRef.current.elapsed + (updatedAt - anchorRef.current.updatedAt) / 1000;
      anchorRef.current = {
        elapsed: nextElapsed,
        resetKey,
        updatedAt,
      };
      setElapsed(nextElapsed);
    };

    tick();
    const intervalId = window.setInterval(tick, 250);
    return () => window.clearInterval(intervalId);
  }, [resetKey, status]);

  return elapsed;
}
