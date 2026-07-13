const STATIC_HTTP_ACTIONS = {
  "motor.emergency_stop": {
    endpoint: "/api/motor/emergency-stop",
  },
  "motor.move": {
    endpoint: "/api/motor/move",
    sendPayload: true,
  },
  "motor.return_origin": {
    endpoint: "/api/motor/return-origin",
  },
  "motor.stop": {
    endpoint: "/api/motor/stop",
  },
  "schedule.stop": {
    endpoint: "/api/schedules/stop",
  },
  "camera.snapshot_all": {
    endpoint: "/api/cameras/snapshot-all",
  },
  "camera.reconnect_all": {
    endpoint: "/api/cameras/reconnect-all",
  },
};

function cameraEndpoint(
  payload,
  suffix,
) {
  const cameraId = typeof payload?.camera_id === "string"
    ? payload.camera_id.trim()
    : "";

  if (!cameraId) {
    throw new Error("缺少相機識別碼。");
  }

  return `/api/cameras/${encodeURIComponent(cameraId)}/${suffix}`;
}

export function controlPanelHttpAction(
  action,
  payload = {},
) {
  if (action === "camera.snapshot") {
    return {
      endpoint: cameraEndpoint(
        payload,
        "snapshot",
      ),
    };
  }

  if (action === "camera.reconnect") {
    return {
      endpoint: cameraEndpoint(
        payload,
        "reconnect",
      ),
    };
  }

  const config = STATIC_HTTP_ACTIONS[action];

  if (!config) return null;
  return {
    endpoint: config.endpoint,
    body: config.sendPayload ? payload : null,
  };
}
