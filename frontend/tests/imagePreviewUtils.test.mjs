import assert from "node:assert/strict";
import test from "node:test";

import {
  formatImagePreviewFps,
  imagePreviewDeviceOptions,
  serializeImagePreviewSettingsPayload,
  unavailableImagePreviewAssignments,
} from "../src/features/ImagePreview/lib/imagePreviewUtils.js";

test("image preview FPS uses a stable whole-number display", () => {
  assert.equal(formatImagePreviewFps(29.6), "30");
  assert.equal(formatImagePreviewFps(0), "0");
  assert.equal(formatImagePreviewFps(undefined), "0");
  assert.equal(formatImagePreviewFps("invalid"), "0");
});

test("image preview device options follow the unsaved camera assignment draft", () => {
  const scanResults = [
    {
      camera_id: "top",
      device_index: 0,
      connected: true,
      in_use: true,
      camera_name: "TOP CAMERA",
    },
    {
      camera_id: "side",
      device_index: 1,
      connected: true,
      in_use: true,
      camera_name: "SIDE CAMERA",
    },
  ];
  const cameraDrafts = {
    top: {
      enabled: true,
      device_index: 1,
    },
    side: {
      enabled: true,
      device_index: 0,
    },
  };

  const options = imagePreviewDeviceOptions(
    scanResults,
    "top",
    cameraDrafts,
  );

  assert.deepEqual(options, [
    {
      value: "",
      label: "無",
    },
    {
      value: "1",
      label: "裝置 1 SIDE CAMERA",
    },
  ]);
});

test("image preview settings serialize device indices and reject duplicates", () => {
  const payload = {
    cameras: {
      top: {
        enabled: true,
        device_index: "3",
      },
      side: {
        enabled: true,
        device_index: "4",
      },
      rotating: {
        enabled: false,
        device_index: "",
      },
    },
  };

  const serialized = serializeImagePreviewSettingsPayload(payload);

  assert.equal(serialized.cameras.top.device_index, 3);
  assert.equal(serialized.cameras.side.device_index, 4);
  assert.equal(serialized.cameras.rotating.device_index, null);
  assert.throws(
    () => serializeImagePreviewSettingsPayload({
      cameras: {
        ...payload.cameras,
        rotating: {
          enabled: true,
          device_index: "4",
        },
      },
    }),
    /裝置 4 不可同時指派給側視角與旋臂視角/,
  );
  assert.throws(
    () => serializeImagePreviewSettingsPayload({
      cameras: {
        ...payload.cameras,
        rotating: {
          enabled: true,
          device_index: "",
        },
      },
    }),
    /旋臂視角已啟用，請先選擇裝置/,
  );
});

test("image preview device options show only usable device names", () => {
  const options = imagePreviewDeviceOptions(
    [
      {
        camera_id: "top",
        device_index: 0,
        connected: true,
        in_use: true,
        backend: "MOCK",
        mock: true,
        camera_name: "TOP CAMERA",
      },
      {
        device_index: 1,
        connected: true,
        in_use: false,
        backend: "MSMF",
        mock: false,
        camera_name: "USB CAMERA",
      },
      {
        device_index: 2,
        connected: false,
        camera_name: "OFFLINE CAMERA",
      },
    ],
    "top",
    {
      top: {
        enabled: true,
        device_index: 0,
      },
    },
  );

  assert.deepEqual(options, [
    {
      value: "",
      label: "無",
    },
    {
      value: "0",
      label: "裝置 0 TOP CAMERA",
    },
    {
      value: "1",
      label: "裝置 1 USB CAMERA",
    },
  ]);
});

test("image preview unavailable assignments return only detected misses", () => {
  const unavailable = unavailableImagePreviewAssignments(
    {
      cameras: {
        top: {
          device_index: 0,
        },
        side: {
          device_index: 1,
        },
        rotating: {
          device_index: null,
        },
      },
    },
    [
      {
        device_index: 0,
        connected: true,
      },
      {
        device_index: 1,
        connected: false,
      },
    ],
  );

  assert.deepEqual(unavailable, ["side"]);
});
