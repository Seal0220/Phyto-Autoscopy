"use client";

import { useEffect, useState } from "react";
import {
  FiAlertOctagon,
  FiCornerDownLeft,
  FiMapPin,
  FiMove,
  FiPower,
  FiSave,
  FiSquare,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { NumericInput } from "@/components/inputs/Input";

import { suggestedCalibrationAngles } from "../lib/calibrationUtils";

export default function CalibrationMotorControls({
  status,
  profile,
  locked,
  pendingAction,
  onAction,
}) {
  const [targetAngle, setTargetAngle] = useState("0");
  const [armHeight, setArmHeight] = useState("0");

  useEffect(() => {
    const value = profile?.motion_model?.arm_height_mm
      ?? status?.arm_height_mm
      ?? 0;
    setArmHeight(String(value));
  }, [
    profile?.motion_model?.arm_height_mm,
    status?.arm_height_mm,
  ]);

  const angleRange = profile?.motion_model?.usable_angle_range_deg || [0, 360];
  const suggestedAngles = suggestedCalibrationAngles(angleRange);

  function moveTo(angle) {
    setTargetAngle(String(angle));
    return onAction(
      "motor.move",
      "/api/calibration/motor/move",
      {
        body: {
          angle_deg: Number(angle),
        },
        timeoutMs: 120_000,
        successMessage: `旋臂已移動至 ${Number(angle).toFixed(1)}°。`,
      },
    );
  }

  return (
    <section
      className="grid gap-3"
      aria-labelledby="calibration-motor-title"
    >
      <SubsectionHeader
        titleId="calibration-motor-title"
        title="馬達與旋臂控制"
        description="所有移動仍會通過既有軟體限位、速度、加速度、電流與逾時安全檢查。"
      />

      <div className="grid gap-3 min-[760px]:grid-cols-2">
        <NumericInput
          id="calibration-target-angle"
          label="目標角度"
          value={targetAngle}
          min={0}
          max={360}
          step={1}
          suffix="度"
          disabled={!locked}
          onValueChange={setTargetAngle}
        />
        <NumericInput
          id="calibration-arm-height"
          label="旋臂高度"
          value={armHeight}
          min={0}
          max={10000}
          step={1}
          suffix="mm"
          disabled={!locked || !profile}
          description={profile
            ? `儲存至外參校正檔 ${profile.name}。`
            : "請先建立或選擇外參校正檔。"
          }
          onValueChange={setArmHeight}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-black text-neutral-400">
          建議角度
        </span>
        {suggestedAngles.map((angle) => (
          <Button
            className="min-h-9 px-3 text-xs"
            disabled={
              !locked
              || !status?.motor?.engaged
              || Boolean(pendingAction)
            }
            onClick={() => void moveTo(angle)}
            key={angle}
          >
            <FiMove
              className="size-3.5 shrink-0"
              aria-hidden="true"
            />
            {angle}°
          </Button>
        ))}
      </div>

      <div className="flex flex-wrap justify-end gap-2">
        <Button
          disabled={!locked || Boolean(pendingAction)}
          onClick={() => void onAction(
            status?.motor?.engaged ? "motor.disengage" : "motor.engage",
            status?.motor?.engaged
              ? "/api/calibration/motor/disengage"
              : "/api/calibration/motor/engage",
            {
              successMessage: status?.motor?.engaged
                ? "馬達已釋放。"
                : "馬達已啟用。",
            },
          )}
        >
          <FiPower
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {status?.motor?.engaged ? "釋放馬達" : "啟用馬達"}
        </Button>
        <Button
          variant="primary"
          disabled={
            !locked
            || !status?.motor?.engaged
            || Boolean(pendingAction)
          }
          onClick={() => void moveTo(targetAngle)}
        >
          <FiMove
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          移動至角度
        </Button>
        <Button
          disabled={!locked || !profile || Boolean(pendingAction)}
          onClick={() => void onAction(
            "profile.arm-height",
            `/api/calibration/extrinsics/${encodeURIComponent(profile?.profile_id || "")}/arm-height`,
            {
              method: "PATCH",
              body: {
                arm_height_mm: Number(armHeight),
              },
              successMessage: "旋臂高度已儲存至外參校正檔。",
            },
          )}
        >
          <FiSave
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          儲存高度
        </Button>
        <Button
          disabled={
            !locked
            || !status?.motor?.engaged
            || Boolean(pendingAction)
          }
          onClick={() => void onAction(
            "motor.return-origin",
            "/api/calibration/motor/return-origin",
            {
              timeoutMs: 120_000,
              successMessage: "旋臂已返回原點。",
            },
          )}
        >
          <FiCornerDownLeft
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          返回原點
        </Button>
        <Button
          disabled={!locked || Boolean(pendingAction)}
          onClick={() => void onAction(
            "motor.set-origin",
            "/api/calibration/motor/set-origin",
            {
              successMessage: "目前位置已設為馬達零點。",
            },
          )}
        >
          <FiMapPin
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          設為原點
        </Button>
        <Button
          disabled={!locked || Boolean(pendingAction)}
          onClick={() => void onAction(
            "motor.stop",
            "/api/calibration/motor/stop",
            {
              successMessage: "已停止馬達移動。",
            },
          )}
        >
          <FiSquare
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          停止
        </Button>
        <Button
          variant="danger"
          disabled={pendingAction === "motor.emergency-stop"}
          onClick={() => void onAction(
            "motor.emergency-stop",
            "/api/calibration/motor/emergency-stop",
            {
              successMessage: "緊急停止已執行。",
            },
          )}
        >
          <FiAlertOctagon
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          緊急停止
        </Button>
      </div>
    </section>
  );
}
