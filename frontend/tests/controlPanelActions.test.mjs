import assert from "node:assert/strict";
import test from "node:test";

import { controlPanelHttpAction } from "../src/features/ControlPanel/lib/controlPanelActionUtils.js";
import {
  CAMERA_GROUP_ACTION_TIMEOUT_MS,
  CAMERA_SINGLE_ACTION_TIMEOUT_MS,
  MOTOR_MOVEMENT_TIMEOUT_MS,
  cameraProxyTimeout,
  motorProxyTimeout,
} from "../src/lib/proxyTimeoutUtils.js";

test("blocking motor actions use independent HTTP endpoints and extended proxy timeouts", () => {
  assert.deepEqual(
    controlPanelHttpAction("motor.move", { angle_deg: 45 }),
    {
      endpoint: "/api/motor/move",
      body: { angle_deg: 45 },
    },
  );
  assert.deepEqual(
    controlPanelHttpAction("motor.return_origin"),
    {
      endpoint: "/api/motor/return-origin",
      body: null,
    },
  );
  assert.equal(motorProxyTimeout(["move"]), MOTOR_MOVEMENT_TIMEOUT_MS);
  assert.equal(motorProxyTimeout(["return-origin"]), MOTOR_MOVEMENT_TIMEOUT_MS);
  assert.equal(motorProxyTimeout(["stop"]), undefined);
});

test("camera snapshot and reconnect actions use scoped HTTP endpoints and timeouts", () => {
  assert.deepEqual(
    controlPanelHttpAction("camera.snapshot", { camera_id: "side" }),
    {
      endpoint: "/api/cameras/side/snapshot",
    },
  );
  assert.deepEqual(
    controlPanelHttpAction("camera.snapshot_all"),
    {
      endpoint: "/api/cameras/snapshot-all",
      body: null,
    },
  );
  assert.equal(cameraProxyTimeout(["snapshot-all"]), CAMERA_GROUP_ACTION_TIMEOUT_MS);
  assert.equal(cameraProxyTimeout(["scan"]), CAMERA_GROUP_ACTION_TIMEOUT_MS);
  assert.equal(cameraProxyTimeout(["top", "snapshot"]), CAMERA_SINGLE_ACTION_TIMEOUT_MS);
  assert.equal(cameraProxyTimeout(["top", "status"]), undefined);
});

test("unknown actions stay on WebSocket and camera actions require an identifier", () => {
  assert.equal(controlPanelHttpAction("motor.engage"), null);
  assert.throws(
    () => controlPanelHttpAction("camera.snapshot", {}),
    /缺少相機識別碼/,
  );
});
