"use client";

import { useState } from "react";
import { FiPlus, FiSave } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import {
  NumericInput,
  SelectInput,
  TextInput,
} from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";

import { CALIBRATION_CAMERAS } from "../calibrationConfig";

const WORLD_ORIGIN_OPTIONS = [
  {
    value: "platform_center",
    label: "植物平台中心",
  },
  {
    value: "board_fixture",
    label: "校正板固定定位座",
  },
  {
    value: "custom_offset",
    label: "自訂原點偏移",
  },
];

function initialCameras() {
  return Object.fromEntries(CALIBRATION_CAMERAS.map((camera) => [
    camera.id,
    {
      enabled: true,
      position_label: "",
      height_mm: "0",
      offset_x_mm: "0",
      offset_y_mm: "0",
      offset_z_mm: "0",
      mount_description: "",
      is_movable: camera.id === "rotating",
    },
  ]));
}

export default function CalibrationExtrinsicCreate({
  selectedBoardId,
  locked,
  pendingAction,
  onCreated,
  onAction,
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [cameras, setCameras] = useState(initialCameras);
  const [motion, setMotion] = useState({
    arm_height_mm: "0",
    arm_radius_mm: "0",
    minimum_angle_deg: "0",
    maximum_angle_deg: "360",
  });
  const [world, setWorld] = useState({
    origin_definition: "platform_center",
    origin_x_mm: "0",
    origin_y_mm: "0",
    origin_z_mm: "0",
    platform_height_mm: "0",
  });

  function updateCamera(
    cameraId,
    key,
    value,
  ) {
    setCameras((current) => ({
      ...current,
      [cameraId]: {
        ...current[cameraId],
        [key]: value,
      },
    }));
  }

  async function createProfile() {
    const cameraIds = CALIBRATION_CAMERAS
      .map((camera) => camera.id)
      .filter((cameraId) => cameras[cameraId].enabled);
    const outcome = await onAction(
      "profile.create",
      "/api/calibration/extrinsics",
      {
        body: {
          name: name.trim(),
          board_profile_id: selectedBoardId,
          camera_ids: cameraIds,
          cameras: cameraIds.map((cameraId) => ({
            camera_id: cameraId,
            position_label: cameras[cameraId].position_label.trim(),
            height_mm: Number(cameras[cameraId].height_mm),
            offset_x_mm: Number(cameras[cameraId].offset_x_mm),
            offset_y_mm: Number(cameras[cameraId].offset_y_mm),
            offset_z_mm: Number(cameras[cameraId].offset_z_mm),
            mount_description: cameras[cameraId].mount_description.trim(),
            is_movable: cameras[cameraId].is_movable,
          })),
          motion_model: {
            arm_height_mm: Number(motion.arm_height_mm),
            arm_radius_mm: Number(motion.arm_radius_mm),
            usable_angle_range_deg: [
              Number(motion.minimum_angle_deg),
              Number(motion.maximum_angle_deg),
            ],
          },
          world_alignment: {
            origin_definition: world.origin_definition,
            origin_offset_mm: [
              Number(world.origin_x_mm),
              Number(world.origin_y_mm),
              Number(world.origin_z_mm),
            ],
            x_axis_definition: "平台水平方向",
            y_axis_definition: "平台深度方向",
            z_axis_definition: "垂直向上",
            plant_center_mm: [0, 0, 0],
            platform_height_mm: Number(world.platform_height_mm),
            unit: "mm",
          },
          notes: notes.trim(),
        },
        successMessage: "已建立外參校正檔。",
      },
    );
    if (!outcome?.result?.profile_id) return;
    onCreated(outcome.result.profile_id);
    setCreating(false);
    setName("");
  }

  const enabledCount = Object.values(cameras).filter(
    (camera) => camera.enabled,
  ).length;

  return (
    <section className="grid gap-3">
      <SubsectionHeader
        title="建立外參校正檔"
        description="以一組任意參與相機集合建立觀測圖；手動量測僅作先驗，矩陣仍由影像求解。"
      >
        <Button
          disabled={!locked || Boolean(pendingAction)}
          onClick={() => setCreating((current) => !current)}
        >
          <FiPlus
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {creating ? "取消建立" : "建立校正檔"}
        </Button>
      </SubsectionHeader>

      {creating ? (
        <div className="grid gap-4 border-t border-white/10 pt-4">
          <div className="grid gap-3">
            <TextInput
              id="calibration-profile-name"
              label="校正檔名稱"
              value={name}
              onValueChange={setName}
            />
          </div>

          <div className="grid gap-3 min-[760px]:grid-cols-3">
            {CALIBRATION_CAMERAS.map((camera) => {
              const current = cameras[camera.id];

              return (
                <div
                  className="grid content-start gap-3 rounded-[22px] border border-white/10 bg-black/10 p-4"
                  key={camera.id}
                >
                  <ToggleRow
                    checked={current.enabled}
                    label={`${camera.label}（${camera.id}）`}
                    description="決定此相機是否參與這組外參觀測圖。"
                    onClick={() => updateCamera(
                      camera.id,
                      "enabled",
                      !current.enabled,
                    )}
                  />
                  <TextInput
                    id={`calibration-${camera.id}-position-label`}
                    label="安裝位置名稱"
                    value={current.position_label}
                    disabled={!current.enabled}
                    onValueChange={(value) => updateCamera(
                      camera.id,
                      "position_label",
                      value,
                    )}
                  />
                  <NumericInput
                    id={`calibration-${camera.id}-height`}
                    label="相機高度"
                    value={current.height_mm}
                    min={0}
                    max={10000}
                    step={1}
                    suffix="mm"
                    disabled={!current.enabled}
                    onValueChange={(value) => updateCamera(
                      camera.id,
                      "height_mm",
                      value,
                    )}
                  />
                  <div className="grid gap-3 grid-cols-3">
                    {["x", "y", "z"].map((axis) => (
                      <NumericInput
                        id={`calibration-${camera.id}-offset-${axis}`}
                        label={`${axis.toUpperCase()} 偏移`}
                        value={current[`offset_${axis}_mm`]}
                        min={-10000}
                        max={10000}
                        step={1}
                        suffix="mm"
                        disabled={!current.enabled}
                        onValueChange={(value) => updateCamera(
                          camera.id,
                          `offset_${axis}_mm`,
                          value,
                        )}
                        key={axis}
                      />
                    ))}
                  </div>
                  <TextInput
                    id={`calibration-${camera.id}-mount-description`}
                    label="安裝備註"
                    value={current.mount_description}
                    disabled={!current.enabled}
                    onValueChange={(value) => updateCamera(
                      camera.id,
                      "mount_description",
                      value,
                    )}
                  />
                  <ToggleRow
                    checked={current.is_movable}
                    label="可移動相機"
                    disabled={!current.enabled}
                    onClick={() => updateCamera(
                      camera.id,
                      "is_movable",
                      !current.is_movable,
                    )}
                  />
                </div>
              );
            })}
          </div>

          <div className="grid gap-3 min-[520px]:grid-cols-2 min-[960px]:grid-cols-4">
            <NumericInput
              id="calibration-profile-arm-height"
              label="旋臂高度"
              value={motion.arm_height_mm}
              min={0}
              max={10000}
              step={1}
              suffix="mm"
              onValueChange={(value) => setMotion((current) => ({
                ...current,
                arm_height_mm: value,
              }))}
            />
            <NumericInput
              id="calibration-profile-arm-radius"
              label="旋臂半徑先驗"
              value={motion.arm_radius_mm}
              min={0}
              max={10000}
              step={1}
              suffix="mm"
              onValueChange={(value) => setMotion((current) => ({
                ...current,
                arm_radius_mm: value,
              }))}
            />
            <NumericInput
              id="calibration-profile-minimum-angle"
              label="最小安全角度"
              value={motion.minimum_angle_deg}
              min={0}
              max={360}
              step={1}
              suffix="度"
              onValueChange={(value) => setMotion((current) => ({
                ...current,
                minimum_angle_deg: value,
              }))}
            />
            <NumericInput
              id="calibration-profile-maximum-angle"
              label="最大安全角度"
              value={motion.maximum_angle_deg}
              min={0}
              max={360}
              step={1}
              suffix="度"
              onValueChange={(value) => setMotion((current) => ({
                ...current,
                maximum_angle_deg: value,
              }))}
            />
          </div>

          <div className="grid gap-3 min-[520px]:grid-cols-2 min-[960px]:grid-cols-5">
            <SelectInput
              id="calibration-world-origin"
              label="世界原點"
              value={world.origin_definition}
              options={WORLD_ORIGIN_OPTIONS}
              onValueChange={(value) => setWorld((current) => ({
                ...current,
                origin_definition: value,
              }))}
            />
            {["x", "y", "z"].map((axis) => (
              <NumericInput
                id={`calibration-world-origin-${axis}`}
                label={`原點 ${axis.toUpperCase()} 偏移`}
                value={world[`origin_${axis}_mm`]}
                min={-10000}
                max={10000}
                step={1}
                suffix="mm"
                onValueChange={(value) => setWorld((current) => ({
                  ...current,
                  [`origin_${axis}_mm`]: value,
                }))}
                key={axis}
              />
            ))}
            <NumericInput
              id="calibration-platform-height"
              label="平台高度"
              value={world.platform_height_mm}
              min={-10000}
              max={10000}
              step={1}
              suffix="mm"
              onValueChange={(value) => setWorld((current) => ({
                ...current,
                platform_height_mm: value,
              }))}
            />
          </div>

          <TextInput
            id="calibration-profile-notes"
            label="校正檔備註"
            value={notes}
            onValueChange={setNotes}
          />

          <div className="flex justify-end">
            <Button
              variant="primary"
              disabled={
                !name.trim()
                || !selectedBoardId
                || enabledCount < 1
                || Boolean(pendingAction)
              }
              onClick={() => void createProfile()}
            >
              <FiSave
                className="size-4 shrink-0"
                aria-hidden="true"
              />
              儲存外參校正檔
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
