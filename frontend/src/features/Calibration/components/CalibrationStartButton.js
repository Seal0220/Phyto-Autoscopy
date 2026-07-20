import { FiPlay } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import Tooltip from "@/components/Tooltip";

export default function CalibrationStartButton({
  className,
  disabled = false,
  systemActive = false,
  onClick,
}) {
  return (
    <span className="group relative inline-flex">
      <Button
        className={className}
        variant="primary"
        disabled={disabled || systemActive}
        onClick={onClick}
      >
        <FiPlay
          className="size-4 shrink-0"
          aria-hidden="true"
        />
        開始校正
      </Button>
      {systemActive ? (
        <Tooltip className="right-0 left-auto">
          目前系統運行中無法校正
        </Tooltip>
      ) : null}
    </span>
  );
}
