"use client";

import { useState } from "react";
import {
  FiCheck,
  FiRefreshCw,
  FiSave,
  FiX,
} from "react-icons/fi";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import {
  NumericInput,
  TextInput,
} from "@/components/inputs/Input";
import { ToggleRow } from "@/components/inputs/Toggle";
import InnerPanel from "@/components/panels/InnerPanel";
import { StatusPill } from "@/components/panels/Panel";

import {
  CALIBRATION_PAPER_BASELINE,
} from "../calibrationConfig";
import {
  appendStereoPair,
  buildCalibrationCreatePayload,
  calibrationBaselineComparison,
  createCalibrationDraft,
  toggleCalibrationPath,
} from "../lib/calibrationUtils";
import CalibrationSourcePicker from "./CalibrationSourcePicker";
import CalibrationStereoPairs from "./CalibrationStereoPairs";

const WORLD_COORDINATE_KEYS = new Set([
  "worldOrigin",
  "worldXAxis",
  "worldYAxis",
  "worldZAxis",
]);

export default function CalibrationCreateForm({
  sourceImages,
  pending,
  error,
  requiresRefresh,
  onCreate,
  onClearError,
  onRefresh,
}) {
  const [draft, setDraft] = useState(createCalibrationDraft);
  const [validationError, setValidationError] = useState("");
  const comparison = calibrationBaselineComparison(draft);

  function update(
    key,
    value,
  ) {
    setValidationError("");
    setDraft((current) => ({
      ...current,
      [key]: value,
      ...(WORLD_COORDINATE_KEYS.has(key)
        ? {
          worldTransformConfirmed: false,
        }
        : {}
      ),
    }));
  }

  function togglePath(
    cameraId,
    path,
  ) {
    setValidationError("");
    if (cameraId === "rotating") {
      setDraft((current) => ({
        ...current,
        rotatingImages: current.rotatingImages.some(
          (item) => item.path === path,
        )
          ? current.rotatingImages.filter((item) => item.path !== path)
          : [
            ...current.rotatingImages,
            {
              path,
              angleDeg: "",
            },
          ],
      }));
      return;
    }
    const key = cameraId === "top" ? "topImagePaths" : "sideImagePaths";
    setDraft((current) => {
      const nextPaths = toggleCalibrationPath(
        current[key],
        path,
      );
      const nextPairs = current.stereoImagePairs.filter((pair) => (
        cameraId === "top"
          ? nextPaths.includes(pair[0])
          : nextPaths.includes(pair[1])
      ));
      return {
        ...current,
        [key]: nextPaths,
        stereoImagePairs: nextPairs,
      };
    });
  }

  function updateMatrixCell(
    rowIndex,
    columnIndex,
    value,
  ) {
    setValidationError("");
    setDraft((current) => ({
      ...current,
      worldTransformConfirmed: false,
      worldTransformMatrix: current.worldTransformMatrix.map(
        (row, currentRow) => row.map(
          (cell, currentColumn) => (
            currentRow === rowIndex && currentColumn === columnIndex
              ? value
              : cell
          ),
        ),
      ),
    }));
  }

  async function submit(event) {
    event.preventDefault();
    try {
      const payload = buildCalibrationCreatePayload(draft);
      setValidationError("");
      await onCreate(payload);
    } catch (nextError) {
      setValidationError(
        nextError instanceof Error
          ? nextError.message.trim()
          : "校正建立資料無效。",
      );
    }
  }

  const visibleError = validationError || error;

  return (
    <form
      className="grid gap-5"
      onSubmit={(event) => void submit(event)}
    >
      <SubsectionHeader
        title="建立校正檔案"
        description="來源影像保持唯讀；建立後會依序偵測角點、計算單鏡頭校正、計算雙鏡頭校正，再由使用者驗證。"
      />

      <InnerPanel as="section">
        <SubsectionHeader
          title="論文 A1／A2 基準與實測值"
          description="論文基準只供比較。棋盤格尺寸、雙鏡頭內角點規格及世界座標轉換必須來自實際量測，不會由板面尺寸推導。"
        />
        <div className="grid gap-3 min-[720px]:grid-cols-2">
          <article className="grid gap-2 rounded-xl border border-white/10 bg-black/10 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 className="m-0 text-sm font-black text-white">A1 單鏡頭校正板</h4>
              <StatusPill tone={
                comparison.individualComplete
                && comparison.patternComplete
                && comparison.individualMatches
                && comparison.patternMatches
                  ? "success"
                  : "warning"
              }>
                {!comparison.individualComplete || !comparison.patternComplete
                  ? "待填實測值"
                  : comparison.individualMatches && comparison.patternMatches
                    ? "符合論文板面基準"
                    : "與論文板面基準不同"
                }
              </StatusPill>
            </div>
            <p className="m-0 text-xs font-semibold text-neutral-300">
              論文：{CALIBRATION_PAPER_BASELINE.individualPattern.join(" × ")} 內角點，板面 {CALIBRATION_PAPER_BASELINE.individualBoardSizeCm.join(" × ")} cm
            </p>
          </article>
          <article className="grid gap-2 rounded-xl border border-white/10 bg-black/10 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 className="m-0 text-sm font-black text-white">A2 雙鏡頭校正板</h4>
              <StatusPill tone={
                comparison.stereoComplete && comparison.stereoMatches
                  ? "success"
                  : "warning"
              }>
                {!comparison.stereoComplete
                  ? "待填實測值"
                  : comparison.stereoMatches
                    ? "符合論文板面基準"
                    : "與論文板面基準不同"
                }
              </StatusPill>
            </div>
            <p className="m-0 text-xs font-semibold text-neutral-300">
              論文只公開板面 {CALIBRATION_PAPER_BASELINE.stereoBoardSizeCm.join(" × ")} cm，未公開內角點數與棋盤格尺寸。
            </p>
          </article>
        </div>
      </InnerPanel>

      <div className="grid gap-4 min-[900px]:grid-cols-3">
        <CalibrationSourcePicker
          cameraId="top"
          cameraLabel="俯視角"
          images={sourceImages}
          selectedPaths={draft.topImagePaths}
          onToggle={(path) => togglePath(
            "top",
            path,
          )}
        />
        <CalibrationSourcePicker
          cameraId="side"
          cameraLabel="側視角"
          images={sourceImages}
          selectedPaths={draft.sideImagePaths}
          onToggle={(path) => togglePath(
            "side",
            path,
          )}
        />
        <CalibrationSourcePicker
          cameraId="rotating"
          cameraLabel="旋臂視角"
          images={sourceImages}
          selectedPaths={draft.rotatingImages.map((item) => item.path)}
          onToggle={(path) => togglePath(
            "rotating",
            path,
          )}
        />
      </div>

      {draft.rotatingImages.length ? (
        <InnerPanel as="section">
          <SubsectionHeader
            title="環繞校正角度"
            description="每張 rotating 棋盤影像都必須填入拍攝時的實際馬達角度，至少包含三個不同角度。"
          />
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {draft.rotatingImages.map((item) => (
              <NumericInput
                id={`calibration-rotating-angle-${encodeURIComponent(item.path)}`}
                label={item.path.split(/[\\/]/).pop() || "環繞影像"}
                value={item.angleDeg}
                suffix="度"
                step={0.1}
                onValueChange={(angleDeg) => setDraft((current) => ({
                  ...current,
                  rotatingImages: current.rotatingImages.map((currentItem) => (
                    currentItem.path === item.path
                      ? {
                        ...currentItem,
                        angleDeg,
                      }
                      : currentItem
                  )),
                }))}
              />
            ))}
          </div>
        </InnerPanel>
      ) : null}

      <CalibrationStereoPairs
        images={sourceImages}
        topPaths={draft.topImagePaths}
        sidePaths={draft.sideImagePaths}
        pairs={draft.stereoImagePairs}
        onAdd={(topPath, sidePath) => {
          const nextPairs = appendStereoPair(
            draft.stereoImagePairs,
            topPath,
            sidePath,
          );
          setDraft((current) => ({
            ...current,
            stereoImagePairs: nextPairs,
          }));
        }}
        onRemove={(index) => setDraft((current) => ({
          ...current,
          stereoImagePairs: current.stereoImagePairs.filter(
            (_, currentIndex) => currentIndex !== index,
          ),
        }))}
      />

      <InnerPanel as="section">
        <SubsectionHeader
          title="棋盤實測規格"
          description="內角點是棋盤內部交點數；X／Y 格距與完整板面寬高都必須由實體校正板量測。"
        />
        <div className="grid gap-3 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-4">
          <NumericInput
            id="calibration-pattern-columns"
            label="單鏡頭內角點欄數"
            min={2}
            step={1}
            value={draft.patternColumns}
            onValueChange={(value) => update(
              "patternColumns",
              value,
            )}
          />
          <NumericInput
            id="calibration-pattern-rows"
            label="單鏡頭內角點列數"
            min={2}
            step={1}
            value={draft.patternRows}
            onValueChange={(value) => update(
              "patternRows",
              value,
            )}
          />
          <NumericInput
            id="calibration-square-x"
            label="單鏡頭格距 X"
            min={0.001}
            step={0.1}
            suffix="mm"
            value={draft.squareSizeMmX}
            onValueChange={(value) => update(
              "squareSizeMmX",
              value,
            )}
          />
          <NumericInput
            id="calibration-square-y"
            label="單鏡頭格距 Y"
            min={0.001}
            step={0.1}
            suffix="mm"
            value={draft.squareSizeMmY}
            onValueChange={(value) => update(
              "squareSizeMmY",
              value,
            )}
          />
          <NumericInput
            id="calibration-individual-board-width"
            label="單鏡頭板面寬度"
            min={0.1}
            step={0.1}
            suffix="cm"
            value={draft.individualBoardWidthCm}
            onValueChange={(value) => update(
              "individualBoardWidthCm",
              value,
            )}
          />
          <NumericInput
            id="calibration-individual-board-height"
            label="單鏡頭板面高度"
            min={0.1}
            step={0.1}
            suffix="cm"
            value={draft.individualBoardHeightCm}
            onValueChange={(value) => update(
              "individualBoardHeightCm",
              value,
            )}
          />
          <NumericInput
            id="calibration-stereo-pattern-columns"
            label="雙鏡頭內角點欄數"
            min={2}
            step={1}
            value={draft.stereoPatternColumns}
            onValueChange={(value) => update(
              "stereoPatternColumns",
              value,
            )}
          />
          <NumericInput
            id="calibration-stereo-pattern-rows"
            label="雙鏡頭內角點列數"
            min={2}
            step={1}
            value={draft.stereoPatternRows}
            onValueChange={(value) => update(
              "stereoPatternRows",
              value,
            )}
          />
          <NumericInput
            id="calibration-stereo-square-x"
            label="雙鏡頭格距 X"
            min={0.001}
            step={0.1}
            suffix="mm"
            value={draft.stereoSquareSizeMmX}
            onValueChange={(value) => update(
              "stereoSquareSizeMmX",
              value,
            )}
          />
          <NumericInput
            id="calibration-stereo-square-y"
            label="雙鏡頭格距 Y"
            min={0.001}
            step={0.1}
            suffix="mm"
            value={draft.stereoSquareSizeMmY}
            onValueChange={(value) => update(
              "stereoSquareSizeMmY",
              value,
            )}
          />
          <NumericInput
            id="calibration-stereo-board-width"
            label="雙鏡頭板面寬度"
            min={0.1}
            step={0.1}
            suffix="cm"
            value={draft.stereoBoardWidthCm}
            onValueChange={(value) => update(
              "stereoBoardWidthCm",
              value,
            )}
          />
          <NumericInput
            id="calibration-stereo-board-height"
            label="雙鏡頭板面高度"
            min={0.1}
            step={0.1}
            suffix="cm"
            value={draft.stereoBoardHeightCm}
            onValueChange={(value) => update(
              "stereoBoardHeightCm",
              value,
            )}
          />
        </div>
      </InnerPanel>

      <InnerPanel as="section">
        <SubsectionHeader
          title="世界座標與剛體轉換"
          description="T_world_from_stereo 將雙鏡頭校正座標轉為 mm 世界座標。預填單位矩陣只方便輸入，不代表其符合實際裝置。"
        />
        <div className="grid gap-3 min-[720px]:grid-cols-2">
          <TextInput
            id="calibration-world-origin"
            label="世界座標原點"
            value={draft.worldOrigin}
            onValueChange={(value) => update(
              "worldOrigin",
              value,
            )}
          />
          <TextInput
            id="calibration-world-x-axis"
            label="X 軸方向"
            value={draft.worldXAxis}
            onValueChange={(value) => update(
              "worldXAxis",
              value,
            )}
          />
          <TextInput
            id="calibration-world-y-axis"
            label="Y 軸方向"
            value={draft.worldYAxis}
            onValueChange={(value) => update(
              "worldYAxis",
              value,
            )}
          />
          <TextInput
            id="calibration-world-z-axis"
            label="Z 軸方向"
            value={draft.worldZAxis}
            onValueChange={(value) => update(
              "worldZAxis",
              value,
            )}
          />
        </div>

        <div className="grid gap-2 overflow-x-auto rounded-xl border border-white/10 bg-black/10 p-3">
          <strong className="text-xs font-black text-emerald-200">
            T_world_from_stereo（4 × 4）
          </strong>
          <div className="grid min-w-[40rem] grid-cols-4 gap-2">
            {draft.worldTransformMatrix.map((row, rowIndex) => row.map((value, columnIndex) => (
              <NumericInput
                id={`calibration-world-transform-${rowIndex}-${columnIndex}`}
                label={`第 ${rowIndex + 1} 列第 ${columnIndex + 1} 欄`}
                step={0.001}
                value={value}
                onValueChange={(nextValue) => updateMatrixCell(
                  rowIndex,
                  columnIndex,
                  nextValue,
                )}
                key={`${rowIndex}-${columnIndex}`}
              />
            )))}
          </div>
        </div>

        <ToggleRow
          label="這是已量測／確認的 T_world_from_stereo"
          description="只有在矩陣確實對應目前裝置的原點與軸向時才可確認；單位矩陣不一定正確。"
          checked={draft.worldTransformConfirmed}
          onClick={() => update(
            "worldTransformConfirmed",
            !draft.worldTransformConfirmed,
          )}
          status={draft.worldTransformConfirmed ? (
            <StatusPill tone="success">已確認</StatusPill>
          ) : (
            <StatusPill tone="warning">尚未確認</StatusPill>
          )}
        />

        <TextInput
          id="calibration-notes"
          label="校正備註"
          value={draft.notes}
          maxLength={2000}
          onValueChange={(value) => update(
            "notes",
            value,
          )}
          placeholder="記錄棋盤、鏡頭、支架、量測方式及與論文基準的差異"
        />
      </InnerPanel>

      {visibleError ? (
        <div
          className="grid gap-3 rounded-xl border border-rose-300/30 bg-rose-500/10 p-3"
          role="alert"
        >
          <p className="m-0 text-sm font-semibold text-rose-200">
            {visibleError}
          </p>
          <div className="flex flex-wrap justify-end gap-2">
            {!requiresRefresh ? (
              <Button
                onClick={() => {
                  setValidationError("");
                  onClearError();
                }}
              >
                <FiX
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                清除錯誤
              </Button>
            ) : null}
            {requiresRefresh ? (
              <Button
                variant="primary"
                onClick={onRefresh}
              >
                <FiRefreshCw
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                重新讀取並確認
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      <ActionRow className="w-full">
        <Button
          disabled={pending || requiresRefresh}
          onClick={() => {
            setDraft(createCalibrationDraft());
            setValidationError("");
            onClearError();
          }}
        >
          <FiRefreshCw
            className="size-4 shrink-0"
            aria-hidden="true"
          />
          重設表單
        </Button>
        <Button
          className="ml-auto"
          variant="primary"
          type="submit"
          disabled={pending || requiresRefresh}
        >
          {pending ? (
            <FiCheck
              className="size-4 shrink-0"
              aria-hidden="true"
            />
          ) : (
            <FiSave
              className="size-4 shrink-0"
              aria-hidden="true"
            />
          )}
          {pending ? "建立中…" : "建立校正"}
        </Button>
      </ActionRow>
    </form>
  );
}
