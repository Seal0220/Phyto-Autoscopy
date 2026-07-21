import {
  mutationResponseOutcomeUnknown,
  mutationTransportOutcomeUnknown,
  parseJsonResponse,
  RequestTimeoutError,
  responseErrorMessage,
  UnknownMutationOutcomeError,
  withRequestTimeout,
} from "@/lib/httpUtils";

async function requestAnalysisJson(
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
              ? "分析操作失敗。"
              : "讀取分析資料失敗。",
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

export function loadAnalysisDashboard(signal) {
  return Promise.all([
    requestAnalysisJson("/api/analysis/sources", {
      signal,
    }),
    requestAnalysisJson("/api/analysis", {
      signal,
    }),
  ]);
}

export function loadAnalysisSetupOptions(signal) {
  return requestAnalysisJson("/api/analysis/sources", {
    signal,
  });
}

export function createAnalysisRun(
  payload,
  signal,
) {
  return requestAnalysisJson("/api/analysis", {
    body: payload,
    method: "POST",
    signal,
    timeoutMs: 30_000,
  });
}

export function previewAnalysisSources(
  payload,
  signal,
) {
  return requestAnalysisJson("/api/analysis/sources/preview", {
    body: payload,
    method: "POST",
    signal,
    timeoutMs: 60_000,
  });
}

export function validateAnalysisRun(
  analysisId,
  signal,
) {
  return requestAnalysisJson(
    `/api/analysis/${encodeURIComponent(analysisId)}/validate`,
    {
      body: {},
      method: "POST",
      signal,
      timeoutMs: 60_000,
    },
  );
}

export function startAnalysisRun(
  analysisId,
  signal,
) {
  return requestAnalysisJson(
    `/api/analysis/${encodeURIComponent(analysisId)}/start`,
    {
      body: {},
      method: "POST",
      signal,
      timeoutMs: 30_000,
    },
  );
}

export function analysisMutationErrorMessage(
  error,
  action,
) {
  if (error instanceof UnknownMutationOutcomeError) {
    return `${error.message} 請先返回分析首頁確認狀態，勿立即重送。`;
  }
  if (error instanceof RequestTimeoutError) {
    return `${action}要求逾時，操作結果尚未確認。請先返回分析首頁確認狀態，勿立即重送。`;
  }
  return error instanceof Error && error.message
    ? error.message
    : `${action}失敗，請稍後重試。`;
}
