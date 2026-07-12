"use client";

import { useEffect, useRef, useState } from "react";

export default function useElapsedSeconds({
  elapsedSeconds,
  status,
}) {
  const reportedElapsed = Math.max(0, Number(elapsedSeconds) || 0);
  const [elapsed, setElapsed] = useState(reportedElapsed);
  const anchorRef = useRef({
    elapsed: reportedElapsed,
    updatedAt: Date.now(),
  });

  useEffect(() => {
    const updatedAt = Date.now();
    const currentElapsed = anchorRef.current.elapsed + (updatedAt - anchorRef.current.updatedAt) / 1000;
    const nextElapsed = status === "running"
      ? Math.max(reportedElapsed, currentElapsed)
      : reportedElapsed;

    anchorRef.current = {
      elapsed: nextElapsed,
      updatedAt,
    };
    setElapsed(nextElapsed);
  }, [reportedElapsed, status]);

  useEffect(() => {
    if (status !== "running") return undefined;

    const tick = () => {
      const updatedAt = Date.now();
      const nextElapsed = anchorRef.current.elapsed + (updatedAt - anchorRef.current.updatedAt) / 1000;
      anchorRef.current = {
        elapsed: nextElapsed,
        updatedAt,
      };
      setElapsed(nextElapsed);
    };

    tick();
    const intervalId = window.setInterval(tick, 250);
    return () => window.clearInterval(intervalId);
  }, [status]);

  return elapsed;
}
