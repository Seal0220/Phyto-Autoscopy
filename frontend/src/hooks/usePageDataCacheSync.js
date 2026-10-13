"use client";

import { useEffect, useRef } from "react";
import { usePageDataCache } from "@/hooks/PageDataCacheProvider";

export default function usePageDataCacheSync(snapshot) {
  const cache = usePageDataCache();
  const previousScheduleRef = useRef(null);
  const previousAnalysesRef = useRef(new Map());
  const analysis = snapshot?.analysis;
  const schedule = snapshot?.schedule;

  useEffect(() => {
    if (!analysis?.analysis_id) return;
    const runKey = `analysis:run:${analysis.analysis_id}`;
    const resultKey = `analysis:results:${analysis.analysis_id}`;
    const cached = cache.read(runKey)?.value;
    const revisionOf = (progress) => [
      progress.status,
      progress.results_revision,
      progress.round_key,
      progress.round_progress === 1,
    ].join(":");
    const revision = revisionOf(analysis);
    const previous = previousAnalysesRef.current.get(analysis.analysis_id)
      ?? (cached ? revisionOf(cached.progress) : null);
    if ((previous !== null && previous !== revision)
      || (previous === null && cache.read(resultKey))) {
      cache.invalidate(runKey);
      cache.invalidate(resultKey);
      cache.invalidate("analysis:dashboard");
    }
    previousAnalysesRef.current.set(analysis.analysis_id, revision);
    if (previousAnalysesRef.current.size > 16) {
      previousAnalysesRef.current.delete(previousAnalysesRef.current.keys().next().value);
    }
    cache.update(
      runKey,
      (current) => ({
        ...current,
        run: {
          ...current.run,
          status: analysis.status,
          stage: analysis.stage,
          progress: analysis.progress,
          current_frame: analysis.current_frame,
          total_frames: analysis.total_frames,
          last_error: analysis.last_error,
        },
        progress: { ...current.progress, ...analysis },
      }),
    );
  }, [analysis, cache]);

  useEffect(() => {
    if (!schedule) return;
    const revision = [
      schedule.record_id,
      schedule.status,
      schedule.capture_count,
    ].join(":");
    if (previousScheduleRef.current !== null && previousScheduleRef.current !== revision) {
      cache.invalidate("records:");
      cache.invalidate("analysis:sources");
      cache.invalidate("analysis:dashboard");
    }
    previousScheduleRef.current = revision;
  }, [cache, schedule]);
}
