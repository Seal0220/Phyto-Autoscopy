"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  abortRequest,
  messageFromError,
  parseJsonResponse,
  responseErrorMessage,
} from "@/lib/httpUtils";

import {
  recordExportFilename,
  recordExportMeta,
} from "../lib/storageUtils";

export default function useRecordExport({
  onNotify,
}) {
  const [exportingKeys, setExportingKeys] = useState(() => new Set());
  const mountedRef = useRef(false);
  const pendingExportsRef = useRef(new Map());

  useEffect(() => {
    const pendingExports = pendingExportsRef.current;
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;

      for (const pending of pendingExports.values()) {
        abortRequest(pending.controller);
      }

      pendingExports.clear();
    };
  }, []);

  const exportRecord = useCallback((
    recordId,
    format,
  ) => {
    const key = `${recordId}:${format}`;
    const existing = pendingExportsRef.current.get(key);

    if (existing) return existing.request;

    const controller = new AbortController();
    let request;

    request = (async () => {
      let anchor = null;
      let objectUrl = null;

      try {
        const meta = recordExportMeta(format);
        const response = await fetch(
          `/api/records/${encodeURIComponent(recordId)}/${meta.endpoint}`,
          {
            cache: "no-store",
            signal: controller.signal,
          },
        );

        if (!response.ok) {
          const payload = await parseJsonResponse(response);
          throw new Error(responseErrorMessage(
            payload,
            `匯出${meta.label}失敗。`,
          ));
        }

        const blob = await response.blob();

        if (!blob.size) {
          throw new Error(`匯出的${meta.label}檔案沒有內容。`);
        }

        if (!mountedRef.current || controller.signal.aborted) {
          return false;
        }

        objectUrl = URL.createObjectURL(blob);
        anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = recordExportFilename(
          recordId,
          meta.filenameSuffix,
        );
        anchor.hidden = true;
        document.body.append(anchor);
        anchor.click();
        onNotify?.(`已下載 ${recordId} 的${meta.label}紀錄。`, "success");
        return true;
      } catch (error) {
        if (error?.name === "AbortError") return false;

        if (mountedRef.current) {
          onNotify?.(messageFromError(error, "匯出紀錄失敗。"), "error");
        }

        return false;
      } finally {
        anchor?.remove();

        if (objectUrl) {
          URL.revokeObjectURL(objectUrl);
        }

        if (pendingExportsRef.current.get(key)?.request === request) {
          pendingExportsRef.current.delete(key);

          if (mountedRef.current) {
            setExportingKeys(new Set(pendingExportsRef.current.keys()));
          }
        }
      }
    })();

    pendingExportsRef.current.set(key, {
      controller,
      request,
    });
    setExportingKeys(new Set(pendingExportsRef.current.keys()));
    return request;
  }, [onNotify]);

  return {
    exportingKeys,
    exportRecord,
  };
}
