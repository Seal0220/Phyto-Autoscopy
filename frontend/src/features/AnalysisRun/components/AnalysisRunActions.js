import {
  FiCheckCircle,
  FiDownload,
  FiEye,
  FiFastForward,
  FiPlay,
  FiRefreshCw,
  FiRotateCcw,
  FiSquare,
  FiTrendingUp,
} from "react-icons/fi";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";

import { analysisRunActionAvailability } from "../lib/analysisRunUtils";

export default function AnalysisRunActions({
  exportPending,
  locked,
  onAction,
  onExport,
  onOpenResults,
  onOpenReview,
  onSkipReview,
  pendingAction,
  status,
}) {
  const available = analysisRunActionAvailability(status);

  return (
    <ActionRow className="w-full">
      {available.validate ? (
        <Button
          variant="primary"
          disabled={locked}
          onClick={() => onAction("validate")}
        >
          <FiCheckCircle
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {pendingAction === "validate" ? "驗證中…" : "驗證分析"}
        </Button>
      ) : null}
      {available.start ? (
        <Button
          variant="primary"
          disabled={locked}
          onClick={() => onAction("start")}
        >
          <FiPlay
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {pendingAction === "start" ? "啟動中…" : "開始分析"}
        </Button>
      ) : null}
      {available.cancel ? (
        <Button
          variant="danger"
          disabled={locked}
          onClick={() => onAction("cancel")}
        >
          <FiSquare
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {pendingAction === "cancel" ? "取消中…" : "取消分析"}
        </Button>
      ) : null}
      {available.retry ? (
        <Button
          disabled={locked}
          onClick={() => onAction("retry")}
        >
          <FiRefreshCw
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {pendingAction === "retry" ? "重試中…" : "重試"}
        </Button>
      ) : null}
      {available.reset ? (
        <Button
          disabled={locked}
          onClick={() => onAction("reset")}
        >
          <FiRotateCcw
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {pendingAction === "reset" ? "重設中…" : "重設"}
        </Button>
      ) : null}
      {available.review ? (
        <Button
          disabled={locked}
          onClick={onOpenReview}
        >
          <FiEye
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          人工修正
        </Button>
      ) : null}
      {available.skipReview ? (
        <Button
          disabled={locked}
          onClick={onSkipReview}
        >
          <FiFastForward
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {pendingAction === "reconstruct_without_review"
            ? "啟動重建中…"
            : "略過人工修正並重建"
          }
        </Button>
      ) : null}
      {available.results ? (
        <Button
          disabled={locked}
          onClick={onOpenResults}
        >
          <FiTrendingUp
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          查看結果
        </Button>
      ) : null}
      {available.export ? (
        <Button
          variant="primary"
          disabled={exportPending || locked}
          onClick={onExport}
        >
          <FiDownload
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {exportPending ? "匯出中…" : "匯出結果"}
        </Button>
      ) : null}
    </ActionRow>
  );
}
