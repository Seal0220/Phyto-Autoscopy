"use client";

import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import SelectMenu from "@/components/inputs/SelectMenu";
import { Panel, PanelHeader } from "@/components/panels/Panel";
import useAnalysisRunStereoReview from "../hooks/useAnalysisRunStereoReview";
import { completedStereoPairs } from "../lib/analysisStereoReviewUtils";
import AnalysisRunStereoReviewImage from "./AnalysisRunStereoReviewImage";

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
  const state = useAnalysisRunStereoReview({ analysisId, open, onAccepted });
  const completed = completedStereoPairs(state.pairs).length;
  const locked = state.saving || state.unknown || state.loading;
  const incomplete = state.pairs.some((pair) => Boolean(pair.top) !== Boolean(pair.side));

  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    element.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus?.();
    };
  }, [open]);

  if (!open) return null;
  return createPortal(
    <div
      className="fixed inset-0 z-200 grid place-items-center bg-[#06100c]/95 p-3 max-sm:p-2"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      tabIndex={-1}
      ref={element}
      onKeyDown={(event) => {
        if (!event.currentTarget.contains(event.target)) return;
        if (event.key === "Escape" && !state.saving) onClose();
        if (event.key !== "Tab") return;
        const controls = [...element.current.querySelectorAll('button:not([disabled]), [tabindex="0"]')];
        const first = controls[0];
        const last = controls.at(-1);
        if (event.shiftKey && (document.activeElement === first || document.activeElement === element.current)) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === element.current)) {
          event.preventDefault();
          first?.focus();
        }
      }}
    >
      <Panel className="max-h-[94svh] w-full max-w-[100rem] overflow-y-auto">
        <PanelHeader
          title="人工確認雙鏡頭姿態"
          action={(
            <Button
              disabled={state.saving}
              onClick={onClose}
            >
              稍後處理
            </Button>
          )}
        />
        <div className="grid gap-4 p-5 max-sm:p-3">
          <h2
            id={titleId}
            className="m-0 text-base font-black text-white"
          >
            自動配對不足，分析已停在這個步驟
          </h2>
          <p className="m-0 text-sm font-semibold text-neutral-400">
            請在兩張影像標記同一個靜態位置，再新增下一組。至少需要 8 組；選擇分散且可辨識的盆器、土壤或背景位置，避開會移動的葉片。可放大影像，方向鍵也能微調標記。
          </p>
          {state.review?.reason ? (
            <p className="m-0 text-xs font-semibold text-neutral-500">{state.review.reason}</p>
          ) : null}
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
                  目前配對
                </label>
                <SelectMenu
                  id={selectId}
                  value={state.selected}
                  options={state.pairs.map((pair, index) => ({
                    value: index,
                    label: `第 ${index + 1} 組${pair.top && pair.side ? "（已標記）" : "（待標記）"}`,
                    disabled: locked,
                  }))}
                  onValueChange={(value) => { if (!locked) state.setSelected(Number(value)); }}
                />
                <span
                  className="text-sm font-bold text-neutral-400"
                  role="status"
                >
                  {`已完成 ${completed} 組 / 至少 ${state.review.minimum_pairs} 組`}
                </span>
              </div>
              <div className="grid min-w-0 gap-4 min-[800px]:grid-cols-2">
                {state.review.views.map((view) => (
                  <AnalysisRunStereoReviewImage
                    key={view.view_id}
                    analysisId={analysisId}
                    view={view}
                    pairs={state.pairs}
                    selected={state.selected}
                    disabled={locked}
                    onPointChange={state.changePoint}
                  />
                ))}
              </div>
              <ActionRow>
                <Button
                  disabled={locked || state.pairs.length >= 200}
                  onClick={state.addPair}
                >
                  新增配對
                </Button>
                <Button
                  disabled={locked}
                  onClick={state.removePair}
                >
                  清除目前配對
                </Button>
                <Button
                  variant="primary"
                  disabled={locked || incomplete || completed < state.review.minimum_pairs}
                  onClick={() => void state.submit()}
                >
                  {state.saving ? "驗證幾何並保存中…" : "驗證配對並繼續分析"}
                </Button>
              </ActionRow>
            </>
          ) : null}
        </div>
      </Panel>
    </div>,
    document.body,
  );
}
