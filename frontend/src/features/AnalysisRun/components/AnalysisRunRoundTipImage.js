"use client";

import {
  useEffect,
  useState,
} from "react";
import { FiX } from "react-icons/fi";

import FullscreenImage from "@/components/media/FullscreenImage";
import { StatusPill } from "@/components/panels/Panel";
import { ANALYSIS_CAMERA_LABELS } from "@/features/Analysis/analysisConfig";
import { formatDateTime } from "@/lib/formatUtils";

import { analysisViewImageUrl } from "@/lib/analysisImageUtils";
import AnalysisRunTipImage from "./AnalysisRunTipImage";

export default function AnalysisRunRoundTipImage({
  analysisId,
  view,
  point,
  viewIndex,
  disabled,
  onPointChange,
  onPointRemove,
  initialCoordinateSpace = "reprojection",
  features = [],
  activeFeature,
  onActiveFeature,
}) {
  const [coordinateSpace, setCoordinateSpace] = useState(initialCoordinateSpace);
  const cameraLabel = ANALYSIS_CAMERA_LABELS[view.camera_id] || "未知視角";
  const imageUrl = analysisViewImageUrl(
    analysisId,
    view.view_id,
    coordinateSpace,
  );

  useEffect(() => {
    setCoordinateSpace(initialCoordinateSpace);
  }, [view.view_id, initialCoordinateSpace]);
  const imageProps = {
    src: imageUrl, alt: `${cameraLabel}尖端標記`, viewId: view.view_id,
    cameraLabel, point, disabled, onPointChange, onPointRemove,
    features, activeFeature, onActiveFeature,
    onError: () => { if (coordinateSpace !== "undistorted") setCoordinateSpace("undistorted"); },
  };

  return (
    <article className="grid min-w-0 gap-3 rounded-xl border border-white/15 bg-black/15 p-3">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <div className="min-w-0">
          <h4 className="m-0 truncate text-sm font-black text-white">
            {cameraLabel}
          </h4>
          <p className="mt-1 m-0 truncate text-xs font-semibold text-neutral-500">
            {`影像 ${viewIndex + 1}・${formatDateTime(view.timestamp)}`}
          </p>
        </div>
        <StatusPill tone={point ? "success" : "neutral"}>
          {point ? "已指定" : "未指定"}
        </StatusPill>
      </div>

      <div className="relative min-w-0">
        <AnalysisRunTipImage {...imageProps} />
        <FullscreenImage
          src={imageUrl}
          alt={`${cameraLabel}尖端標記重投影`}
          label={`${cameraLabel}尖端標記`}
          imageContent={<AnalysisRunTipImage {...imageProps} fullscreen />}
        />
      </div>

      <div className="flex min-w-0 items-center justify-between gap-2 text-xs font-bold text-neutral-400">
        <span className="min-w-0 truncate">
          {point
            ? `X ${point.x_px.toFixed(1)} / Y ${point.y_px.toFixed(1)} px`
            : disabled
              ? "目前未使用視角修正"
              : "點擊影像指定尖端"
          }
        </span>
        {point && !disabled ? (
          <button
            type="button"
            className="inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-lg px-2 py-1 text-neutral-300 transition-colors duration-150 hover:bg-rose-500/15 hover:text-rose-200 focus-visible:outline-2 focus-visible:outline-emerald-300"
            onClick={() => onPointRemove(view.view_id)}
          >
            <FiX
              className="size-3.5"
              aria-hidden="true"
            />
            清除
          </button>
        ) : null}
      </div>
    </article>
  );
}
