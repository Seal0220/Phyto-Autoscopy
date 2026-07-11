"use server";

import crypto from "node:crypto";

import { redirect } from "next/navigation";

import { createOperatorSession } from "@/lib/session";

function passwordsMatch(supplied, configured) {
  const left = Buffer.from(supplied || "");
  const right = Buffer.from(configured || "");
  return left.length === right.length && crypto.timingSafeEqual(left, right);
}

export async function loginAction(_previousState, formData) {
  const configuredPassword = process.env.PHYTO_AUTOSCOPY_OPERATOR_PASSWORD;
  if (!configuredPassword) {
    return { error: "尚未設定 PHYTO_AUTOSCOPY_OPERATOR_PASSWORD。" };
  }

  const password = String(formData.get("password") || "");
  if (!passwordsMatch(password, configuredPassword)) {
    return { error: "密碼不正確。" };
  }

  await createOperatorSession();
  redirect("/");
}
