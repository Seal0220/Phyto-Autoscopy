"use server";

import { redirect } from "next/navigation";

import { passwordsMatch } from "@/lib/authUtils";
import { createOperatorSession } from "@/lib/session";

export async function loginAction(
  _previousState,
  formData,
) {
  const configuredPassword = process.env.PHYTO_AUTOSCOPY_OPERATOR_PASSWORD;
  if (!configuredPassword) {
    console.error("Operator login is unavailable because authentication is not configured.");
    return { error: "登入服務尚未完成設定，請聯絡管理員。" };
  }

  const password = String(formData.get("password") || "");
  if (!passwordsMatch(password, configuredPassword)) {
    return { error: "密碼不正確。" };
  }

  try {
    await createOperatorSession();
  } catch (error) {
    console.error("Operator session creation failed", {
      type: error instanceof Error ? error.name : typeof error,
    });
    return { error: "登入服務暫時無法使用，請稍後再試。" };
  }
  redirect("/capture");
}
