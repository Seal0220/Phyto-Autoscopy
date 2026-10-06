import { PiPlus, PiTrash } from "react-icons/pi";
import Button from "@/components/buttons/Button";

export default function AnalysisRunPairActions({
  disabled,
  full,
  onAdd,
  onRemove,
}) {
  return (
    <>
      <Button
        disabled={disabled}
        onClick={onRemove}
      >
        <PiTrash
          className="size-4 shrink-0"
          aria-hidden="true"
        />
        刪除一組
      </Button>
      <Button
        disabled={disabled || full}
        onClick={onAdd}
      >
        <PiPlus
          className="size-4 shrink-0"
          aria-hidden="true"
        />
        新增一組
      </Button>
    </>
  );
}
