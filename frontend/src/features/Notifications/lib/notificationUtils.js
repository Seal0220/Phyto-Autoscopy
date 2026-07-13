import {
  NOTIFICATION_META,
} from "../notificationConfig";

export function notificationMeta(tone) {
  return NOTIFICATION_META[tone] || NOTIFICATION_META.info;
}

export function normalizeSystemError(value) {
  if (typeof value !== "string") {
    return "系統回報未知錯誤。";
  }

  const message = value.trim();

  if (
    !message
    || message.length > 500
    || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(message)
  ) {
    return "系統回報未知錯誤。";
  }

  return message;
}
