"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";
import { TRAJECTORY_PLOT_CONFIG } from "../trajectoryViewerConfig";
import { currentTrajectoryCamera, defaultTrajectoryCamera, formalTrajectoryPlotLayout } from "../lib/trajectoryPlotUtils";

export default function useFormalTrajectoryPlot({
  analysisId,
  traces,
  ranges,
  hasPoints,
}) {
  const plotElementRef = useRef(null);
  const sessionRef = useRef(null);
  const renderQueueRef = useRef(Promise.resolve());
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retryKey, setRetryKey] = useState(0);

  // The plot lives for this analysis, not for one polling response. All renders
  // and teardown are ordered so an old async completion cannot purge a new plot.
  useEffect(() => {
    if (!hasPoints) return undefined;
    const session = {
      active: true,
      element: plotElementRef.current,
      plotly: null,
      layout: null,
      resizeObserver: null,
      resizeFrame: null,
      size: null,
    };
    sessionRef.current = session;
    setLoading(true);
    setLoadError("");
    return () => {
      session.active = false;
      session.resizeObserver?.disconnect();
      if (session.resizeFrame !== null) cancelAnimationFrame(session.resizeFrame);
      renderQueueRef.current = renderQueueRef.current.then(() => {
        try {
          if (session.plotly) session.plotly.purge(session.element);
        } catch {
          // A detached WebGL canvas must not reject the queue for the next plot.
        }
      });
    };
  }, [analysisId, hasPoints, retryKey]);

  useEffect(() => {
    const session = sessionRef.current;
    if (!hasPoints || !session?.element || !session.active) return undefined;
    let active = true;
    renderQueueRef.current = renderQueueRef.current.then(async () => {
      if (!active || !session.active) return;
      try {
        if (!session.plotly) {
          const plotlyModule = await import("plotly.js-gl3d-dist-min");
          if (!active || !session.active) return;
          session.plotly = plotlyModule.default || plotlyModule;
        }
        // Preserve the live view even if the wheel handler has not yet saved
        // its final zoom to Plotly's layout.
        session.layout ||= formalTrajectoryPlotLayout(ranges, defaultTrajectoryCamera(), analysisId);
        session.layout.scene.camera = currentTrajectoryCamera(session.element, session.layout.scene.camera);
        for (const axis of ["x", "y", "z"]) session.layout.scene[`${axis}axis`].range = ranges[axis];
        await session.plotly.react(
          session.element,
          traces,
          session.layout,
          TRAJECTORY_PLOT_CONFIG,
        );
        if (!session.active) return;
        if (!session.resizeObserver) {
          session.size = [session.element.clientWidth, session.element.clientHeight];
          session.resizeObserver = new ResizeObserver(() => {
            const size = [session.element.clientWidth, session.element.clientHeight];
            if (size.every((value, index) => value === session.size[index])) return;
            session.size = size;
            if (session.resizeFrame !== null) cancelAnimationFrame(session.resizeFrame);
            session.resizeFrame = requestAnimationFrame(() => {
              session.resizeFrame = null;
              if (session.active && session.element.isConnected) {
                renderQueueRef.current = renderQueueRef.current.then(async () => {
                  if (!session.active || !session.element.isConnected) return;
                  const camera = currentTrajectoryCamera(session.element, session.layout.scene.camera);
                  await session.plotly.relayout(session.element, {
                    width: session.element.clientWidth,
                    height: session.element.clientHeight,
                    "scene.camera": camera,
                  });
                }).catch(() => {
                  if (session.active) setLoadError("調整三維圖表尺寸失敗，請重新載入圖表。");
                });
              }
            });
          });
          session.resizeObserver.observe(session.element.parentElement);
        }
      } catch {
        if (active && session.active) {
          setLoadError("無法顯示互動式三維軌跡，請重試或檢查瀏覽器的 WebGL 支援。");
        }
      } finally {
        if (active && session.active) setLoading(false);
      }
    });
    return () => { active = false; };
  }, [analysisId, hasPoints, traces, ranges, retryKey]);

  const resetCamera = () => {
    const session = sessionRef.current;
    if (!session?.active || !session.plotly) return;
    const camera = defaultTrajectoryCamera();
    renderQueueRef.current = renderQueueRef.current.then(async () => {
      if (!session.active) return;
      try {
        await session.plotly.relayout(session.element, { "scene.camera": camera });
      } catch {
        if (session.active) setLoadError("重設三維視角失敗，請重新載入圖表。");
      }
    });
  };

  return {
    plotElementRef,
    loading,
    loadError,
    resetCamera,
    retry: () => setRetryKey((value) => value + 1),
  };
}
