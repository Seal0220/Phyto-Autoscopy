import {
  parseJsonResponse,
  responseErrorMessage,
} from "@/lib/httpUtils";

import { controlPanelHttpAction } from "./controlPanelActionUtils";

function responseError(
  payload,
  fallback,
) {
  const error = new Error(responseErrorMessage(
    payload,
    fallback,
  ));

  if (typeof payload?.code === "string" && payload.code.trim()) {
    error.code = payload.code.trim();
  }

  return error;
}

export async function executeControlPanelAction({
  action,
  payload,
  command,
}) {
  const httpAction = controlPanelHttpAction(
    action,
    payload,
  );

  if (!httpAction) {
    return command(action, payload);
  }

  const requestOptions = {
    method: "POST",
  };

  if (httpAction.body) {
    requestOptions.headers = {
      "Content-Type": "application/json",
    };
    requestOptions.body = JSON.stringify(httpAction.body);
  }

  const response = await fetch(
    httpAction.endpoint,
    requestOptions,
  );
  const result = await parseJsonResponse(response);

  if (!response.ok) {
    throw responseError(
      result,
      "操作執行失敗。",
    );
  }

  return result;
}
