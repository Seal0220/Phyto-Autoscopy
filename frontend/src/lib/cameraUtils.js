import {
  mutationResponseOutcomeUnknown,
  mutationTransportOutcomeUnknown,
  parseJsonResponse,
  responseErrorMessage,
  UnknownMutationOutcomeError,
} from "@/lib/httpUtils";

export async function updateCameraMeteringRegion(
  cameraId,
  region,
) {
  try {
    const response = await fetch(
      `/api/cameras/${encodeURIComponent(cameraId)}/metering-region`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(region),
      },
    );
    const payload = await parseJsonResponse(response);

    if (!response.ok) {
      const message = responseErrorMessage(
        payload,
        "儲存測光區域失敗。",
      );
      if (mutationResponseOutcomeUnknown(response, payload)) {
        throw new UnknownMutationOutcomeError(
          `${message} 套用結果未知，請確認相機狀態後再調整。`,
        );
      }
      throw new Error(message);
    }

    return payload;
  } catch (error) {
    if (error instanceof UnknownMutationOutcomeError) throw error;
    if (mutationTransportOutcomeUnknown(error)) {
      throw new UnknownMutationOutcomeError(
        "儲存測光區域時連線中斷，套用結果未知，請確認相機狀態後再調整。",
      );
    }
    throw error;
  }
}
