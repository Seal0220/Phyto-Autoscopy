"use client";

import { useContext } from "react";

import NotificationsContext from "../NotificationsContext";

export default function useNotificationsContext() {
  const context = useContext(NotificationsContext);

  if (!context) {
    throw new Error("通知功能必須在 NotificationsProvider 內使用。");
  }

  return context;
}
