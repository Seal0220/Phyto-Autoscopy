"use client";

import { useState } from "react";

import RetryMessage from "@/components/feedback/RetryMessage";
import FullscreenImage from "@/components/media/FullscreenImage";
import { ANALYSIS_CAMERA_LABELS } from "@/features/Analysis/analysisConfig";
import {
  analysisArtifactUrl,
  analysisViewImageUrl,
} from "@/lib/analysisImageUtils";
import { formatDateTime } from "@/lib/formatUtils";

import { ANALYSIS_IMAGE_SPACE_LABELS } from "../analysisRunConfig";

export default function AnalysisRunImage({
  analysisId,
  view,
  coordinateSpace = "source",
  artifactPath,
  revision,
  label,
}) {
  const [space, setSpace] = useState(coordinateSpace);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const cameraLabel = label || ANALYSIS_CAMERA_LABELS[view?.camera_id] || "分析影像";
  const baseUrl = artifactPath
    ? analysisArtifactUrl(analysisId, artifactPath)
    : analysisViewImageUrl(analysisId, view?.view_id, space);
  const version = artifactPath ? revision : "";
  const imageUrl = `${baseUrl}${baseUrl.includes("?") ? "&" : "?"}revision=${encodeURIComponent(version || "")}&retry=${retry}`;

  function handleError() {
    if (!artifactPath && space !== "source") {
      setSpace(space === "reprojection" ? "undistorted" : "source");
      return;
    }
    setFailed(true);
  }

  return (
    <figure className="m-0 grid min-w-0 content-start gap-2">
      <figcaption className="flex min-w-0 flex-wrap items-center justify-between gap-2 text-xs font-bold">
        <span className="text-neutral-100">{cameraLabel}</span>
        {!artifactPath ? (
          <span className="text-neutral-400">
            {ANALYSIS_IMAGE_SPACE_LABELS[space]}
            {space !== coordinateSpace ? "（此處理圖目前不可用）" : ""}
          </span>
        ) : null}
      </figcaption>
      {failed ? (
        <RetryMessage
          message="影像讀取失敗，請重試。"
          onRetry={() => {
            setSpace(coordinateSpace);
            setFailed(false);
            setRetry((value) => value + 1);
          }}
        />
      ) : (
        <div className="relative aspect-video overflow-hidden rounded-xl border border-white/15 bg-black">
          {/* 保留完整科學影像，圖片經同源且受保護的 BFF 載入。 */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            className="h-full w-full object-contain"
            src={imageUrl}
            alt={`${cameraLabel}${artifactPath ? "" : ANALYSIS_IMAGE_SPACE_LABELS[space]}`}
            loading="lazy"
            onError={handleError}
          />
          <FullscreenImage
            src={imageUrl}
            alt={cameraLabel}
            label={cameraLabel}
          />
        </div>
      )}
      {view?.timestamp ? (
        <p className="m-0 break-all text-xs font-semibold text-neutral-500">
          {view.snapshot_id || ""} · {formatDateTime(view.timestamp)}
        </p>
      ) : null}
    </figure>
  );
}
