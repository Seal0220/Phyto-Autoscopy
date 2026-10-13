"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import { requestAnalysisResource } from "../lib/analysisRunApiUtils";
import { analysisImageGroups } from "../lib/analysisRunUtils";
import AnalysisRunImage from "./AnalysisRunImage";
import AnalysisRunRoundImageControls from "./AnalysisRunRoundImageControls";
import AnalysisRunRoundTipImage from "./AnalysisRunRoundTipImage";
import AnalysisRunRoundTipEditor from "./AnalysisRunRoundTipEditor";
import useAnalysisRunFeatureCorrespondences from "../hooks/useAnalysisRunFeatureCorrespondences";

export default function AnalysisRunRoundImages({
  analysisId,
  round,
  hasLandmark,
  marking = false,
  correction,
  onSaved,
  onFinishEditing,
  model,
  landmark,
  controlsElement,
  featureActionElement,
  tipActionElement,
}) {
  const [views, setViews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [groupIndex, setGroupIndex] = useState(0);
  const [space, setSpace] = useState(hasLandmark ? "reprojection" : "undistorted");
  const [showFeatures, setShowFeatures] = useState(true);
  const [activeFeature, setActiveFeature] = useState(null);
  const selectedCorrection = useRef(null);
  const reload = useCallback(() => setRetry((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError("");
    const query = new URLSearchParams({ round_key: round.round_key });
    void requestAnalysisResource(
      `/api/analysis/${encodeURIComponent(analysisId)}/views?${query}`,
      { signal: controller.signal },
    ).then((payload) => {
      if (active) setViews(Array.isArray(payload) ? payload : []);
    }).catch((failure) => {
      if (active && failure?.name !== "AbortError") {
        setError("讀取此輪影像清單失敗，請重試。");
      }
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [analysisId, round.round_key, retry]);

  const groups = analysisImageGroups(views);
  useEffect(() => {
    const identity = correction?.correction_id || landmark?.tip_id;
    if (!views.length || !identity || selectedCorrection.current === identity) return;
    const observations = correction ? correction.observations?.length ? correction.observations : correction.projected_observations || []
      : landmark?.image_observations || [];
    const selected = views.find((view) => view.view_id === observations[0]?.view_id);
    if (selected) {
      const index = analysisImageGroups(views).findIndex((item) => item.views.some((view) => view.view_id === selected.view_id));
      if (index >= 0) setGroupIndex(index);
    }
    selectedCorrection.current = identity;
  }, [views, correction, landmark]);
  const selectedIndex = Math.min(groupIndex, Math.max(0, groups.length - 1));
  const group = groups[selectedIndex];
  const features = useAnalysisRunFeatureCorrespondences({
    analysisId,
    roundKey: round.round_key,
    snapshotId: group?.views[0]?.snapshot_id,
    enabled: showFeatures,
    modelStatus: model?.status,
  });
  useEffect(() => { setActiveFeature(null); }, [group?.key]);
  const imagePoints = correction?.invalid ? [] : correction?.observations?.length ? correction.observations
    : correction?.projected_observations?.length ? correction.projected_observations
      : landmark?.image_tip_confirmed ? landmark.image_observations || [] : [];
  const controls = groups.length ? (
    <AnalysisRunRoundImageControls
      roundKey={round.round_key}
      groups={groups}
      selectedIndex={selectedIndex}
      onGroupChange={setGroupIndex}
      space={space}
      onSpaceChange={setSpace}
      marking={marking}
      compact={controlsElement !== undefined}
    />
  ) : null;
  const featureControls = (
    <>
      <Button
        aria-pressed={showFeatures}
        onClick={() => {
          setShowFeatures((value) => !value);
          setSpace("undistorted");
          setActiveFeature(null);
        }}
      >
        {showFeatures ? "隱藏葉片特徵點" : "顯示葉片特徵點"}
      </Button>
      {showFeatures ? (
        <p
          className={`m-0 text-xs text-neutral-400 ${featureActionElement !== undefined ? "min-w-[12rem] max-w-sm shrink-0" : ""}`}
          role="status"
        >
          {features.loading ? "讀取葉片特徵配對中…" : features.result?.features?.length
            ? `${features.result.features.length} 組配對；游標停在青色點上可突出其他視角的對應點。`
            : "這組影像尚無可靠的葉片特徵配對。"}
          {features.result?.unregistered_view_ids?.length ? " 部分視角尚未對齊，沒有對應點。" : ""}
        </p>
      ) : null}
    </>
  );

  return (
    <div className="@container grid min-w-0 gap-3">
      {loading ? <p role="status">讀取此輪影像中…</p> : null}
      {error ? (
        <RetryMessage
          message={error}
          onRetry={reload}
          retrying={loading}
        />
      ) : null}
      {groups.length ? (
        <>
          {controlsElement === undefined ? controls : controlsElement ? createPortal(controls, controlsElement) : null}
          {featureActionElement === undefined ? (
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              {featureControls}
            </div>
          ) : featureActionElement ? createPortal(featureControls, featureActionElement) : null}
          {features.error ? <RetryMessage message={features.error} onRetry={features.retry} /> : null}
          {marking ? (
            <AnalysisRunRoundTipEditor
              analysisId={analysisId}
              roundKey={round.round_key}
              views={group.views}
              model={model}
              landmark={landmark}
              correction={correction}
              onSaved={onSaved}
              onFinishEditing={onFinishEditing}
              initializing={round.status === "waiting_tip_seed"}
              features={showFeatures ? features.result?.features || [] : []}
              activeFeature={activeFeature}
              onActiveFeature={setActiveFeature}
              actionElement={tipActionElement}
            />
          ) : <div className="grid min-w-0 gap-3 @min-[720px]:grid-cols-3">
            {group.views.map((view) => (
              space !== "source" && (imagePoints.length || showFeatures) ? <AnalysisRunRoundTipImage
                key={view.view_id}
                analysisId={analysisId}
                view={view}
                viewIndex={group.views.indexOf(view)}
                point={imagePoints.find((item) => item.view_id === view.view_id) || null}
                initialCoordinateSpace="undistorted"
                disabled
                features={showFeatures ? features.result?.features || [] : []}
                activeFeature={activeFeature}
                onActiveFeature={setActiveFeature}
              /> : <AnalysisRunImage
                key={`${view.view_id}:${space}`}
                analysisId={analysisId}
                view={view}
                coordinateSpace={space}
              />
            ))}
          </div>}
        </>
      ) : !loading && !error ? <p>此輪沒有來源影像。</p> : null}
    </div>
  );
}
