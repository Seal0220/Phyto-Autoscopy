import {
  FiCheckCircle,
  FiDownload,
  FiEye,
  FiFastForward,
  FiPlay,
  FiPause,
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
  stage,
  stereoReview,
}) {
  const available = analysisRunActionAvailability(status, stage);
  let skipReviewLabel = "略過人工確認並完成";
  if (pendingAction === "reconstruct_without_review") {
    skipReviewLabel = "完成分析中…";
  }

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
      {available.pause ? (
        <Button
          disabled={locked}
          onClick={() => onAction("pause")}
        >
          <FiPause
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {pendingAction === "pause" ? "要求暫停中…" : "暫停並保存"}
        </Button>
      ) : null}
      {available.resume ? (
        <Button
          variant="primary"
          disabled={locked}
          onClick={() => onAction("resume")}
        >
          <FiPlay
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {pendingAction === "resume" ? "恢復中…" : "恢復分析"}
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
      {available.rebuildPreview ? (
        <Button
          disabled={locked}
          onClick={() => onAction("retry")}
        >
          <FiRefreshCw
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          {pendingAction === "retry" ? "準備中…" : "重建預覽"}
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
          {stage === "waiting_for_model_review" ? "對齊模型" : stereoReview ? "人工配對" : "人工修正"}
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
          {skipReviewLabel}
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
