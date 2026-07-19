"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  FiArrowLeft,
  FiDownload,
  FiX,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import StatusCard from "@/components/cards/StatusCard";
import RetryMessage from "@/components/feedback/RetryMessage";
import InnerPanel from "@/components/panels/InnerPanel";
import {
  Panel,
  PanelHeader,
  StatusPill,
} from "@/components/panels/Panel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import MainNavigation from "@/features/MainNavigation/MainNavigation";
import ReprojectionErrors from "@/features/ReprojectionErrors/ReprojectionErrors";
import { analysisRunDisplay } from "@/features/AnalysisRun/lib/analysisRunUtils";
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";

import TrajectoryViewer2D from "./components/TrajectoryViewer2D";
import TrajectoryViewer3D from "./components/TrajectoryViewer3D";
import TrajectoryViewerDetectionSummary from "./components/TrajectoryViewerDetectionSummary";
import useTrajectoryResults from "./hooks/useTrajectoryResults";
import { analysisImageResolution } from "./lib/trajectoryUtils";

export default function TrajectoryViewer({
  analysisId,
}) {
  const router = useRouter();
  const { showNotification } = useNotificationsContext();
  const {
    run,
    trajectory,
    errors,
    summary,
    calibration,
    frameOverlay,
    loading,
    loadError,
    exportPending,
    exportError,
    load,
    downloadExport,
    clearExportError,
  } = useTrajectoryResults({
    analysisId,
  });

  useEffect(() => {
    const error = exportError || loadError;
    if (error) showNotification(error, "error");
  }, [
    exportError,
    loadError,
    showNotification,
  ]);
  const manualPoints = trajectory.filter((point) => (
    point.topType === "Manual" || point.sideType === "Manual"
  )).length;
  const highErrorPoints = trajectory.filter((point) => (
    point.topError > 10 || point.sideError > 10
  )).length;
  const runDisplay = analysisRunDisplay(run);
  const topResolution = analysisImageResolution(
    run,
    calibration,
    "top",
  );
  const sideResolution = analysisImageResolution(
    run,
    calibration,
    "side",
  );

  return (
    <main className="min-h-screen bg-[#06100c] px-5 pb-8 max-sm:px-3">
      <MainNavigation />

      <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-[5.6rem] max-[980px]:pt-[8.8rem]">
        <Panel aria-label="分析結果">
          <PanelHeader
            title="分析結果"
            action={(
              <div className="flex flex-wrap items-center justify-end gap-2">
                {run ? (
                  <StatusPill tone={runDisplay.status.tone}>
                    {runDisplay.status.label}
                  </StatusPill>
                ) : null}
                <Button onClick={() => router.push(
                  `/analysis/${encodeURIComponent(analysisId)}`,
                )}>
                  <FiArrowLeft
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  返回分析執行
                </Button>
                <Button
                  variant="primary"
                  disabled={exportPending || !run}
                  onClick={() => void downloadExport()}
                >
                  <FiDownload
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  {exportPending ? "匯出中…" : "匯出結果"}
                </Button>
              </div>
            )}
          />

          <div className="grid gap-4 p-5 max-sm:p-4">
            {loadError ? (
              <RetryMessage
                message={loadError}
                onRetry={() => void load()}
                retrying={loading}
              />
            ) : null}

            {loading && !run ? (
              <div
                className="grid min-h-36 place-items-center rounded-xl border border-white/10 bg-black/10 p-4 text-sm font-semibold text-neutral-400"
                role="status"
              >
                讀取分析結果中…
              </div>
            ) : null}

            {exportError ? (
              <div
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-xl border border-rose-300/30 bg-rose-500/10 p-3"
                role="alert"
              >
                <p className="m-0 text-sm font-semibold text-rose-200">
                  {exportError}
                </p>
                <Button onClick={clearExportError}>
                  <FiX
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  清除錯誤
                </Button>
              </div>
            ) : null}

            {run ? (
              <>
                <div className="grid gap-3 min-[520px]:grid-cols-2 min-[900px]:grid-cols-4">
                  <StatusCard
                    title="有效三維點"
                    content={trajectory.length}
                    note="個影格"
                  />
                  <StatusCard
                    title="人工修正點"
                    content={manualPoints}
                    note="個三維點"
                  />
                  <StatusCard
                    title="高誤差點"
                    content={highErrorPoints}
                    note="> 10 px"
                  />
                  <StatusCard
                    title="相機校正"
                    content={calibration?.valid ? "有效" : "需確認"}
                    note={run.calibration_id || "—"}
                  />
                </div>

                {trajectory.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-white/10 bg-black/10 p-5 text-center text-sm font-semibold text-neutral-400">
                    本次分析沒有可顯示的有效三維軌跡。
                  </div>
                ) : (
                  <>
                    <div className="grid gap-4 min-[980px]:grid-cols-2">
                      <TrajectoryViewer2D
                        analysisId={analysisId}
                        cameraId="top"
                        imageHeight={topResolution[1]}
                        imageWidth={topResolution[0]}
                        overlay={frameOverlay?.top}
                        trajectory={trajectory}
                      />
                      <TrajectoryViewer2D
                        analysisId={analysisId}
                        cameraId="side"
                        imageHeight={sideResolution[1]}
                        imageWidth={sideResolution[0]}
                        overlay={frameOverlay?.side}
                        trajectory={trajectory}
                      />
                    </div>

                    <TrajectoryViewer3D
                      calibration={calibration}
                      trajectory={trajectory}
                    />
                  </>
                )}

                {summary ? (
                  <TrajectoryViewerDetectionSummary summary={summary} />
                ) : null}

                <ReprojectionErrors
                  errors={errors}
                  summary={summary}
                />

                <div className="grid gap-4 min-[900px]:grid-cols-2">
                  <InnerPanel>
                    <SubsectionHeader
                      title="論文比較基準"
                      description="以下是 Ruiz-Melero et al. 2024 的報告值，只供方法重現比較。"
                    />
                    <dl className="grid gap-3 text-sm min-[520px]:grid-cols-2">
                      <div>
                        <dt className="font-black text-neutral-400">尖端正確取得率</dt>
                        <dd className="mt-1 font-bold text-neutral-100">86% 至 98%</dd>
                      </div>
                      <div>
                        <dt className="font-black text-neutral-400">平均重投影誤差</dt>
                        <dd className="mt-1 font-bold text-neutral-100">約 3.7 px</dd>
                      </div>
                      <div>
                        <dt className="font-black text-neutral-400">推估三維定位誤差</dt>
                        <dd className="mt-1 font-bold text-neutral-100">約 0.5 cm</dd>
                      </div>
                      <div>
                        <dt className="font-black text-neutral-400">人工修正比例</dt>
                        <dd className="mt-1 font-bold text-neutral-100">約 8.3%</dd>
                      </div>
                    </dl>
                    <p className="m-0 text-xs font-semibold leading-5 text-amber-200">
                      這些數值不是 CHLOROCULUS 的通過門檻，也不保證本次資料可達到相同表現。
                    </p>
                  </InnerPanel>

                  <InnerPanel>
                    <SubsectionHeader
                      title="研究解讀限制"
                      description="本頁呈現可追溯的觀測與測量結果。"
                    />
                    <p className="m-0 text-sm font-semibold leading-6 text-neutral-300">
                      三維軌跡、偵測比例與重投影誤差只能描述此資料中的植物尖端運動與量測品質，不能直接推論植物具有或不具有意識、意圖或行為目的。後續研究必須結合可重現的實驗設計與其他證據。
                    </p>
                    <p className="m-0 text-xs font-semibold leading-5 text-neutral-500">
                      結果可能受相機解析度、鏡頭、位置、光照、背景、校正覆蓋、遮擋與影像同步影響。
                    </p>
                  </InnerPanel>
                </div>
              </>
            ) : null}

          </div>
        </Panel>
      </div>
    </main>
  );
}
