"use client";

import {
  useCallback,
  useEffect,
  useState,
} from "react";
import {
  FiChevronLeft,
  FiChevronRight,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import { SelectInput } from "@/components/inputs/Input";

import { ANALYSIS_IMAGE_SPACE_OPTIONS } from "../analysisRunConfig";
import { requestAnalysisResource } from "../lib/analysisRunApiUtils";
import { analysisImageGroups } from "../lib/analysisRunUtils";
import AnalysisRunImage from "./AnalysisRunImage";

export default function AnalysisRunRoundImages({
  analysisId,
  round,
  model,
  hasLandmark,
}) {
  const [views, setViews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [groupIndex, setGroupIndex] = useState(0);
  const [space, setSpace] = useState(hasLandmark ? "reprojection" : "source");
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
  const selectedIndex = Math.min(groupIndex, Math.max(0, groups.length - 1));
  const group = groups[selectedIndex];

  return (
    <div className="grid min-w-0 gap-3">
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
          <div className="grid min-w-0 gap-3 min-[720px]:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
            <SelectInput
              id={`analysis-snapshot-${round.round_key}`}
              label="擷取組"
              value={String(selectedIndex)}
              options={groups.map((item, index) => ({ value: String(index), label: item.key }))}
              onValueChange={(value) => setGroupIndex(Number(value))}
            />
            <SelectInput
              id={`analysis-image-space-${round.round_key}`}
              label="影像類型"
              value={space}
              options={ANALYSIS_IMAGE_SPACE_OPTIONS}
              onValueChange={setSpace}
            />
            <div className="flex items-center justify-end gap-2">
              <Button
                aria-label="上一組擷取影像"
                disabled={selectedIndex === 0}
                onClick={() => setGroupIndex(selectedIndex - 1)}
              >
                <FiChevronLeft aria-hidden="true" />
              </Button>
              <span className="whitespace-nowrap text-xs font-semibold text-neutral-400">
                {selectedIndex + 1} / {groups.length}
              </span>
              <Button
                aria-label="下一組擷取影像"
                disabled={selectedIndex === groups.length - 1}
                onClick={() => setGroupIndex(selectedIndex + 1)}
              >
                <FiChevronRight aria-hidden="true" />
              </Button>
            </div>
          </div>
          <div className="grid min-w-0 gap-3 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-3">
            {group.views.map((view) => (
              <AnalysisRunImage
                key={`${view.view_id}:${space}`}
                analysisId={analysisId}
                view={view}
                coordinateSpace={space}
              />
            ))}
          </div>
        </>
      ) : !loading && !error ? <p>此輪沒有來源影像。</p> : null}
      {model?.preview_paths?.length ? (
        <div className="grid min-w-0 gap-3 min-[720px]:grid-cols-2">
          {model.preview_paths.map((path, index) => (
            <AnalysisRunImage
              key={path}
              analysisId={analysisId}
              artifactPath={path}
              label={`模型預覽 ${index + 1}`}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
