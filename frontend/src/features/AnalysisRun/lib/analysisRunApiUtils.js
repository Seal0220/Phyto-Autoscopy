import {
  parseJsonResponse,
  RequestTimeoutError,
  responseErrorMessage,
  withRequestTimeout,
} from "@/lib/httpUtils";

import { analysisRunActionRequest } from "./analysisRunUtils";

export class UnknownAnalysisMutationOutcomeError extends Error {
  constructor(message) {
    super(message);
    this.name = "UnknownAnalysisMutationOutcomeError";
  }
}

function isUnknownMutationResponse(
  response,
  payload,
) {
  return response.status >= 500
    || [
      "BACKEND_TIMEOUT",
      "BACKEND_UNAVAILABLE",
      "BACKEND_INVALID_RESPONSE",
    ].includes(payload?.code);
}

export async function requestAnalysisResource(
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
          body: body === undefined
            ? undefined
            : JSON.stringify(body),
          signal: requestSignal,
        });
        const payload = await parseJsonResponse(response);

        if (!response.ok) {
          const fallback = isMutation
            ? "分析操作失敗。"
            : "讀取分析資料失敗。";
          const message = responseErrorMessage(payload, fallback);

          if (isMutation && isUnknownMutationResponse(response, payload)) {
            throw new UnknownAnalysisMutationOutcomeError(
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
    if (error instanceof UnknownAnalysisMutationOutcomeError) throw error;
    if (isMutation && (
      error instanceof RequestTimeoutError
      || error instanceof TypeError
    )) {
      throw new UnknownAnalysisMutationOutcomeError(
        "與後端的連線中斷，操作結果尚未確認。",
      );
    }
    throw error;
  }
}

function analysisPath(
  analysisId,
  suffix = "",
) {
  return `/api/analysis/${encodeURIComponent(analysisId)}${suffix}`;
}

export async function loadAnalysisRunBundle(
  analysisId,
  signal,
) {
  const [run, progress] = await Promise.all([
    requestAnalysisResource(analysisPath(analysisId), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/progress"), {
      signal,
    }),
  ]);

  const [rounds, models, landmarks, trajectory] = await Promise.all([
    requestAnalysisResource(analysisPath(analysisId, "/rounds"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/round-models"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/tip-landmarks"), {
      signal,
    }),
    requestAnalysisResource(analysisPath(analysisId, "/tip-trajectory"), {
      signal,
    }),
  ]);

  return {
    run,
    progress,
    formalData: {
      rounds: Array.isArray(rounds) ? rounds : [],
      models: Array.isArray(models) ? models : [],
      landmarks: Array.isArray(landmarks) ? landmarks : [],
      trajectory: Array.isArray(trajectory) ? trajectory : [],
    },
  };
}

function analysisActionTimeout(action) {
  if (["retry", "validate"].includes(action)) return 120_000;
  if (action === "reconstruct") return 60_000;
  return 30_000;
}

export function performAnalysisRunAction(
  analysisId,
  action,
  signal,
) {
  const request = analysisRunActionRequest(action);
  const encodedId = encodeURIComponent(analysisId);
  const encodedAction = encodeURIComponent(request.action);
  return requestAnalysisResource(
    `/api/analysis/${encodedId}/${encodedAction}`,
    {
      body: request.body,
      method: "POST",
      signal,
      timeoutMs: analysisActionTimeout(request.action),
    },
  );
}

function exportFilename(response) {
  const disposition = response.headers.get("content-disposition") || "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  let candidate = plain;
  if (encoded) {
    try {
      candidate = decodeURIComponent(encoded);
    } catch {
      candidate = plain;
    }
  }

  return candidate && /^[\w. -]+$/u.test(candidate)
    ? candidate
    : "analysis-export.zip";
}

export async function downloadAnalysisExport(
  analysisId,
  signal,
) {
  return withRequestTimeout(
    async (requestSignal) => {
      const response = await fetch(
        `/api/analysis/${encodeURIComponent(analysisId)}/export`,
        {
          cache: "no-store",
          signal: requestSignal,
        },
      );

      if (!response.ok) {
        const payload = await parseJsonResponse(response);
        throw new Error(responseErrorMessage(
          payload,
          "下載分析匯出檔失敗。",
        ));
      }

      return {
        blob: await response.blob(),
        filename: exportFilename(response),
      };
    },
    {
      signal,
      timeoutMs: 120_000,
    },
  );
}

export function loadRunCalibration(
  analysisId,
  signal,
) {
  return requestAnalysisResource(
    `/api/analysis/${encodeURIComponent(analysisId)}/calibration-reference`,
    {
      signal,
    },
  );
}
