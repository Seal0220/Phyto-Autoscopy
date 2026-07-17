"use client";

import { useEffect, useMemo, useState } from "react";
import {
  FiLink,
  FiPlus,
  FiTrash2,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { SelectInput } from "@/components/inputs/Input";
import InnerPanel from "@/components/panels/InnerPanel";

function pathLabel(
  path,
  images,
) {
  const image = images.find((item) => item.path === path);
  return image
    ? `${image.name} · ${image.image_width} × ${image.image_height}`
    : path;
}

export default function CalibrationStereoPairs({
  images,
  topPaths,
  sidePaths,
  pairs,
  onAdd,
  onRemove,
}) {
  const [topPath, setTopPath] = useState("");
  const [sidePath, setSidePath] = useState("");
  const [localError, setLocalError] = useState("");
  const topOptions = useMemo(
    () => topPaths.map((path) => ({
      value: path,
      label: pathLabel(
        path,
        images,
      ),
    })),
    [images, topPaths],
  );
  const sideOptions = useMemo(
    () => sidePaths.map((path) => ({
      value: path,
      label: pathLabel(
        path,
        images,
      ),
    })),
    [images, sidePaths],
  );

  useEffect(() => {
    if (topPath && !topPaths.includes(topPath)) setTopPath("");
  }, [topPath, topPaths]);

  useEffect(() => {
    if (sidePath && !sidePaths.includes(sidePath)) setSidePath("");
  }, [sidePath, sidePaths]);

  function addPair() {
    try {
      onAdd(
        topPath,
        sidePath,
      );
      setLocalError("");
    } catch (error) {
      setLocalError(error instanceof Error ? error.message.trim() : "無法新增雙目影像配對。");
    }
  }

  return (
    <InnerPanel
      as="section"
      aria-labelledby="calibration-stereo-pairs-title"
    >
      <SubsectionHeader
        titleId="calibration-stereo-pairs-title"
        title="雙目影像配對"
        description="每組影像必須讓同一個實測校正物件同時出現在俯視角與側視角；系統不會依檔名推測配對。"
      />

      <div className="grid gap-3 min-[720px]:grid-cols-2">
        <SelectInput
          id="calibration-stereo-top-image"
          label="俯視角影像"
          value={topPath}
          options={[
            {
              value: "",
              label: "請選擇",
            },
            ...topOptions,
          ]}
          onValueChange={(value) => {
            setTopPath(value);
            setLocalError("");
          }}
        />
        <SelectInput
          id="calibration-stereo-side-image"
          label="側視角影像"
          value={sidePath}
          options={[
            {
              value: "",
              label: "請選擇",
            },
            ...sideOptions,
          ]}
          onValueChange={(value) => {
            setSidePath(value);
            setLocalError("");
          }}
        />
      </div>

      {localError ? (
        <p
          className="m-0 rounded-xl border border-rose-300/30 bg-rose-500/10 p-3 text-sm font-semibold text-rose-200"
          role="alert"
        >
          {localError}
        </p>
      ) : null}

      <div className="flex justify-end">
        <Button
          disabled={!topPath || !sidePath}
          onClick={addPair}
        >
          <FiPlus
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          新增配對
        </Button>
      </div>

      <div className="grid gap-2">
        {pairs.length ? pairs.map((pair, index) => (
          <article
            className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-xl border border-white/10 bg-black/10 p-3"
            key={`${pair[0]}::${pair[1]}`}
          >
            <FiLink
              className="size-4 shrink-0 text-emerald-200"
              aria-hidden="true"
            />
            <div className="min-w-0">
              <h4 className="m-0 text-xs font-black text-emerald-200">
                配對 {String(index + 1).padStart(2, "0")}
              </h4>
              <p className="mt-1 truncate text-xs font-semibold text-neutral-300">
                俯視角：{pathLabel(pair[0], images)}
              </p>
              <p className="mt-1 truncate text-xs font-semibold text-neutral-300">
                側視角：{pathLabel(pair[1], images)}
              </p>
            </div>
            <button
              className="grid size-9 shrink-0 cursor-pointer place-items-center rounded-xl border border-transparent text-neutral-300 transition-[background-color,border-color,color] duration-150 hover:border-rose-300/30 hover:bg-rose-500/15 hover:text-rose-200 focus-visible:outline-2 focus-visible:outline-emerald-300"
              type="button"
              aria-label={`移除配對 ${index + 1}`}
              onClick={() => onRemove(index)}
            >
              <FiTrash2
                className="size-4"
                aria-hidden="true"
              />
            </button>
          </article>
        )) : (
          <div className="grid min-h-20 place-items-center rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-sm font-semibold text-neutral-400">
            尚未建立雙目影像配對。
          </div>
        )}
      </div>
    </InnerPanel>
  );
}
