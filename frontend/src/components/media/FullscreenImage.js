"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import {
  PiCornersInBold,
  PiCornersOutBold,
} from "react-icons/pi";

import Button from "@/components/buttons/Button";

const FULLSCREEN_TRANSITION_MS = 400;

export default function FullscreenImage({
  src,
  alt,
  label,
  children,
  onLoad,
  onError,
}) {
  const closeTimerRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [visible, setVisible] = useState(false);

  const closeFullscreen = useCallback(() => {
    const delay = window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? 0
      : FULLSCREEN_TRANSITION_MS;

    setVisible(false);
    window.clearTimeout(closeTimerRef.current);
    closeTimerRef.current = window.setTimeout(() => setOpen(false), delay);
  }, []);

  useEffect(() => {
    if (!open) return undefined;

    const previousOverflow = document.body.style.overflow;
    const animationFrame = window.requestAnimationFrame(() => setVisible(true));

    function closeOnEscape(event) {
      if (event.key === "Escape") closeFullscreen();
    }

    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);

    return () => {
      window.cancelAnimationFrame(animationFrame);
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [
    closeFullscreen,
    open,
  ]);

  useEffect(() => () => {
    window.clearTimeout(closeTimerRef.current);
  }, []);

  return (
    <>
      <Button
        className="absolute right-4 bottom-4 size-10 min-h-10 shrink-0 p-0! shadow-lg backdrop-blur-xl"
        aria-label={`放大檢視${label}`}
        title={`放大檢視${label}`}
        onClick={() => {
          window.clearTimeout(closeTimerRef.current);
          setOpen(true);
        }}
      >
        <PiCornersOutBold
          className="size-6 shrink-0"
          aria-hidden="true"
        />
      </Button>

      {open && createPortal(
        <div
          className={`fixed inset-0 z-300 flex items-center justify-center bg-[#06100c]/95 p-4 transition-opacity duration-400 ease-in-out motion-reduce:transition-none ${
            visible ? "opacity-100" : "opacity-0"
          }`}
          role="dialog"
          aria-label={`${label}全螢幕預覽`}
          aria-modal="true"
          onPointerDown={(event) => {
            if (event.target === event.currentTarget) closeFullscreen();
          }}
        >
          <div
            className={`relative flex size-full min-h-0 min-w-0 items-center justify-center transition-[opacity,transform] duration-400 ease-in-out motion-reduce:transform-none motion-reduce:transition-none ${
              visible ? "scale-100 opacity-100" : "scale-95 opacity-0"
            }`}
            onPointerDown={(event) => {
              if (event.target === event.currentTarget) closeFullscreen();
            }}
          >
            {/* 全螢幕檢視需直接接受串流、Blob 與動態檔案 URL。 */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              className="block size-full object-contain"
              src={src}
              alt={alt}
              onLoad={onLoad}
              onError={onError}
            />
            {children}
            <Button
              className="absolute top-0 right-0 z-30 size-10 min-h-10 shrink-0 p-0! shadow-lg backdrop-blur-xl"
              aria-label={`關閉${label}全螢幕檢視`}
              title="關閉全螢幕檢視"
              onClick={closeFullscreen}
            >
              <PiCornersInBold
                className="size-6 shrink-0"
                aria-hidden="true"
              />
            </Button>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
