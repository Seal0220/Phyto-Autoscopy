"use client";

import {
  useEffect,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  FiPlus,
  FiRefreshCw,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import StatusCard from "@/components/cards/StatusCard";
import {
  Panel,
  PanelHeader,
} from "@/components/panels/Panel";
import SettingsGear from "@/components/panels/SettingsGear";
import MainNavigation from "@/features/MainNavigation/MainNavigation";
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";

import AnalysisDashboardRuns from "./components/AnalysisDashboardRuns";
import ArucoWorldSettings from "./components/ArucoWorldSettings";
import useAnalysisDashboard from "./hooks/useAnalysisDashboard";

export default function Analysis() {
  const router = useRouter();
  const { showNotification } = useNotificationsContext();
  const [poseSettingsOpen, setPoseSettingsOpen] = useState(false);
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
  const activeRunCount = runs.filter((run) => [
    "validating",
    "processing",
    "needs_review",
    "reviewing",
    "reconstructing",
  ].includes(run.status)).length;
  const hasData = sources.length > 0 || runs.length > 0;

  useEffect(() => {
    if (loadError) showNotification(loadError, "error");
  }, [
    loadError,
    showNotification,
  ]);

  useEffect(() => {
    if (!socketError) return;
    showNotification(
      `${socketError.message} 分析進度仍會定時重新讀取。`,
      "error",
    );
    resetSocketError();
  }, [
    resetSocketError,
    showNotification,
    socketError,
  ]);

  useEffect(() => {
    if (exportFailure?.message) {
      showNotification(exportFailure.message, "error");
    }
  }, [
    exportFailure,
    showNotification,
  ]);

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
            {!loadError || hasData ? (
              <div className="grid gap-3 min-[520px]:grid-cols-2">
                <StatusCard
                  title="捕捉紀錄"
                  content={sources.length}
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

        <Panel aria-label="ArUco 基準">
          <PanelHeader
            title="ArUco 基準"
            action={(
              <SettingsGear
                label="ArUco 基準"
                open={poseSettingsOpen}
                onClick={() => setPoseSettingsOpen((current) => !current)}
              />
            )}
          />
          <ArucoWorldSettings
            open={poseSettingsOpen}
            onNotify={showNotification}
          />
        </Panel>

        {(!loadError || hasData) ? (
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
        ) : null}
      </div>
    </main>
  );
}
