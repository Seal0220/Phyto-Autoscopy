export const MOTOR_MOVEMENT_TIMEOUT_MS = 310000;
export const CAMERA_SINGLE_ACTION_TIMEOUT_MS = 60000;
export const CAMERA_GROUP_ACTION_TIMEOUT_MS = 120000;

export function motorProxyTimeout(path = []) {
  return [
    "move",
    "return-origin",
  ].includes(path[0])
    ? MOTOR_MOVEMENT_TIMEOUT_MS
    : undefined;
}

export function cameraProxyTimeout(path = []) {
  if ([
    "snapshot-all",
    "reconnect-all",
  ].includes(path[0])) {
    return CAMERA_GROUP_ACTION_TIMEOUT_MS;
  }

  if ([
    "snapshot",
    "reconnect",
  ].includes(path[1])) {
    return CAMERA_SINGLE_ACTION_TIMEOUT_MS;
  }

  return undefined;
}
