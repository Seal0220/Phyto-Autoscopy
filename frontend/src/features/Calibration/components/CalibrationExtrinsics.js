"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  FiArchive,
  FiCamera,
  FiCheckCircle,
  FiCopy,
  FiDownload,
  FiEdit3,
  FiGitMerge,
  FiPlay,
  FiRefreshCw,
  FiSave,
  FiTarget,
  FiTrash2,
  FiUnlock,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import {
  NumericInput,
  TextInput,
} from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";
import {
  abortRequest,
  messageFromError,
} from "@/lib/httpUtils";
import { formatDateTime } from "@/lib/formatUtils";

import { requestUnifiedCalibration } from "../lib/unifiedCalibrationApiUtils";
import {
  CALIBRATION_CAMERAS,
  CALIBRATION_SUGGESTED_ANGLES,
} from "../calibrationConfig";
import { calibrationAngleCompleted } from "../lib/calibrationUtils";
import CalibrationExtrinsicCreate from "./CalibrationExtrinsicCreate";
import CalibrationStartButton from "./CalibrationStartButton";
import CalibrationQuality from "./CalibrationQuality";

const PROFILE_STATUS = {
  draft: {
    label: "草稿",
    tone: "neutral",
  },
  validating: {
    label: "待驗證",
    tone: "warning",
  },
  valid: {
    label: "有效",
    tone: "success",
  },
  invalid: {
    label: "無效",
    tone: "offline",
  },
  active: {
    label: "使用中",
    tone: "success",
  },
  archived: {
    label: "已封存",
    tone: "neutral",
  },
};

const RELOCATION_ITEMS = [
  ["arm_height", "旋臂高度改變"],
  ["rotating_mount", "旋臂相機重新安裝"],
  ["top_moved", "俯視相機移動"],
  ["side_moved", "側視相機移動"],
  ["rig_moved", "整套裝置搬移"],
  ["motor_zero", "馬達零點改變"],
];

function profileStatus(profile) {
  return PROFILE_STATUS[profile?.status] || PROFILE_STATUS.draft;
}

function qualityMetric(profile, key, suffix) {
  const value = Number(profile?.quality?.[key]);
  return Number.isFinite(value) ? `${value.toFixed(3)} ${suffix}` : "—";
}

function cameraLabel(cameraId) {
  return CALIBRATION_CAMERAS.find(
    (camera) => camera.id === cameraId,
  )?.label || cameraId;
}

