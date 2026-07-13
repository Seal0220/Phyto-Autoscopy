"use client";

import { useState } from "react";
import {
  FiCrosshair,
  FiNavigation,
  FiRotateCcw,
  FiSquare,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import { NumericInput } from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import { StatusPill } from "@/components/panels/Panel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import VerticalLine from "@/components/VerticalLine";

export default function MotorControls({
  motor,
  isConnected,
  busyActions,
  scheduleActive,
  onRunAction,
}) {
  const [targetAngle, setTargetAngle] = useState(String(motor.command_position_deg ?? 0));
  const engaged = Boolean(motor.engaged);
  const changingEngagement = busyActions.has("motor.engage")
    || busyActions.has("motor.disengage");
  const baseDisabled = scheduleActive || !isConnected;
  const motorActionInProgress = [...busyActions].some((action) => (
    action.startsWith("motor.") && action !== "motor.stop"
  ));
  const actionInProgress = motorActionInProgress || Boolean(motor.moving);
  const controlsDisabled = baseDisabled || actionInProgress;
  const parsedTarget = Number(targetAngle);
  const targetValid = Number.isFinite(parsedTarget)
    && parsedTarget >= Number(motor.minimum_angle_deg ?? 0)
    && parsedTarget <= Number(motor.maximum_angle_deg ?? 360);

  function moveToTarget() {
    if (!targetValid) return;
    void onRunAction(
      "motor.move",
      { angle_deg: parsedTarget },
      `馬達已移動到 ${parsedTarget} 度。`,
    );
  }

  return (
    <fieldset
      className={`
        grid min-w-0 gap-5 border-0 p-0
        ${scheduleActive ? "grayscale opacity-60" : ""}
      `}
    >
      <SubsectionHeader
        title="馬達控制"
        description={scheduleActive ? "排程進行中，馬達控制已停用。" : "移動、原點與保持扭力等即時操作。"}
      >
        <StatusPill tone={scheduleActive ? "warning" : isConnected ? "success" : "offline"}>
          {scheduleActive ? "排程中" : isConnected ? "可操作" : "離線"}
        </StatusPill>
      </SubsectionHeader>

      <div className="flex flex-row gap-3">
        <div className="flex flex-row gap-2">
          <Button
            disabled={controlsDisabled}
            onClick={() => void onRunAction(
              "motor.set_origin",
              {},
              "已設定馬達原點。",
            )}
          >
            <FiCrosshair
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            設為原點
          </Button>
          <Button
            disabled={controlsDisabled}
            onClick={() => void onRunAction(
              "motor.return_origin",
              {},
              "馬達正在回到原點。",
            )}
          >
            <FiRotateCcw
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            回到原點
          </Button>
          <Button
            variant="danger"
            disabled={scheduleActive || busyActions.has("motor.stop")}
            onClick={() => void onRunAction(
              "motor.stop",
              {},
              "馬達已停止。",
            )}
          >
            <FiSquare
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            停止馬達
          </Button>
        </div>
        <VerticalLine />
        <ToggleRow
          checked={engaged}
          label="鎖定馬達位置"
          description="啟用後持續提供保持電流，讓轉盤停在目前角度；關閉後即可手動轉動。"
          status={(
            <StatusPill tone={!isConnected ? "offline" : engaged ? "success" : "neutral"}>
              {changingEngagement ? "切換中" : !isConnected ? "離線" : engaged ? "保持中" : "已釋放"}
            </StatusPill>
          )}
          disabled={controlsDisabled || changingEngagement}
          onClick={() => void onRunAction(
            engaged ? "motor.disengage" : "motor.engage",
            {},
            engaged ? "馬達已釋放。" : "馬達位置已鎖定。",
          )}
        />
        <VerticalLine />
        <div className="flex flex-row gap-2">
          <Button
            variant="primary"
            disabled={controlsDisabled || !targetValid}
            onClick={moveToTarget}
          >
            <FiNavigation
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            轉到角度
          </Button>
          <NumericInput
            id="motor-target-angle"
            label="目標角度"
            disabled={controlsDisabled}
            value={targetAngle}
            onValueChange={setTargetAngle}
            min={motor.minimum_angle_deg ?? 0}
            max={motor.maximum_angle_deg ?? 360}
            step={0.1}
            suffix="度"
            required
          />
        </div>
      </div>
    </fieldset>
  );
}
