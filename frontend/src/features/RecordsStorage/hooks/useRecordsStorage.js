"use client";

import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  messageFromError,
  parseJsonResponse,
} from "@/lib/httpUtils";

export default function useRecordsStorage({
  onNotify,
}) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadRecords = useCallback(async () => {
    setLoading(true);

    try {
      const response = await fetch("/api/sessions", {
        cache: "no-store",
      });
      const payload = await parseJsonResponse(response);

      if (!response.ok) {
        throw new Error(payload.detail || "讀取紀錄失敗。");
      }

      setRecords(Array.isArray(payload) ? payload : []);
    } catch (error) {
      onNotify(messageFromError(error, "讀取紀錄失敗。"), "error");
    } finally {
      setLoading(false);
    }
  }, [onNotify]);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  return {
    records,
    loading,
    loadRecords,
  };
}
