"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { requestAnalysisResource } from "@/features/AnalysisRun/lib/analysisRunApiUtils";
import { trajectoryModelVersion } from "../lib/trajectoryPlaybackUtils";
import { trajectoryModelTransform } from "../lib/trajectoryModelOverlayUtils";
import { TRAJECTORY_MODEL_LIMITS } from "../trajectoryViewerConfig";

export default function useTrajectoryModelOverlay({
  analysisId,
  models,
  enabled,
  plotReady,
  plotElementRef,
  elementRef,
  opacity,
  frameKey,
}) {
  const sessionRef = useRef(null);
  const queueRef = useRef(Promise.resolve());
  const modelsRef = useRef(models);
  const opacityRef = useRef(opacity);
  modelsRef.current = models;
  opacityRef.current = opacity;
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ key: "", loading: false, loaded: 0, unavailable: 0, failed: 0, error: "" });
  const selectionKey = useMemo(() => JSON.stringify([analysisId, frameKey,
    models.map(trajectoryModelVersion), attempt]), [analysisId, frameKey, models, attempt]);

  useEffect(() => {
    if (!enabled || !plotReady || !elementRef.current || !plotElementRef.current) return undefined;
    const session = { active: true, renderer: null, references: new Map(), buffers: new Map(), attempt: 0 };
    sessionRef.current = session;
    return () => {
      session.active = false;
      session.renderer?.hide();
      sessionRef.current = null;
      session.references.clear();
      session.buffers.clear();
      queueRef.current = queueRef.current.then(() => session.renderer?.dispose()).catch(() => {});
    };
  }, [analysisId, enabled, plotReady, elementRef, plotElementRef]);

  useEffect(() => {
    const session = sessionRef.current;
    if (!enabled || !plotReady || !session?.active) return undefined;
    const controller = new AbortController();
    const selected = modelsRef.current;
    const current = () => session.active && !controller.signal.aborted;
    session.renderer?.hide();
    setState({ key: selectionKey, loading: true, loaded: 0, unavailable: 0, failed: 0, error: "" });
    queueRef.current = queueRef.current.then(async () => {
      if (!current()) return;
      if (session.attempt !== attempt) {
        session.references.clear();
        session.attempt = attempt;
      }
      let loaded = 0, unavailable = 0, failed = 0, error = "";
      const references = [];
      try {
        // Limit simultaneous authenticated metadata reads; unregistered models
        // return a small reason without hashing/downloading their PLY files.
        for (let index = 0; index < selected.length; index += 4) {
          const batch = await Promise.allSettled(selected.slice(index, index + 4).map(async (model) => {
            const version = trajectoryModelVersion(model);
            if (!session.references.has(version)) {
              const query = new URLSearchParams({ round_key: model.round_key, for_trajectory: "true" });
              const reference = await requestAnalysisResource(
                `/api/analysis/${encodeURIComponent(analysisId)}/round-model-preview?${query}`,
                { signal: controller.signal },
              );
              if (current()) session.references.set(version, reference);
              return reference;
            }
            return session.references.get(version);
          }));
          if (!current()) return;
          for (const result of batch) {
            if (result.status === "rejected") { failed += 1; continue; }
            const transform = trajectoryModelTransform(result.value);
            if (!transform || !result.value.gaussian_path) { unavailable += 1; continue; }
            references.push({ reference: result.value, transform });
          }
          setState({ key: selectionKey, loading: true, loaded: 0, unavailable, failed, error: "" });
        }
        const count = references.reduce((sum, item) => sum + (item.reference.gaussian_count || 0), 0);
        if (count > TRAJECTORY_MODEL_LIMITS.overlayGaussians) {
          throw new Error("模型總量超過同時疊加的容量，請使用播放逐輪檢視模型。");
        }
        if (references.length) {
          const [rendering, gaussian] = await Promise.all([
            import("../lib/trajectoryModelOverlay"),
            import("../lib/trajectoryGaussianBuffers"),
          ]);
          if (!current()) return;
          const buffers = [];
          for (const { reference, transform } of references) {
            const key = JSON.stringify([reference.gaussian_sha256, transform]);
            let buffer = session.buffers.get(key);
            try {
              if (!buffer) buffer = await gaussian.loadTrajectoryGaussian({ analysisId, reference, transform, signal: controller.signal });
              if (!current()) return;
              session.buffers.delete(key);
              session.buffers.set(key, buffer);
              let bytes = [...session.buffers.values()].reduce((sum, item) => sum + item.bufferData.byteLength, 0);
              while (session.buffers.size > TRAJECTORY_MODEL_LIMITS.cachedModels || bytes > TRAJECTORY_MODEL_LIMITS.cachedBytes) {
                const oldest = session.buffers.keys().next().value;
                bytes -= session.buffers.get(oldest).bufferData.byteLength;
                session.buffers.delete(oldest);
              }
              buffers.push(buffer);
              loaded += 1;
            } catch (failure) {
              if (!current()) return;
              error = failure.message || "模型載入失敗，請重試。";
              failed += 1;
            }
            setState({ key: selectionKey, loading: true, loaded: 0, unavailable, failed, error });
          }
          if (!current()) return;
          if (buffers.length) {
            session.renderer ||= rendering.createTrajectoryModelOverlay({
              element: elementRef.current,
              plotElement: plotElementRef.current,
              antialiased: references[0].reference.model_quality?.rasterize_mode === "antialiased",
              onError: (message) => {
                if (session.active) setState((previous) => ({ ...previous, loading: false, error: message, failed: Math.max(1, previous.failed) }));
              },
            });
            session.renderer.setOpacity(opacityRef.current);
            await session.renderer.show(gaussian.mergeTrajectoryGaussians(buffers));
            if (!current()) session.renderer.hide();
          }
        }
      } catch (failure) {
        if (!current()) return;
        session.renderer?.hide();
        loaded = 0;
        failed = Math.max(1, failed);
        error = failure.message || "模型疊加失敗，請重試。";
      } finally {
        if (current()) setState({ key: selectionKey, loading: false, loaded, unavailable, failed, error });
      }
    });
    return () => {
      controller.abort();
      session.renderer?.hide();
    };
  }, [analysisId, selectionKey, enabled, plotReady, attempt, elementRef, plotElementRef]);

  useEffect(() => {
    sessionRef.current?.renderer?.setOpacity(opacity);
  }, [opacity, state.loading]);

  return {
    ...state,
    loading: enabled && (!plotReady || state.key !== selectionKey || state.loading),
    retry: () => setAttempt((value) => value + 1),
  };
}
