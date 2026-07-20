"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";
import { FiDownload } from "react-icons/fi";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import { NumericInput } from "@/components/inputs/Input";
import FullscreenImage from "@/components/media/FullscreenImage";

import { CALIBRATION_BOARD_DEFAULTS } from "../calibrationConfig";

const AUTO_GENERATE_DELAY_MS = 400;

export default function CalibrationBoardSettings({
  boards,
  selectedBoardId,
  pendingAction,
  onBoardChange,
  onAction,
}) {
  const [draft, setDraft] = useState({
    squares_x: CALIBRATION_BOARD_DEFAULTS.squaresX,
    squares_y: CALIBRATION_BOARD_DEFAULTS.squaresY,
  });
  const [generationRevision, setGenerationRevision] = useState(0);
  const syncedBoardIdRef = useRef("");
  const latestRevisionRef = useRef(0);
  const lastRequestedGridRef = useRef("");
  const mountedRef = useRef(false);
  const selectedBoard = boards.find(
    (board) => board.board_profile_id === selectedBoardId,
  ) || null;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (
      !selectedBoard
      || syncedBoardIdRef.current === selectedBoard.board_profile_id
    ) {
      return;
    }
    syncedBoardIdRef.current = selectedBoard.board_profile_id;
    setDraft({
      squares_x: String(selectedBoard.squares_x),
      squares_y: String(selectedBoard.squares_y),
    });
  }, [selectedBoard]);

  function update(key, value) {
    latestRevisionRef.current += 1;
    setGenerationRevision(latestRevisionRef.current);
    setDraft((current) => ({
      ...current,
      [key]: value,
    }));
  }

  useEffect(() => {
    if (generationRevision === 0 || pendingAction) return undefined;

    const squaresX = Number(draft.squares_x);
    const squaresY = Number(draft.squares_y);
    const validGrid = Number.isInteger(squaresX)
      && Number.isInteger(squaresY)
      && squaresX >= 3
      && squaresY >= 3;

    if (!validGrid) return undefined;

    const requestedRevision = generationRevision;
    const gridKey = `${squaresX}:${squaresY}`;
    if (lastRequestedGridRef.current === gridKey) return undefined;

    const timer = window.setTimeout(async () => {
      lastRequestedGridRef.current = gridKey;
      const outcome = await onAction(
        "board.create",
        "/api/calibration/boards",
        {
          body: {
            paper_size: CALIBRATION_BOARD_DEFAULTS.paperSize,
            paper_orientation: CALIBRATION_BOARD_DEFAULTS.paperOrientation,
            squares_x: squaresX,
            squares_y: squaresY,
          },
        },
      );

      if (
        !mountedRef.current
        || requestedRevision !== latestRevisionRef.current
        || !outcome?.result?.board_profile_id
      ) {
        return;
      }

      onBoardChange(outcome.result.board_profile_id);
    }, AUTO_GENERATE_DELAY_MS);

    return () => window.clearTimeout(timer);
  }, [
    draft.squares_x,
    draft.squares_y,
    generationRevision,
    onAction,
    onBoardChange,
    pendingAction,
  ]);

  const imagePath = selectedBoardId
    ? `/api/calibration/boards/${encodeURIComponent(selectedBoardId)}/image`
    : "";
  return (
    <section
      className="flex flex-col w-full gap-4 items-center justify-center"
      aria-label="OpenCV 校正板生成"
    >
      <div className="relative grid min-h-64 min-w-120 place-items-center overflow-hidden rounded-xl border border-white/15 bg-neutral-100 p-3">
        {imagePath ? (
          <>
            <img
              className="max-h-128 w-full object-contain"
              src={imagePath}
              alt="OpenCV 校正板預覽"
            />
            <FullscreenImage
              src={imagePath}
              alt="OpenCV 校正板全螢幕預覽"
              label="校正板"
            />
          </>
        ) : (
          <span className="text-sm font-bold text-neutral-600">
            尚無可預覽的校正板
          </span>
        )}
      </div>

      <div className="place-self-center flex flex-row content-start gap-4">
        <div className="grid grid-cols-2 gap-2">
          <NumericInput
            id="calibration-board-squares-x"
            label="水平格數"
            value={draft.squares_x}
            min={3}
            step={1}
            onValueChange={(value) => update("squares_x", value)}
            className="w-30"
          />
          <NumericInput
            id="calibration-board-squares-y"
            label="垂直格數"
            value={draft.squares_y}
            min={3}
            step={1}
            onValueChange={(value) => update("squares_y", value)}
            className="w-30"
          />
        </div>
        <Button
          disabled={!imagePath}
          onClick={() => {
            const anchor = document.createElement("a");
            anchor.href = `${imagePath}?download=true`;
            anchor.download = `${selectedBoardId || "calibration-board"}.png`;
            anchor.click();
          }}
        >
          <FiDownload
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          下載校正板
        </Button>
      </div>
    </section>
  );
}
