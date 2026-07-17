"use client";

import { useRouter } from "next/navigation";
import {
  FiArrowLeft,
  FiRefreshCw,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import StatusCard from "@/components/cards/StatusCard";
import RetryMessage from "@/components/feedback/RetryMessage";
import {
  Panel,
  PanelHeader,
} from "@/components/panels/Panel";
import MainNavigation from "@/features/MainNavigation/MainNavigation";

import CalibrationCreateForm from "./components/CalibrationCreateForm";
import CalibrationProfileList from "./components/CalibrationProfileList";
import useCalibrationCatalog from "./hooks/useCalibrationCatalog";

export default function Calibration() {
  const router = useRouter();
  const {
    profiles,
    sourceImages,
    loading,
    loadError,
    createPending,
    createError,
    createRequiresRefresh,
    load,
    create,
    clearCreateError,
  } = useCalibrationCatalog();
  const validCount = profiles.filter((profile) => profile.valid).length;
  const staleCount = profiles.filter(
    (profile) => profile.potentially_invalid_reasons?.length,
  ).length;
  const hasCatalog = profiles.length > 0 || sourceImages.length > 0;

  async function handleCreate(payload) {
    const profile = await create(payload);
    if (profile?.calibration_id) {
      router.push(`/analysis/calibration/${encodeURIComponent(profile.calibration_id)}`);
    }
  }

  return (
    <main className="min-h-screen bg-[#06100c] px-5 pb-8 max-sm:px-3">
      <MainNavigation />

      <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-[5.6rem] max-[980px]:pt-[8.8rem]">
        <Panel aria-label="相機校正">
          <PanelHeader
            title="相機校正"
            action={(
              <div className="flex flex-wrap items-center justify-end gap-2">
                <Button onClick={() => router.push("/analysis")}>
                  <FiArrowLeft
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  返回分析
                </Button>
                <Button
                  disabled={loading || createPending}
                  onClick={() => void load()}
                >
                  <FiRefreshCw
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  {loading ? "讀取中…" : "重新讀取"}
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

            {loading && !hasCatalog ? (
              <div
                className="grid min-h-32 place-items-center rounded-xl border border-white/10 bg-black/10 p-4 text-sm font-semibold text-neutral-400"
                role="status"
              >
                讀取校正資料與來源影像中…
              </div>
            ) : null}

            {(!loadError || hasCatalog) && (!loading || hasCatalog) ? (
              <div className="grid gap-3 min-[520px]:grid-cols-3">
                <StatusCard
                  title="校正檔案"
                  content={profiles.length}
                  note="組"
                />
                <StatusCard
                  title="有效校正"
                  content={validCount}
                  note="組"
                />
                <StatusCard
                  title="可能失效"
                  content={staleCount}
                  note="組"
                />
              </div>
            ) : null}
          </div>
        </Panel>

        {(!loadError || hasCatalog) && (!loading || hasCatalog) ? (
          <Panel aria-label="校正檔案清單">
            <div className="grid gap-5 p-5 max-sm:p-4">
              <CalibrationProfileList profiles={profiles} />
            </div>
          </Panel>
        ) : null}

        {(!loadError || hasCatalog) && (!loading || hasCatalog) ? (
          <Panel aria-label="建立相機校正">
            <PanelHeader title="建立相機校正" />
            <div className="grid gap-5 p-5 max-sm:p-4">
              <CalibrationCreateForm
                sourceImages={sourceImages}
                pending={createPending}
                error={createError}
                requiresRefresh={createRequiresRefresh}
                onCreate={handleCreate}
                onClearError={clearCreateError}
                onRefresh={() => void load()}
              />
            </div>
          </Panel>
        ) : null}
      </div>
    </main>
  );
}
