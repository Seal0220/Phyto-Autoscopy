"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";
import {
  FiAlertOctagon,
  FiLogOut,
} from "react-icons/fi";
import { PiPlantFill } from "react-icons/pi";
import { usePathname } from "next/navigation";

import Button from "@/components/buttons/Button";
import NavLink from "@/components/navigation/NavLink";
import { StatusPill } from "@/components/panels/Panel";
import useNotificationsContext from "@/features/Notifications/hooks/useNotificationsContext";
import {
  abortRequest,
  messageFromError,
  RequestTimeoutError,
} from "@/lib/httpUtils";

import { MAIN_NAVIGATION_ITEMS } from "./mainNavigationConfig";
import { postMainNavigationAction } from "./lib/mainNavigationApiUtils";
import { isMainNavigationItemActive } from "./lib/mainNavigationUtils";

export default function MainNavigation({
  isConnected = null,
  emergencyStopping = false,
  logoutPending = false,
  onEmergencyStop,
  onLogout,
  secondaryItems = [],
}) {
  const pathname = usePathname();
  const { showNotification } = useNotificationsContext();
  const [localEmergencyPending, setLocalEmergencyPending] = useState(false);
  const [localLogoutPending, setLocalLogoutPending] = useState(false);
  const mountedRef = useRef(false);
  const emergencyControllerRef = useRef(null);
  const logoutControllerRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      abortRequest(emergencyControllerRef.current);
      abortRequest(logoutControllerRef.current);
    };
  }, []);

  async function handleEmergencyStop() {
    if (onEmergencyStop) {
      onEmergencyStop();
      return;
    }

    if (localEmergencyPending) return;

    const controller = new AbortController();
    emergencyControllerRef.current = controller;
    setLocalEmergencyPending(true);

    try {
      await postMainNavigationAction(
        "/api/motor/emergency-stop",
        "緊急停止失敗，請立即檢查設備狀態。",
        controller.signal,
      );
    } catch (error) {
      if (error?.name === "AbortError" && !mountedRef.current) return;

      const fallback = error instanceof RequestTimeoutError
        ? "緊急停止要求逾時，操作結果尚未確認，請立即檢查設備狀態。"
        : "緊急停止失敗，請立即檢查設備狀態。";

      if (mountedRef.current) {
        showNotification(
          error instanceof RequestTimeoutError
            || error instanceof TypeError
            ? fallback
            : messageFromError(
              error,
              fallback,
          ),
          "error",
        );
      }
    } finally {
      if (emergencyControllerRef.current === controller) {
        emergencyControllerRef.current = null;

        if (mountedRef.current) {
          setLocalEmergencyPending(false);
        }
      }
    }
  }

  async function handleLogout() {
    if (onLogout) {
      onLogout();
      return;
    }

    if (localLogoutPending) return;

    const controller = new AbortController();
    logoutControllerRef.current = controller;
    setLocalLogoutPending(true);

    try {
      await postMainNavigationAction(
        "/api/auth/logout",
        "登出失敗，請稍後重試。",
        controller.signal,
      );
      window.location.assign("/");
    } catch (error) {
      if (error?.name === "AbortError" && !mountedRef.current) return;

      const fallback = error instanceof RequestTimeoutError
        ? "登出要求逾時，請重新整理後確認登入狀態。"
        : "登出失敗，請稍後重試。";

      if (mountedRef.current) {
        showNotification(
          error instanceof RequestTimeoutError
            || error instanceof TypeError
            ? fallback
            : messageFromError(
              error,
              fallback,
          ),
          "error",
        );
      }
    } finally {
      if (logoutControllerRef.current === controller) {
        logoutControllerRef.current = null;

        if (mountedRef.current) {
          setLocalLogoutPending(false);
        }
      }
    }
  }

  const hasSecondaryNavigation = secondaryItems.length > 0;
  const effectiveEmergencyPending = emergencyStopping
    || localEmergencyPending;
  const effectiveLogoutPending = logoutPending
    || localLogoutPending;

  return (
    <header className="fixed inset-x-0 top-0 z-300 border-b border-white/10 bg-[#07110d]/90 px-5 py-3 shadow-[0_14px_42px_rgba(0,0,0,0.14)] backdrop-blur-2xl max-[980px]:px-3 max-[980px]:py-2">
      <div className="mx-auto grid w-full grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-4 max-[980px]:grid-cols-[minmax(0,1fr)_auto] max-[980px]:gap-2">
        <div className="grid min-w-0 grid-cols-[2.25rem_minmax(0,1fr)] items-center gap-3">
          <span
            className="grid size-9 place-items-center rounded-2xl border border-emerald-200/20 bg-emerald-300/10"
            aria-hidden="true"
          >
            <PiPlantFill className="size-5 text-emerald-200" />
          </span>
          <div className="min-w-0">
            <strong className="block overflow-hidden text-sm font-black tracking-[0.08em] text-white text-ellipsis whitespace-nowrap">
              PHYTO-AUTOSCOPY
            </strong>
            <span className="block pt-0.5 text-[11px] font-bold text-neutral-300">
              控制台
            </span>
          </div>
        </div>

        <div className="flex flex-row gap-4 justify-center items-center">
          <nav
            className="flex min-w-0 items-center gap-1 overflow-x-auto rounded-2xl border border-white/10 bg-black/10 p-1 max-[980px]:col-span-full max-[980px]:row-start-2 max-[980px]:w-full"
            aria-label="主要導覽"
          >
            {MAIN_NAVIGATION_ITEMS.map((item) => {
              const active = isMainNavigationItemActive(
                pathname,
                item.href,
              );

              return (
                <NavLink
                  href={item.href}
                  key={item.href}
                  aria-current={active ? "page" : undefined}
                  className={active
                    ? "border border-emerald-200/40 bg-emerald-400/15 text-emerald-100 hover:border-emerald-100/60 hover:bg-emerald-300/20 hover:text-emerald-50"
                    : "border border-transparent"
                  }
                >
                  {item.label}
                </NavLink>
              );
            })}
          </nav>

          {hasSecondaryNavigation ? (
            <nav
              className="flex min-w-0 items-center gap-1 overflow-x-auto rounded-2xl border border-white/10 bg-black/10 p-1 max-[980px]:col-span-full max-[980px]:row-start-2 max-[980px]:w-full"
              aria-label="捕捉頁面導覽"
            >
              {secondaryItems.map((item) => (
                <NavLink
                  href={item.href}
                  key={item.href}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          ) : null}
        </div>

        <div className="col-start-3 flex min-w-0 items-center justify-end gap-2 max-[980px]:col-start-2 max-[980px]:row-start-1">
          {isConnected !== null ? (
            <div className="max-[720px]:hidden">
              <StatusPill tone={isConnected ? "success" : "warning"}>
                {isConnected ? "即時連線已建立" : "即時連線中"}
              </StatusPill>
            </div>
          ) : null}
          <Button
            className="min-h-9 px-3 text-xs"
            variant="danger"
            disabled={effectiveEmergencyPending}
            onClick={() => void handleEmergencyStop()}
          >
            <FiAlertOctagon
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            緊急停止
          </Button>
          <Button
            className="min-h-9 px-3 text-xs"
            disabled={effectiveLogoutPending}
            onClick={() => void handleLogout()}
          >
            <FiLogOut
              className="size-4 shrink-0"
              aria-hidden="true"
            />
            {effectiveLogoutPending ? "登出中…" : "登出"}
          </Button>
        </div>
      </div>
    </header>
  );
}
