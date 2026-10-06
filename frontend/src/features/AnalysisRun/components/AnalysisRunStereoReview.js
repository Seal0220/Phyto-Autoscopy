"use client";

import { useEffect, useId, useRef } from "react";
import { PiCheck } from "react-icons/pi";
import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import SelectMenu from "@/components/inputs/SelectMenu";
import DisclosurePanel from "@/components/panels/DisclosurePanel";
import useAnalysisRunStereoReview from "../hooks/useAnalysisRunStereoReview";
import {
  completedStereoPairs,
  stereoPairLabel,
  stereoValidationCount,
} from "../lib/analysisStereoReviewUtils";
import AnalysisRunStereoReviewImage from "./AnalysisRunStereoReviewImage";
import AnalysisRunModelReference from "./AnalysisRunModelReference";
import AnalysisRunPairActions from "./AnalysisRunPairActions";

export default function AnalysisRunStereoReview({
  analysisId,
  open,
  onClose,
  onAccepted,
  onReloadRun,
}) {
  const element = useRef(null);
  const titleId = useId();
  const selectId = useId();
  const state = useAnalysisRunStereoReview({
    analysisId,
    open,
    onAccepted,
  });
  const modelReference = state.review?.mode === "model_reference";
  const completed = completedStereoPairs(state.pairs, modelReference).length;
  const checkedCount = stereoValidationCount(state.validation);
  const locked = state.saving || state.unknown || state.loading;
  const incomplete = state.pairs.some((pair) => Boolean(pair.top) !== Boolean(pair.side)
    || (modelReference && (pair.top || pair.side) && !Number.isInteger(pair.model_point_id)));

  useEffect(() => {
    if (!open) return undefined;
    const frame = window.requestAnimationFrame(() => {
      element.current?.scrollIntoView({
        block: "start",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
      element.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  if (!open) return null;
  return (
    <section
      className="grid min-w-0 scroll-mt-28 gap-4 outline-none max-[980px]:scroll-mt-36"
      aria-labelledby={titleId}
      tabIndex={-1}
      ref={element}
    >
      <SubsectionHeader
        title={modelReference ? "對齊相機" : "雙鏡頭配對"}
        titleId={titleId}
        description={modelReference
          ? "選三維參照點，再標記兩張影像中的同一位置，至少四組。"
          : "標記同一位置，可選芽尖、葉尖或莖節，盡量分散。"}
      >
        <Button
          disabled={state.saving}
          onClick={onClose}
        >
          收合
        </Button>
      </SubsectionHeader>
      <div className="grid min-w-0 gap-3">
        {state.error ? (
          state.unknown ? (
            <RetryMessage
              message={state.error}
              onRetry={async () => {
                await onReloadRun();
                await state.load();
              }}
              retrying={false}
            />
          ) : state.review ? (
            <div
              role="alert"
              className="rounded-xl border border-rose-300/30 bg-rose-500/10 p-3 text-sm text-rose-200"
            >
              {state.error}
            </div>
          ) : (
            <RetryMessage
              message={state.error}
              onRetry={state.load}
              retrying={state.loading}
            />
          )
        ) : null}
        {state.loading ? <p role="status">讀取配對影像中…</p> : null}
        {state.review ? (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <label
                htmlFor={selectId}
                className="text-sm font-bold text-neutral-300"
              >
                配對
              </label>
              <SelectMenu
                id={selectId}
                value={state.selected}
                options={state.pairs.map((pair, index) => ({
                  value: index,
                  label: stereoPairLabel(pair, index, state.validation),
                  disabled: locked,
                }))}
                onValueChange={(value) => { if (!locked) state.setSelected(Number(value)); }}
              />
              <span
                className="text-sm font-bold text-neutral-400"
                role="status"
              >
                {`已標記 ${completed} 組 · 至少 ${state.review.minimum_pairs} 組`}
                {checkedCount !== null ? ` · 本次內點 ${checkedCount} 組 · 黃色點需檢查` : ""}
              </span>
            </div>
            {modelReference ? (
              <AnalysisRunModelReference
                analysisId={analysisId}
                reference={state.review.reference}
                selectedPointId={state.pairs[state.selected]?.model_point_id}
                pointIds={state.pairs.map((pair) => pair.model_point_id)}
                pairNumber={state.selected + 1}
                disabled={locked}
                onPointChange={state.changeModelPoint}
                onPointMove={state.moveModelPoint}
                onPointRemove={state.removeModelPoint}
              />
            ) : null}
            <div className="grid min-w-0 gap-4 min-[800px]:grid-cols-2">
              {state.review.views.map((view) => (
                <AnalysisRunStereoReviewImage
                  key={view.view_id}
                  analysisId={analysisId}
                  view={view}
                  pairs={state.pairs}
                  selected={state.selected}
                  validation={state.validation}
                  disabled={locked}
                  onPointChange={state.changePoint}
                  onPairRemove={state.removePair}
                />
              ))}
            </div>
            {state.review.reason ? (
              <DisclosurePanel title="配對原因">
                <p className="m-0 break-words text-xs font-semibold text-neutral-400">
                  {state.review.reason}
                </p>
              </DisclosurePanel>
            ) : null}
          </>
        ) : null}
      </div>
      {state.review ? (
        <div
          className="sticky bottom-0 z-20 grid min-w-0 rounded-xl bg-[#0e1c16]/95 px-3 pb-3 backdrop-blur-md"
          aria-label="配對操作"
        >
          <ActionRow className="w-full justify-end">
            <AnalysisRunPairActions
              disabled={locked}
              full={state.pairs.length >= 200}
              onAdd={state.addPair}
              onRemove={() => state.removePair()}
            />
            <Button
              variant="primary"
              disabled={locked || incomplete || completed < state.review.minimum_pairs}
              onClick={() => void state.submit()}
            >
              <PiCheck
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              {state.saving ? "驗證中…" : "驗證"}
            </Button>
          </ActionRow>
        </div>
      ) : null}
    </section>
  );
}
