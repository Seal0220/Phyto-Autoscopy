import {
  mutationResponseOutcomeUnknown,
  mutationTransportOutcomeUnknown,
  parseJsonResponse,
  responseErrorMessage,
  UnknownMutationOutcomeError,
  withRequestTimeout,
} from "@/lib/httpUtils";

export async function requestUnifiedCalibration(
  path,
  {
    body,
    method = "GET",
    signal,
    timeoutMs = 30_000,
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
          body: body === undefined
            ? undefined
            : JSON.stringify(body),
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
              `${message} 操作結果尚未確認。`,
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
        "與後端的連線中斷，相機校正操作結果尚未確認。",
      );
    }
    throw error;
  }
}

export function loadUnifiedCalibrationWorkspace(signal) {
  return Promise.all([
    requestUnifiedCalibration("/api/calibration/status", { signal }),
    requestUnifiedCalibration("/api/calibration/boards", { signal }),
    requestUnifiedCalibration("/api/calibration/extrinsics", { signal }),
    ...["top", "side", "rotating"].map((cameraId) => (
      requestUnifiedCalibration(
        `/api/calibration/intrinsics/${cameraId}/runs`,
        { signal },
      )
    )),
  ]);
}
