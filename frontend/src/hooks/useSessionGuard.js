"use client";

import {
  useCallback,
  useEffect,
  useRef,
} from "react";

import { abortRequest } from "@/lib/httpUtils";

const SESSION_CHECK_INTERVAL_MS = 5 * 60 * 1000;

export default function useSessionGuard() {
  const mountedRef = useRef(false);
  const checkingRef = useRef(false);
  const controllerRef = useRef(null);

  const checkSession = useCallback(async () => {
    if (
      !mountedRef.current
      || checkingRef.current
      || document.visibilityState !== "visible"
    ) {
      return;
    }

    const controller = new AbortController();
    controllerRef.current = controller;
    checkingRef.current = true;

    try {
      const response = await fetch("/api/auth/session", {
        cache: "no-store",
        signal: controller.signal,
      });

      if ([401, 403].includes(response.status)) {
        window.location.replace("/");
      }
    } catch (error) {
      if (error?.name !== "AbortError") {
        // A temporary network failure must not discard a still-valid session.
      }
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        checkingRef.current = false;
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void checkSession();
      }
    };
    const handleOnline = () => {
      void checkSession();
    };
    const interval = window.setInterval(
      () => void checkSession(),
      SESSION_CHECK_INTERVAL_MS,
    );

    document.addEventListener(
      "visibilitychange",
      handleVisibilityChange,
    );
    window.addEventListener("online", handleOnline);
    void checkSession();

    return () => {
      mountedRef.current = false;
      checkingRef.current = false;
      window.clearInterval(interval);
      document.removeEventListener(
        "visibilitychange",
        handleVisibilityChange,
      );
      window.removeEventListener("online", handleOnline);
      abortRequest(controllerRef.current);
      controllerRef.current = null;
    };
  }, [checkSession]);
}
