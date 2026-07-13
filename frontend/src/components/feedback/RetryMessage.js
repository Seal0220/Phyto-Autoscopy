import { FiRefreshCw } from "react-icons/fi";

import Button from "@/components/buttons/Button";

export default function RetryMessage({
  message,
  onRetry,
  retrying = false,
}) {
  return (
    <div
      className="grid min-h-28 place-items-center gap-3 rounded-xl border border-dashed border-rose-300/25 bg-rose-400/5 p-4 text-center"
      role="alert"
    >
      <p className="m-0 text-sm font-semibold text-rose-200">
        {message}
      </p>
      <Button
        className="min-h-9 px-3 text-xs"
        disabled={retrying}
        onClick={onRetry}
      >
        <FiRefreshCw
          className="size-3.5 shrink-0"
          aria-hidden="true"
        />
        {retrying ? "重新讀取中…" : "重新讀取"}
      </Button>
    </div>
  );
}
