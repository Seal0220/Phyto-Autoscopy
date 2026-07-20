import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  calibrationAngleCompleted,
  calibrationLockState,
  intrinsicCaptureNotice,
  suggestedCalibrationAngles,
} from "../src/features/Calibration/lib/calibrationUtils.js";

const frontendRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

function source(relativePath) {
  return readFileSync(
    path.join(frontendRoot, "src", relativePath),
    "utf8",
  );
}

test("calibration lock ownership survives a workspace refresh", () => {
  assert.deepEqual(
    calibrationLockState({
      lock: { locked: true },
      lock_owned_by_requester: true,
    }),
    {
      ownsLock: true,
      lockedByAnotherOperator: false,
    },
  );
  assert.deepEqual(
    calibrationLockState({
      lock: { locked: true },
      lock_owned_by_requester: false,
    }),
    {
      ownsLock: false,
      lockedByAnotherOperator: true,
    },
  );
});

test("suggested angles respect the configured motor-safe interval", () => {
  assert.deepEqual(
    suggestedCalibrationAngles([40, 190]),
    [45, 90, 135, 180],
  );
  assert.deepEqual(
    suggestedCalibrationAngles(undefined),
    [0, 45, 90, 135, 180, 225, 270, 315],
  );
});

test("rotating observation completion requires a real recorded angle", () => {
  const detection = {
    accepted: true,
    detections: {
      rotating: { board_detected: true },
    },
  };

  assert.equal(
    calibrationAngleCompleted([
      { ...detection, motor_angle_deg: null },
    ], 0),
    false,
  );
  assert.equal(
    calibrationAngleCompleted([
      { ...detection, motor_angle_deg: 89.8 },
    ], 90),
    true,
  );
});

test("automatic intrinsic capture explains accepted and rejected samples", () => {
  assert.deepEqual(
    intrinsicCaptureNotice("俯視角", {
      samples: [{ accepted: true }],
    }),
    {
      message: "俯視角已接受新的內參樣本。",
      tone: "success",
    },
  );
  assert.deepEqual(
    intrinsicCaptureNotice("側視角", {
      samples: [{
        accepted: false,
        rejection_reason: "姿態重複。",
      }],
    }),
    {
      message: "側視角樣本未儲存：姿態重複。",
      tone: "warning",
    },
  );
});

test("calibration page keeps errors in global notifications and confirms leaving", () => {
  const page = source("features/Calibration/Calibration.js");
  const hook = source("features/Calibration/hooks/useUnifiedCalibration.js");
  const status = source(
    "features/Calibration/components/CalibrationExtrinsicStatus.js",
  );

  assert.match(page, /useNotificationsContext/);
  assert.match(page, /showNotification\(error, "error"\)/);
  assert.match(page, /socketError\.message/);
  assert.doesNotMatch(page, /role="alert"/);
  assert.match(hook, /usePhytoSocket/);
  assert.match(hook, /snapshot\?\.calibration/);
  assert.match(hook, /CATALOG_REFRESH_INTERVAL_MS = 30_000/);
  assert.match(hook, /beforeunload/);
  assert.match(hook, /window\.confirm/);
  assert.match(hook, /\/api\/calibration\/lock\/refresh/);
  assert.match(status, /\/api\/calibration\/storage\/reconcile/);
  assert.match(status, /重新同步校正檔/);
  assert.doesNotMatch(status, /內參|相機已連線|校正板辨識/);
});

test("calibration intrinsics combine each camera preview with concise controls", () => {
  const intrinsics = source(
    "features/Calibration/components/CalibrationIntrinsics.js",
  );
  const cameraStream = source("components/media/CameraStream.js");
  const extrinsics = source(
    "features/Calibration/components/CalibrationExtrinsics.js",
  );

  assert.match(intrinsics, /<CameraStream/);
  assert.match(intrinsics, /min-\[720px\]:grid-cols-2/);
  assert.match(intrinsics, /min-\[1180px\]:grid-cols-3/);
  assert.doesNotMatch(intrinsics, /標記|角點|清晰度|去畸變預覽/);
  assert.match(cameraStream, /全螢幕/);
  assert.match(extrinsics, /role="list"/);
  assert.match(extrinsics, /aria-label="外參觀測品質"/);
});

test("analysis contains no calibration mutation UI and BFF exposes unified proxy", () => {
  const analysis = source("features/Analysis/AnalysisNew.js");
  const proxy = source("app/api/calibration/[...path]/route.js");

  assert.doesNotMatch(analysis, /CalibrationSetup|CalibrationStep/);
  assert.match(proxy, /backendPath\("\/api\/calibration", path\)/);
  assert.match(proxy, /handler as PATCH/);
  assert.match(proxy, /handler as POST/);
});
