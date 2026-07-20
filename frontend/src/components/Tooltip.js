"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

const VIEWPORT_MARGIN = 16;
const TOOLTIP_GAP = 8;

export default function Tooltip({
  children,
  className,
}) {
  const anchorRef = useRef(null);
  const tooltipRef = useRef(null);
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState({
    left: VIEWPORT_MARGIN,
    top: VIEWPORT_MARGIN,
  });

  const updatePosition = useCallback(() => {
    const anchor = anchorRef.current?.parentElement;
    const tooltip = tooltipRef.current;
    if (!anchor || !tooltip) return;

    const anchorRect = anchor.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    const maximumLeft = Math.max(
      VIEWPORT_MARGIN,
      window.innerWidth - tooltipRect.width - VIEWPORT_MARGIN,
    );
    const left = Math.min(
      Math.max(VIEWPORT_MARGIN, anchorRect.left),
      maximumLeft,
    );
    const belowTop = anchorRect.bottom + TOOLTIP_GAP;
    const top = belowTop + tooltipRect.height <= window.innerHeight - VIEWPORT_MARGIN
      ? belowTop
      : Math.max(
        VIEWPORT_MARGIN,
        anchorRect.top - tooltipRect.height - TOOLTIP_GAP,
      );

    setPosition({
      left,
      top,
    });
  }, []);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const anchor = anchorRef.current?.parentElement;
    if (!anchor) return undefined;

    const show = () => setVisible(true);
    const hide = () => setVisible(false);
    anchor.addEventListener("mouseenter", show);
    anchor.addEventListener("mouseleave", hide);

    return () => {
      anchor.removeEventListener("mouseenter", show);
      anchor.removeEventListener("mouseleave", hide);
    };
  }, []);

  useLayoutEffect(() => {
    if (!visible) return undefined;

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [
    updatePosition,
    visible,
  ]);

  return (
    <>
      <span
        className="hidden"
        ref={anchorRef}
        aria-hidden="true"
      />
      {mounted && createPortal(
        <span
          className={`pointer-events-none fixed z-350 w-max max-w-[min(22rem,calc(100vw-2rem))] rounded-lg border border-white/15 bg-[#07130f]/95 px-3 py-2 text-xs font-semibold leading-5 text-neutral-200 shadow-xl backdrop-blur-xl transition-opacity duration-150 ${
            visible
              ? "opacity-100 delay-0"
              : "opacity-0 delay-150"
          } ${className || ""}`}
          style={{
            ...position,
            right: "auto",
            bottom: "auto",
            transform: "none",
          }}
          role="tooltip"
          aria-hidden={!visible}
          ref={tooltipRef}
        >
          {children}
        </span>,
        document.body,
      )}
    </>
  );
}
