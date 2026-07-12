import {
  NOTIFICATION_META,
} from "../notificationConfig";

export function notificationMeta(tone) {
  return NOTIFICATION_META[tone] || NOTIFICATION_META.info;
}
