import {
  FiTrash2,
} from "react-icons/fi";

import Button from "@/components/buttons/Button";
import InnerPanel from "@/components/panels/InnerPanel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";

import { formatTipTimestamp } from "../lib/tipReviewUtils";

function formatStoredPoint(
  xValue,
  yValue,
) {
  if (xValue == null || yValue == null) return "—";
  const x = Number(xValue);
  const y = Number(yValue);
  return Number.isFinite(x) && Number.isFinite(y)
    ? `${x.toFixed(2)}, ${y.toFixed(2)} px`
    : "—";
}

export default function TipReviewCorrectionHistory({
  corrections,
  deletingId,
  locked,
  onDelete,
}) {
  const ordered = [...corrections].sort((
    left,
    right,
  ) => (
    String(right.created_at).localeCompare(String(left.created_at))
  ));

  return (
    <InnerPanel>
      <SubsectionHeader
        title="修正歷史"
        description="每筆修正獨立保存；清除指定修正後，原始自動偵測仍保留。"
      />

      {ordered.length === 0 ? (
        <p className="m-0 rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-center text-sm font-semibold text-neutral-500">
          本影格尚無人工修正
        </p>
      ) : (
        <ol className="grid max-h-72 gap-2 overflow-y-auto pr-1">
          {ordered.map((correction) => (
            <li
              key={correction.correction_id}
              className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] gap-3 rounded-xl border border-white/10 bg-black/10 p-3"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <strong className="text-sm font-black text-neutral-100">
                    {correction.camera_id === "top" ? "俯視角" : "側視角"}
                  </strong>
                  <span className={`text-xs font-black ${correction.invalid ? "text-rose-200" : "text-emerald-200"}`}>
                    {correction.invalid
                      ? "無效"
                      : `${correction.correctedPoint?.x.toFixed(2)}, ${correction.correctedPoint?.y.toFixed(2)} px`
                    }
                  </span>
                </div>
                <p className="mt-1 mb-0 wrap-break-word text-xs font-semibold text-neutral-400">
                  {correction.reason || "未填寫原因"}
                </p>
                <p className="mt-1 mb-0 text-[11px] font-semibold text-neutral-500">
                  自動位置：{formatStoredPoint(
                    correction.automatic_x_px,
                    correction.automatic_y_px,
                  )}
                </p>
                <p className="mt-1 mb-0 text-[11px] font-semibold text-neutral-500">
                  {correction.operator_id || "未知操作者"} · {formatTipTimestamp(correction.created_at)}
                </p>
                <p
                  className="mt-1 mb-0 truncate text-[10px] font-semibold text-neutral-600"
                  title={correction.correction_id}
                >
                  修正 ID：{correction.correction_id}
                </p>
              </div>
              <Button
                className="min-h-9 self-center px-3 text-xs"
                variant="dangerGhost"
                disabled={locked}
                onClick={() => onDelete(correction.correction_id)}
              >
                <FiTrash2
                  className="size-3.5 shrink-0"
                  aria-hidden="true"
                />
                {deletingId === correction.correction_id ? "清除中…" : "清除此筆"}
              </Button>
            </li>
          ))}
        </ol>
      )}
    </InnerPanel>
  );
}
