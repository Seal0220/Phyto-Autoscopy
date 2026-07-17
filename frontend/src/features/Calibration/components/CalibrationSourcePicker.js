"use client";

import { useMemo, useState } from "react";
import { FiImage } from "react-icons/fi";

import { TextInput } from "@/components/inputs/Input";
import InnerPanel from "@/components/panels/InnerPanel";

function sourceLabel(source) {
  return source === "captures" ? "捕捉資料" : "校正資料";
}

export default function CalibrationSourcePicker({
  cameraId,
  cameraLabel,
  images,
  selectedPaths,
  onToggle,
}) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLocaleLowerCase("zh-Hant");
  const filteredImages = useMemo(
    () => images.filter((image) => {
      if (!normalizedQuery) return true;
      return [
        image.name,
        image.relative_path,
        image.path,
      ].some((value) => String(value || "")
        .toLocaleLowerCase("zh-Hant")
        .includes(normalizedQuery));
    }),
    [images, normalizedQuery],
  );

  return (
    <InnerPanel
      as="section"
      aria-label={`${cameraLabel}校正影像`}
      className="content-start"
    >
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
        <div className="min-w-0">
          <h4 className="m-0 text-sm font-black text-white">
            {cameraLabel}單目影像
          </h4>
          <p className="mt-1 text-xs font-semibold text-neutral-400">
            手動選擇已知棋盤規格且覆蓋主要視野的影像。
          </p>
        </div>
        <span className="text-xs font-black text-emerald-200">
          已選 {selectedPaths.length} 張
        </span>
      </div>

      <TextInput
        id={`calibration-${cameraId}-source-search`}
        label={`搜尋${cameraLabel}影像`}
        value={query}
        onValueChange={setQuery}
        placeholder="檔名或相對路徑"
      />

      <div className="grid max-h-80 gap-2 overflow-y-auto pr-1">
        {filteredImages.length ? filteredImages.map((image) => {
          const selected = selectedPaths.includes(image.path);
          return (
            <label
              className={`grid min-w-0 cursor-pointer grid-cols-[auto_minmax(0,1fr)] items-start gap-3 rounded-xl border p-3 transition-[background-color,border-color,color] duration-150 ${
                selected
                  ? "border-emerald-200/55 bg-emerald-400/12 hover:border-emerald-100/75 hover:bg-emerald-400/18"
                  : "border-white/10 bg-black/10 hover:border-white/20 hover:bg-white/[0.06]"
              }`}
              key={image.path}
            >
              <input
                className="mt-1 size-4 accent-emerald-400"
                type="checkbox"
                checked={selected}
                onChange={() => onToggle(image.path)}
              />
              <span className="min-w-0">
                <span className="flex min-w-0 items-center gap-2 text-sm font-bold text-neutral-100">
                  <FiImage
                    className="size-4 shrink-0 text-emerald-200"
                    aria-hidden="true"
                  />
                  <span className="truncate">{image.name}</span>
                </span>
                <span className="mt-1 block break-all text-xs font-semibold text-neutral-400">
                  {image.relative_path || image.path}
                </span>
                <span className="mt-1 block text-[11px] font-bold text-neutral-500">
                  {image.image_width} × {image.image_height} · {sourceLabel(image.source)}
                </span>
              </span>
            </label>
          );
        }) : (
          <div className="grid min-h-24 place-items-center rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-center text-sm font-semibold text-neutral-400">
            {images.length ? "沒有符合搜尋條件的影像。" : "目前沒有可用的校正來源影像。"}
          </div>
        )}
      </div>
    </InnerPanel>
  );
}
