"use client";

import { useEffect, useRef, useState } from "react";
import { TRAJECTORY_METRIC_CHART } from "../trajectoryViewerConfig";

export default function useTrajectoryChartSize({
  enabled,
}) {
  const elementRef = useRef(null);
  const [size, setSize] = useState({ width: TRAJECTORY_METRIC_CHART.width, height: TRAJECTORY_METRIC_CHART.height });
  useEffect(() => {
    if (!enabled) return undefined;
    const element = elementRef.current;
    if (!element) return undefined;
    const update = () => {
      const width = element.clientWidth, height = element.clientHeight;
      if (!width || !height) return;
      setSize((previous) => previous.width === width && previous.height === height ? previous : { width, height });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [enabled]);
  return { elementRef, ...size };
}
