"use client";

import { useRouter } from "next/navigation";
import {
  FiCrosshair,
  FiPlus,
  FiRefreshCw,
  FiX,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import StatusCard from "@/components/cards/StatusCard";
import RetryMessage from "@/components/feedback/RetryMessage";
import {
  Panel,
  PanelHeader,
} from "@/components/panels/Panel";
import MainNavigation from "@/features/MainNavigation/MainNavigation";

import AnalysisDashboardRuns from "./components/AnalysisDashboardRuns";
import AnalysisDashboardSources from "./components/AnalysisDashboardSources";
import useAnalysisDashboard from "./hooks/useAnalysisDashboard";

export default function Analysis() {
  const router = useRouter();
  const {
    sources,
    runs,
    loading,
    loadError,
    exportingIds,
    exportFailure,
    connection,
    socketError,
    load,
    exportRun,
    resetSocketError,
    clearExportFailure,
  } = useAnalysisDashboard();
  const readySourceCount = sources.filter((source) => source.ready).length;
  const activeRunCount = runs.filter((run) => [
    "validating",
    "processing",
    "needs_review",
    "reviewing",
    "reconstructing",
  ].includes(run.status)).length;
  const hasData = sources.length > 0 || runs.length > 0;

  function openNewAnalysis(recordId = "") {
    const query = recordId
      ? `?record=${encodeURIComponent(recordId)}`
      : "";
    router.push(`/analysis/new${query}`);
  }

  return (
    <main className="min-h-screen bg-[#06100c] px-5 pb-8 max-sm:px-3">
      <MainNavigation isConnected={connection === "connected"} />

      <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-[5.6rem] max-[980px]:pt-[8.8rem]">
        <Panel aria-label="分析總覽">
          <PanelHeader
            title="分析"
            action={(
              <div className="flex flex-wrap items-center justify-end gap-2">
                <Button onClick={() => router.push("/analysis/calibration")}>
                  <FiCrosshair
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  相機校正
                </Button>
                <Button
                  disabled={loading}
                  onClick={() => void load()}
                >
                  <FiRefreshCw
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  {loading ? "讀取中…" : "重新整理"}
                </Button>
                <Button
                  variant="primary"
                  onClick={() => openNewAnalysis()}
                >
                  <FiPlus
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  新增分析
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

            {socketError ? (
              <div
                className="flex min-w-0 flex-wrap items-center gap-3 rounded-xl border border-amber-200/30 bg-amber-500/10 p-3"
                role="alert"
              >
                <p className="m-0 min-w-0 flex-1 text-sm font-semibold text-amber-200">
                  {socketError.message} 分析進度仍會定時重新讀取。
                </p>
                <Button onClick={resetSocketError}>
                  <FiX
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  清除連線錯誤
                </Button>
              </div>
            ) : null}

            {!loadError || hasData ? (
              <div className="grid gap-3 min-[520px]:grid-cols-3">
                <StatusCard
                  title="捕捉紀錄"
                  content={sources.length}
                  note="筆"
                />
                <StatusCard
                  title="可分析紀錄"
                  content={readySourceCount}
                  note="筆"
                />
                <StatusCard
                  title="進行中分析"
                  content={activeRunCount}
                  note="個"
                />
              </div>
            ) : null}
          </div>
        </Panel>

        {(!loadError || hasData) ? (
          <>
            <AnalysisDashboardSources
              sources={sources}
              onCreate={openNewAnalysis}
            />
            <AnalysisDashboardRuns
              runs={runs}
              exportingIds={exportingIds}
              exportFailure={exportFailure}
              onClearExportError={clearExportFailure}
              onExport={(analysisId) => void exportRun(analysisId)}
              onOpen={(analysisId) => router.push(
                `/analysis/${encodeURIComponent(analysisId)}`,
              )}
              onReview={(analysisId) => router.push(
                `/analysis/${encodeURIComponent(analysisId)}/review`,
              )}
              onResults={(analysisId) => router.push(
                `/analysis/${encodeURIComponent(analysisId)}/results`,
              )}
            />
          </>
        ) : null}
      </div>
    </main>
  );
}
