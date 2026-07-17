"use client";

import { useRouter } from "next/navigation";
import {
  FiArrowLeft,
  FiRefreshCw,
  FiTrash2,
  FiX,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import {
  Panel,
  PanelHeader,
} from "@/components/panels/Panel";
import MainNavigation from "@/features/MainNavigation/MainNavigation";

import CalibrationMatrices from "./components/CalibrationMatrices";
import CalibrationPreviewGallery from "./components/CalibrationPreviewGallery";
import CalibrationQualityReport from "./components/CalibrationQualityReport";
import CalibrationSummary from "./components/CalibrationSummary";
import CalibrationWorkflowActions from "./components/CalibrationWorkflowActions";
import useCalibrationDetail from "./hooks/useCalibrationDetail";

export default function CalibrationDetail({ calibrationId }) {
  const router = useRouter();
  const {
    profile,
    report,
    loading,
    loadError,
    actionPending,
    actionError,
    actionRequiresRefresh,
    load,
    runStep,
    remove,
    clearActionError,
  } = useCalibrationDetail(calibrationId);

  async function handleDelete() {
    const confirmed = window.confirm(
      `確定刪除 ${calibrationId}？\n\n已被分析引用的校正檔案不會被刪除；此操作成功後無法復原。`,
    );
    if (!confirmed) return;
    const deleted = await remove();
    if (deleted) {
      router.replace("/analysis/calibration");
    }
  }

  return (
    <main className="min-h-screen bg-[#06100c] px-5 pb-8 max-sm:px-3">
      <MainNavigation />

      <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-[5.6rem] max-[980px]:pt-[8.8rem]">
        <Panel aria-label="相機校正詳細資料">
          <PanelHeader
            title="校正檔案"
            action={(
              <div className="flex flex-wrap items-center justify-end gap-2">
                <Button onClick={() => router.push("/analysis/calibration")}>
                  <FiArrowLeft
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  返回校正清單
                </Button>
                <Button
                  disabled={loading || Boolean(actionPending)}
                  onClick={() => void load()}
                >
                  <FiRefreshCw
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  {loading ? "讀取中…" : "重新讀取"}
                </Button>
                <Button
                  variant="danger"
                  disabled={
                    loading
                    || Boolean(actionPending)
                    || actionRequiresRefresh
                  }
                  onClick={() => void handleDelete()}
                >
                  <FiTrash2
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  {actionPending === "delete" ? "刪除中…" : "刪除校正"}
                </Button>
              </div>
            )}
          />

          <div className="grid gap-4 p-5 max-sm:p-4">
            <p className="m-0 break-all text-sm font-bold text-neutral-300">
              {calibrationId}
            </p>

            {loadError ? (
              <RetryMessage
                message={loadError}
                onRetry={() => void load()}
                retrying={loading}
              />
            ) : null}

            {loading && !profile ? (
              <div
                className="grid min-h-36 place-items-center rounded-xl border border-white/10 bg-black/10 p-4 text-sm font-semibold text-neutral-400"
                role="status"
              >
                讀取校正檔案與品質報告中…
              </div>
            ) : null}

            {actionError ? (
              <div
                className="grid gap-3 rounded-xl border border-rose-300/30 bg-rose-500/10 p-3"
                role="alert"
              >
                <p className="m-0 text-sm font-semibold text-rose-200">
                  {actionError}
                </p>
                <div className="flex flex-wrap justify-end gap-2">
                  {!actionRequiresRefresh ? (
                    <Button onClick={clearActionError}>
                      <FiX
                        className="size-4 shrink-0"
                        aria-hidden="true"
                      />
                      清除錯誤
                    </Button>
                  ) : null}
                  {actionRequiresRefresh ? (
                    <Button
                      variant="primary"
                      onClick={() => void load()}
                    >
                      <FiRefreshCw
                        className="size-4 shrink-0"
                        aria-hidden="true"
                      />
                      重新讀取並確認
                    </Button>
                  ) : null}
                </div>
              </div>
            ) : null}

            {profile?.last_error ? (
              <div
                className="rounded-xl border border-rose-300/30 bg-rose-500/10 p-3 text-sm font-semibold text-rose-200"
                role="alert"
              >
                上次校正錯誤：{profile.last_error}
              </div>
            ) : null}
          </div>
        </Panel>

        {profile ? (
          <Panel aria-label="校正摘要">
            <PanelHeader title="校正摘要" />
            <div className="grid gap-5 p-5 max-sm:p-4">
              <CalibrationSummary profile={profile} />
            </div>
          </Panel>
        ) : null}

        {profile ? (
          <Panel aria-label="校正工作流">
            <PanelHeader title="校正工作流" />
            <div className="grid gap-5 p-5 max-sm:p-4">
              <CalibrationWorkflowActions
                profile={profile}
                pending={actionPending}
                requiresRefresh={actionRequiresRefresh}
                onRun={(step) => void runStep(step)}
              />
            </div>
          </Panel>
        ) : null}

        {profile ? (
          <Panel aria-label="棋盤角點預覽">
            <PanelHeader title="角點預覽" />
            <div className="grid gap-5 p-5 max-sm:p-4">
              <CalibrationPreviewGallery profile={profile} />
            </div>
          </Panel>
        ) : null}

        {profile ? (
          <Panel aria-label="校正矩陣">
            <PanelHeader title="校正矩陣" />
            <div className="grid gap-5 p-5 max-sm:p-4">
              <CalibrationMatrices profile={profile} />
            </div>
          </Panel>
        ) : null}

        {report ? (
          <Panel aria-label="校正品質報告">
            <PanelHeader title="校正品質報告" />
            <div className="grid gap-5 p-5 max-sm:p-4">
              <CalibrationQualityReport report={report} />
            </div>
          </Panel>
        ) : null}
      </div>
    </main>
  );
}
