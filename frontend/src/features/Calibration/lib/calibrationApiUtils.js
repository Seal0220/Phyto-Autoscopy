import {
  mutationResponseOutcomeUnknown,
  mutationTransportOutcomeUnknown,
  parseJsonResponse,
  responseErrorMessage,
  UnknownMutationOutcomeError,
  withRequestTimeout,
} from "@/lib/httpUtils";

async function requestCalibrationJson(
  path,
  {
    body,
    method = "GET",
    signal,
    timeoutMs = 20_000,
  } = {},
) {
  const isMutation = method !== "GET";

  try {
    return await withRequestTimeout(
      async (requestSignal) => {
        const response = await fetch(path, {
          cache: "no-store",
          method,
          headers: body === undefined
            ? undefined
            : {
              "Content-Type": "application/json",
            },
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: requestSignal,
        });
        const payload = await parseJsonResponse(response);
        if (!response.ok) {
          const message = responseErrorMessage(
            payload,
            isMutation
              ? "相機校正操作失敗。"
              : "讀取相機校正資料失敗。",
          );

          if (
            isMutation
            && mutationResponseOutcomeUnknown(response, payload)
          ) {
            throw new UnknownMutationOutcomeError(
              /尚未確認/.test(message)
                ? message
                : `${message} 操作結果尚未確認。`,
            );
          }
          throw new Error(message);
        }
        return payload;
      },
      {
        signal,
        timeoutMs,
      },
    );
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    if (error instanceof UnknownMutationOutcomeError) throw error;
    if (isMutation && mutationTransportOutcomeUnknown(error)) {
      throw new UnknownMutationOutcomeError(
        "與後端的連線中斷，操作結果尚未確認。",
      );
    }
    throw error;
  }
}

export function loadCalibrationCatalog(signal) {
  return Promise.all([
    requestCalibrationJson("/api/calibrations", {
      signal,
    }),
    requestCalibrationJson("/api/calibrations/source-images?limit=1000", {
      signal,
      timeoutMs: 30_000,
    }),
  ]);
}

export function createCalibration(
  payload,
  signal,
) {
  return requestCalibrationJson("/api/calibrations", {
    body: payload,
    method: "POST",
    signal,
    timeoutMs: 60_000,
  });
}

export function loadCalibrationDetail(
  calibrationId,
  signal,
) {
  const encoded = encodeURIComponent(calibrationId);
  return Promise.all([
    requestCalibrationJson(`/api/calibrations/${encoded}`, {
      signal,
    }),
    requestCalibrationJson(`/api/calibrations/${encoded}/report`, {
      signal,
    }),
  ]);
}

export function runCalibrationStep(
  calibrationId,
  step,
  signal,
) {
  const paths = {
    corners: "detect-corners",
    intrinsics: "solve-intrinsics",
    stereo: "solve-stereo",
    rotating: "solve-rotating",
    validate: "validate",
  };
  const path = paths[step];
  if (!path) throw new Error("未知的相機校正步驟。");
  return requestCalibrationJson(
    `/api/calibrations/${encodeURIComponent(calibrationId)}/${path}`,
    {
      body: {},
      method: "POST",
      signal,
      timeoutMs: 120_000,
    },
  );
}

export function deleteCalibration(
  calibrationId,
  signal,
) {
  return requestCalibrationJson(
    `/api/calibrations/${encodeURIComponent(calibrationId)}`,
    {
      method: "DELETE",
      signal,
      timeoutMs: 30_000,
    },
  );
}