export default function CalibrationExtrinsics({
  selectedBoardId,
  profiles,
  status,
  locked,
  pendingAction,
  systemActive,
  lockedByAnotherOperator,
  startDisabled,
  selectedProfileId,
  onSelectedProfileChange,
  onAction,
  onBeginCalibration,
  onEndCalibration,
  onNotify,
}) {
  const [observations, setObservations] = useState([]);
  const [profileName, setProfileName] = useState("");
  const [copyName, setCopyName] = useState("");
  const [relocationOpen, setRelocationOpen] = useState(false);
  const [relocationName, setRelocationName] = useState("");
  const [relocationHeight, setRelocationHeight] = useState("0");
  const [relocationItems, setRelocationItems] = useState([]);
  const observationsControllerRef = useRef(null);
  const profile = profiles.find(
    (item) => item.profile_id === selectedProfileId,
  ) || null;

  useEffect(() => {
    if (profile) return;
    const fallback = profiles.find((item) => item.is_active) || profiles[0];
    onSelectedProfileChange(fallback?.profile_id || "");
  }, [
    onSelectedProfileChange,
    profile,
    profiles,
  ]);

  useEffect(() => {
    setProfileName(profile?.name || "");
    setCopyName(profile ? `${profile.name} 複本` : "");
    setRelocationName(profile ? `${profile.name} 重定位` : "");
    setRelocationHeight(String(profile?.motion_model?.arm_height_mm || 0));
    setRelocationItems([]);
    setRelocationOpen(false);
  }, [profile?.profile_id]);

  const loadObservations = useCallback(async () => {
    abortRequest(
      observationsControllerRef.current,
      "已改為讀取另一組外參觀測。",
    );
    if (!selectedProfileId) {
      setObservations([]);
      return;
    }
    const controller = new AbortController();
    observationsControllerRef.current = controller;
    try {
      const payload = await requestUnifiedCalibration(
        `/api/calibration/extrinsics/${encodeURIComponent(selectedProfileId)}/observations`,
        {
          signal: controller.signal,
        },
      );
      if (!controller.signal.aborted) {
        setObservations(Array.isArray(payload) ? payload : []);
      }
    } catch (error) {
      if (error?.name !== "AbortError") {
        onNotify(
          messageFromError(error, "讀取外參觀測失敗。"),
          "error",
        );
      }
    } finally {
      if (observationsControllerRef.current === controller) {
        observationsControllerRef.current = null;
      }
    }
  }, [
    onNotify,
    selectedProfileId,
  ]);

  useEffect(() => {
    void loadObservations();
    return () => {
      abortRequest(observationsControllerRef.current);
      observationsControllerRef.current = null;
    };
  }, [loadObservations]);

  async function captureObservation() {
    if (!profile) return;
    const outcome = await onAction(
      "profile.capture",
      `/api/calibration/extrinsics/${encodeURIComponent(profile.profile_id)}/capture`,
      {
        body: {
          camera_ids: profile.camera_ids,
          motor_angle_deg: status?.motor_angle_deg,
          arm_height_mm: profile.motion_model?.arm_height_mm,
        },
        timeoutMs: 120_000,
        successMessage: "已完成一組外參同步觀測。",
      },
    );
    if (outcome?.result?.observation_id) {
      setObservations((current) => [
        ...current.filter(
          (item) => item.observation_id !== outcome.result.observation_id,
        ),
        outcome.result,
      ]);
    }
  }

  async function relocateProfile() {
    if (!profile) return;
    const outcome = await onAction(
      "profile.relocate",
      "/api/calibration/extrinsics/relocate",
      {
        body: {
          source_profile_id: profile.profile_id,
          name: relocationName.trim(),
          changed_items: relocationItems,
          arm_height_mm: relocationItems.includes("arm_height")
            ? Number(relocationHeight)
            : null,
        },
        successMessage: "已建立新的快速重定位校正檔，原校正檔未被覆寫。",
      },
    );
    if (outcome?.result?.profile_id) {
      onSelectedProfileChange(outcome.result.profile_id);
      setRelocationOpen(false);
    }
  }

  function toggleRelocationItem(item) {
    setRelocationItems((current) => current.includes(item)
      ? current.filter((value) => value !== item)
      : [...current, item]
    );
  }

  return (
    <section
      className="grid gap-4"
      aria-labelledby="calibration-extrinsics-title"
    >
      <SubsectionHeader
        titleId="calibration-extrinsics-title"
        title="外參校正與校正檔"
        description="所有參與相機共用一套觀測圖流程；不依相機數量拆分校正模式。"
      >
        {locked ? (
          <Button
            disabled={Boolean(pendingAction)}
            onClick={() => void onEndCalibration()}
          >
            <FiUnlock
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            結束校正
          </Button>
        ) : (
          <CalibrationStartButton
            disabled={
              lockedByAnotherOperator
              || startDisabled
              || Boolean(pendingAction)
            }
            systemActive={systemActive}
            onClick={() => void onBeginCalibration("extrinsic")}
          />
        )}
      </SubsectionHeader>

      <CalibrationExtrinsicCreate
        selectedBoardId={selectedBoardId}
        locked={locked}
        pendingAction={pendingAction}
        onCreated={onSelectedProfileChange}
        onAction={onAction}
      />

      <div
        className="grid max-h-96 min-h-0 content-start gap-3 overflow-y-auto overscroll-contain pr-1"
        role="list"
        aria-label="外參校正檔列表"
      >
        {profiles.length ? profiles.map((item) => {
          const selected = item.profile_id === selectedProfileId;
          const statusMeta = profileStatus(item);

          return (
            <InnerPanel
              as="article"
              className="grid-cols-[minmax(0,1fr)_auto] items-start max-[720px]:grid-cols-1"
              role="listitem"
              key={item.profile_id}
            >
              <div className="grid min-w-0 gap-3">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <h4 className="m-0 break-all text-sm font-black text-white">
                    {item.name}
                  </h4>
                  <StatusPill tone={statusMeta.tone}>
                    {statusMeta.label}
                  </StatusPill>
                  {item.is_active ? (
                    <StatusPill tone="success">目前啟用</StatusPill>
                  ) : null}
                </div>
                <dl className="grid gap-2 text-xs min-[520px]:grid-cols-2 min-[900px]:grid-cols-4">
                  <div>
                    <dt className="font-black text-neutral-500">參與相機</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {item.camera_ids.join("、")}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-black text-neutral-500">旋臂高度</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {Number(item.motion_model?.arm_height_mm || 0).toFixed(1)} mm
                    </dd>
                  </div>
                  <div>
                    <dt className="font-black text-neutral-500">重投影誤差</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {qualityMetric(item, "mean_reprojection_error_px", "px")}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-black text-neutral-500">更新時間</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {formatDateTime(item.updated_at)}
                    </dd>
                  </div>
                </dl>
              </div>
              <Button
                className="max-[720px]:w-full"
                variant={selected ? "default" : "primary"}
                disabled={selected}
                onClick={() => onSelectedProfileChange(item.profile_id)}
              >
                <FiTarget
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                {selected ? "已選擇" : "選擇"}
              </Button>
            </InnerPanel>
          );
        }) : (
          <InnerPanel role="listitem">
            <p className="m-0 py-4 text-center text-sm font-semibold text-neutral-400">
              尚無外參校正檔，請先建立一組參與相機與裝置配置。
            </p>
          </InnerPanel>
        )}
      </div>

      {profile ? (
        <InnerPanel className="content-start">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h4 className="m-0 mr-auto break-all text-base font-black text-white">
              {profile.name}
            </h4>
            <StatusPill tone={profileStatus(profile).tone}>
              {profileStatus(profile).label}
            </StatusPill>
            <StatusPill tone="neutral">
              {profile.observation_count} 組觀測
            </StatusPill>
          </div>

          <div className="grid gap-3 min-[720px]:grid-cols-[minmax(0,1fr)_auto]">
            <TextInput
              id="calibration-profile-rename"
              label="校正檔名稱"
              value={profileName}
              disabled={!locked || profile.is_active}
              onValueChange={setProfileName}
            />
            <Button
              className="self-end"
              disabled={
                !locked
                || profile.is_active
                || !profileName.trim()
                || profileName.trim() === profile.name
                || Boolean(pendingAction)
              }
              onClick={() => void onAction(
                "profile.rename",
                `/api/calibration/extrinsics/${encodeURIComponent(profile.profile_id)}`,
                {
                  method: "PATCH",
                  body: {
                    name: profileName.trim(),
                  },
                  successMessage: "外參校正檔已重新命名。",
                },
              )}
            >
              <FiEdit3
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              重新命名
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-black text-neutral-400">
              建議旋臂角度
            </span>
            {CALIBRATION_SUGGESTED_ANGLES.map((angle) => (
              <StatusPill
                tone={calibrationAngleCompleted(observations, angle) ? "success" : "neutral"}
                key={angle}
              >
                {angle}° {calibrationAngleCompleted(observations, angle) ? "已完成" : "未完成"}
              </StatusPill>
            ))}
          </div>

          {observations.length ? (
            <div
              className="grid max-h-56 gap-2 overflow-y-auto overscroll-contain pr-1"
              role="list"
              aria-label="外參觀測品質"
            >
              {[...observations].reverse().map((observation) => {
                const detections = Object.entries(observation.detections || {});
                const visibleCameras = detections
                  .filter(([, detection]) => detection.board_detected)
                  .map(([cameraId]) => cameraLabel(cameraId));
                const readyCount = detections.filter(
                  ([, detection]) => detection.capture_ready,
                ).length;

                return (
                  <div
                    className="grid gap-2 rounded-xl border border-white/10 bg-black/10 p-3 text-xs min-[720px]:grid-cols-[auto_minmax(0,1fr)_auto] min-[720px]:items-center"
                    role="listitem"
                    key={observation.observation_id}
                  >
                    <StatusPill tone={observation.accepted ? "success" : "warning"}>
                      {Number.isFinite(Number(observation.motor_angle_deg))
                        ? `${Number(observation.motor_angle_deg).toFixed(1)}°`
                        : "未記錄角度"
                      }
                    </StatusPill>
                    <span className="min-w-0 font-bold text-neutral-300">
                      可見相機：{visibleCameras.length
                        ? visibleCameras.join("、")
                        : "無"
                      }
                    </span>
                    <span className="font-black text-neutral-400">
                      符合擷取品質 {readyCount} / {detections.length}
                    </span>
                    {observation.rejection_reason ? (
                      <span className="text-amber-200 min-[720px]:col-span-3">
                        {observation.rejection_reason}
                      </span>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : null}

          <div className="flex flex-wrap justify-end gap-2">
            <Button
              variant="primary"
              disabled={
                !locked
                || profile.is_active
                || profile.status === "archived"
                || Boolean(pendingAction)
              }
              onClick={() => void captureObservation()}
            >
              <FiCamera
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              同步擷取觀測
            </Button>
            <Button
              disabled={
                !locked
                || profile.is_active
                || profile.status === "archived"
                || profile.observation_count < 1
                || Boolean(pendingAction)
              }
              onClick={() => void onAction(
                "profile.solve",
                `/api/calibration/extrinsics/${encodeURIComponent(profile.profile_id)}/solve`,
                {
                  timeoutMs: 180_000,
                  successMessage: "外參、旋轉軸與世界座標計算完成。",
                },
              )}
            >
              <FiGitMerge
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              計算外參
            </Button>
            <Button
              disabled={
                !locked
                || profile.status !== "validating"
                || Boolean(pendingAction)
              }
              onClick={() => void onAction(
                "profile.validate",
                `/api/calibration/extrinsics/${encodeURIComponent(profile.profile_id)}/validate`,
                {
                  successMessage: "外參品質驗證完成。",
                },
              )}
            >
              <FiCheckCircle
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              驗證品質
            </Button>
            <Button
              disabled={
                !locked
                || profile.status !== "valid"
                || Boolean(pendingAction)
              }
              onClick={() => void onAction(
                "profile.activate",
                `/api/calibration/extrinsics/${encodeURIComponent(profile.profile_id)}/activate`,
                {
                  successMessage: "此外參校正檔已設為目前啟用。",
                },
              )}
            >
              <FiPlay
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              設為啟用
            </Button>
            <Button
              onClick={() => {
                const anchor = document.createElement("a");
                anchor.href = `/api/calibration/extrinsics/${encodeURIComponent(profile.profile_id)}/export`;
                anchor.download = `${profile.profile_id}.zip`;
                anchor.click();
              }}
            >
              <FiDownload
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              匯出
            </Button>
          </div>

          <div className="grid gap-3 min-[720px]:grid-cols-[minmax(0,1fr)_auto]">
            <TextInput
              id="calibration-profile-copy-name"
              label="複本名稱"
              value={copyName}
              disabled={!locked}
              onValueChange={setCopyName}
            />
            <Button
              className="self-end"
              disabled={!locked || !copyName.trim() || Boolean(pendingAction)}
              onClick={async () => {
                const outcome = await onAction(
                  "profile.copy",
                  `/api/calibration/extrinsics/${encodeURIComponent(profile.profile_id)}/copy`,
                  {
                    body: {
                      name: copyName.trim(),
                    },
                    successMessage: "已建立外參校正檔複本。",
                  },
                );
                if (outcome?.result?.profile_id) {
                  onSelectedProfileChange(outcome.result.profile_id);
                }
              }}
            >
              <FiCopy
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              複製校正檔
            </Button>
          </div>

          <div className="flex flex-wrap justify-end gap-2">
            <Button
              disabled={!locked || Boolean(pendingAction)}
              onClick={() => setRelocationOpen((current) => !current)}
            >
              <FiRefreshCw
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              {relocationOpen ? "取消快速重定位" : "快速外參重定位"}
            </Button>
            <Button
              disabled={
                !locked
                || profile.is_active
                || profile.status === "archived"
                || Boolean(pendingAction)
              }
              onClick={() => void onAction(
                "profile.archive",
                `/api/calibration/extrinsics/${encodeURIComponent(profile.profile_id)}/archive`,
                {
                  successMessage: "外參校正檔已封存。",
                },
              )}
            >
              <FiArchive
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              封存
            </Button>
            <Button
              variant="dangerGhost"
              disabled={
                !locked
                || profile.is_active
                || Boolean(pendingAction)
              }
              onClick={async () => {
                const outcome = await onAction(
                  "profile.delete",
                  `/api/calibration/extrinsics/${encodeURIComponent(profile.profile_id)}`,
                  {
                    method: "DELETE",
                    successMessage: "外參校正檔已刪除。",
                  },
                );
                if (outcome) onSelectedProfileChange("");
              }}
            >
              <FiTrash2
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              刪除
            </Button>
          </div>

          {relocationOpen ? (
            <div className="grid gap-3 border-t border-white/10 pt-4">
              <div className="grid gap-3 min-[720px]:grid-cols-2">
                <TextInput
                  id="calibration-relocation-name"
                  label="新校正檔名稱"
                  value={relocationName}
                  onValueChange={setRelocationName}
                />
                <NumericInput
                  id="calibration-relocation-height"
                  label="新旋臂高度"
                  value={relocationHeight}
                  min={0}
                  max={10000}
                  step={1}
                  suffix="mm"
                  disabled={!relocationItems.includes("arm_height")}
                  onValueChange={setRelocationHeight}
                />
              </div>
              <div className="grid gap-3 min-[520px]:grid-cols-2 min-[960px]:grid-cols-3">
                {RELOCATION_ITEMS.map(([value, label]) => (
                  <ToggleRow
                    checked={relocationItems.includes(value)}
                    label={label}
                    onClick={() => toggleRelocationItem(value)}
                    key={value}
                  />
                ))}
              </div>
              <div className="flex justify-end">
                <Button
                  variant="primary"
                  disabled={
                    !relocationName.trim()
                    || !relocationItems.length
                    || Boolean(pendingAction)
                  }
                  onClick={() => void relocateProfile()}
                >
                  <FiSave
                    className="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  建立重定位校正檔
                </Button>
              </div>
            </div>
          ) : null}

          <CalibrationQuality profile={profile} />
        </InnerPanel>
      ) : null}
    </section>
  );
}
