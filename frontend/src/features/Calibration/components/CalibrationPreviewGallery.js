"use client";

import { useState } from "react";
import {
  FiImage,
  FiRefreshCw,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { StatusPill } from "@/components/panels/Panel";

import {
  calibrationPreviewItems,
} from "../lib/calibrationUtils";

function previewLabel(item) {
  if (item.cameraId === "top") return "俯視角單鏡頭";
  if (item.cameraId === "side") return "側視角單鏡頭";
  if (item.cameraId === "stereo:top") return "雙鏡頭配對俯視角";
  return "雙鏡頭配對側視角";
}

function CalibrationPreviewImage({
  calibrationId,
  item,
}) {
  const [failed, setFailed] = useState(false);
  const [retryToken, setRetryToken] = useState(0);
  const source = `/api/calibrations/${encodeURIComponent(calibrationId)}/previews/${encodeURIComponent(item.previewName)}?retry=${retryToken}`;

  return (
    <article className="grid min-w-0 content-start gap-3 overflow-hidden rounded-xl border border-white/10 bg-black/10">
      <div className="relative aspect-video overflow-hidden bg-black">
        {!failed ? (
          <img
            className="size-full object-contain"
            src={source}
            alt={`${previewLabel(item)}棋盤角點預覽`}
            onLoad={() => setFailed(false)}
            onError={() => setFailed(true)}
          />
        ) : (
          <div className="grid size-full place-items-center gap-2 p-4 text-center text-sm font-semibold text-neutral-500">
            <FiImage
              className="size-6"
              aria-hidden="true"
            />
            預覽讀取失敗
          </div>
        )}
      </div>
      <div className="grid min-w-0 gap-2 px-3 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="m-0 text-xs font-black text-white">{previewLabel(item)}</h4>
          <StatusPill tone={item.found ? "success" : "offline"}>
            {item.found ? "偵測成功" : "未偵測到"}
          </StatusPill>
        </div>
        <p
          className="m-0 truncate text-[11px] font-semibold text-neutral-400"
          title={item.imageId}
        >
          {item.pairId ? `${item.pairId} · ` : ""}{item.imageId}
        </p>
        {failed ? (
          <Button
            className="min-h-9 justify-self-end px-3 text-xs"
            onClick={() => {
              setFailed(false);
              setRetryToken((current) => current + 1);
            }}
          >
            <FiRefreshCw
              className="size-3.5 shrink-0"
              aria-hidden="true"
            />
            重新載入預覽
          </Button>
        ) : null}
      </div>
    </article>
  );
}

export default function CalibrationPreviewGallery({ profile }) {
  const items = calibrationPreviewItems(profile);
  return (
    <div className="grid gap-3">
      <SubsectionHeader
        title="棋盤角點預覽"
        description="顯示所有單鏡頭影像及雙鏡頭配對兩側的角點偵測結果；預覽僅供檢查，不會成為新的校正來源。"
      />
      {items.length ? (
        <div className="grid gap-3 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-3">
          {items.map((item) => (
            <CalibrationPreviewImage
              calibrationId={profile.calibration_id}
              item={item}
              key={item.previewName}
            />
          ))}
        </div>
      ) : (
        <div className="grid min-h-24 place-items-center rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-sm font-semibold text-neutral-400">
          完成角點偵測後會在此顯示全部預覽。
        </div>
      )}
    </div>
  );
}
