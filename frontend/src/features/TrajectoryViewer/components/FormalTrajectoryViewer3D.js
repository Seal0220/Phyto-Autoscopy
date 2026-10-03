"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { FiRotateCcw } from "react-icons/fi";

import Button from "@/components/buttons/Button";
import RetryMessage from "@/components/feedback/RetryMessage";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import InnerPanel from "@/components/panels/InnerPanel";

import { buildFormalTrajectoryPlot } from "../lib/trajectoryUtils";

const DEFAULT_CAMERA = {
  eye: { x: 1.55, y: 1.55, z: 1.15 },
  up: { x: 0, y: 0, z: 1 },
};

const AXIS_STYLE = {
  showbackground: true,
  backgroundcolor: "#0b1a14",
  gridcolor: "rgba(255,255,255,0.15)",
  linecolor: "#a3a3a3",
  tickcolor: "#a3a3a3",
  tickfont: { color: "#a3a3a3", size: 11 },
  zerolinecolor: "rgba(110,231,183,0.55)",
};

function defaultCamera() {
  return {
    eye: { ...DEFAULT_CAMERA.eye },
    up: { ...DEFAULT_CAMERA.up },
  };
}

function plotLayout() {
  return {
    autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#e5e5e5", size: 12 },
    margin: { l: 0, r: 0, t: 8, b: 72 },
    showlegend: true,
    legend: {
      orientation: "h",
      x: 0,
      y: -0.04,
      yanchor: "top",
      font: { color: "#d4d4d4", size: 11 },
      bgcolor: "rgba(0,0,0,0)",
    },
    scene: {
      bgcolor: "rgba(0,0,0,0)",
      aspectmode: "data",
      camera: defaultCamera(),
      xaxis: { ...AXIS_STYLE, title: { text: "X（mm）" } },
      yaxis: { ...AXIS_STYLE, title: { text: "Y（mm）" } },
      zaxis: { ...AXIS_STYLE, title: { text: "Z（mm）" } },
    },
    uirevision: "trajectory-camera",
  };
}

const PLOT_CONFIG = {
  displaylogo: false,
  responsive: true,
  scrollZoom: true,
  toImageButtonOptions: {
    format: "png",
    filename: "phyto-trajectory-3d",
    scale: 2,
  },
};

export default function FormalTrajectoryViewer3D({
  trajectory,
}) {
  const plotElementRef = useRef(null);
  const plotlyRef = useRef(null);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retryKey, setRetryKey] = useState(0);
  const { traces, validCount } = useMemo(
    () => buildFormalTrajectoryPlot(trajectory || []),
    [trajectory],
  );

  useEffect(() => {
    const plotElement = plotElementRef.current;
    if (!validCount || !plotElement) return undefined;

    let active = true;
    let plotly = null;
    let resizeObserver = null;
    let resizeFrame = null;

    async function drawPlot() {
      setLoading(true);
      setLoadError("");
      try {
        // Plotly depends on browser APIs and is loaded only on the result page.
        const module = await import("plotly.js-gl3d-dist-min");
        if (!active) return;
        plotly = module.default || module;
        plotlyRef.current = plotly;
        await plotly.react(plotElement, traces, plotLayout(), PLOT_CONFIG);
        if (!active) {
          plotly.purge(plotElement);
          return;
        }
        resizeObserver = new ResizeObserver(() => {
          if (resizeFrame !== null) cancelAnimationFrame(resizeFrame);
          resizeFrame = requestAnimationFrame(() => {
            resizeFrame = null;
            if (active && plotElement.isConnected) {
              void Promise.resolve(plotly.Plots.resize(plotElement)).catch(() => {
                if (active) {
                  setLoadError("調整三維圖表尺寸失敗，請重新載入圖表。");
                }
              });
            }
          });
        });
        resizeObserver.observe(plotElement.parentElement);
      } catch {
        if (active) {
          setLoadError("無法顯示互動式三維軌跡，請重試或檢查瀏覽器的 WebGL 支援。");
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void drawPlot();
    return () => {
      active = false;
      resizeObserver?.disconnect();
      if (resizeFrame !== null) cancelAnimationFrame(resizeFrame);
      if (plotlyRef.current === plotly) plotlyRef.current = null;
      if (plotly) plotly.purge(plotElement);
    };
  }, [traces, validCount, retryKey]);

  const resetCamera = () => {
    const plotElement = plotElementRef.current;
    const plotly = plotlyRef.current;
    if (!plotElement || !plotly) return;
    void plotly.relayout(plotElement, {
      "scene.camera": defaultCamera(),
    }).catch(() => {
      setLoadError("重設三維視角失敗，請重新載入圖表。");
    });
  };

  return (
    <InnerPanel>
      <SubsectionHeader
        title="三維尖端軌跡"
        description="拖曳旋轉、滾輪縮放；X／Y／Z 為等比例世界座標（mm），缺失輪次不連線。"
      >
        <Button
          className="min-h-9 px-3 text-xs"
          disabled={!validCount || loading || Boolean(loadError)}
          onClick={resetCamera}
        >
          <FiRotateCcw
            className="size-3.5 shrink-0"
            aria-hidden="true"
          />
          重設視角
        </Button>
      </SubsectionHeader>

      {validCount ? (
        <div className="relative h-[min(65vh,640px)] min-h-80 min-w-0 overflow-hidden rounded-xl border border-white/15 bg-black/30">
          <div
            ref={plotElementRef}
            className="size-full"
            aria-label="可旋轉縮放的三維尖端軌跡科學圖"
          />
          {loading && !loadError ? (
            <p
              className="absolute inset-0 grid place-items-center bg-[#06100c]/75 text-sm font-semibold text-neutral-300"
              role="status"
            >
              載入三維圖表中…
            </p>
          ) : null}
          {loadError ? (
            <div className="absolute inset-0 grid place-items-center bg-[#06100c]/95 p-4">
              <RetryMessage
                message={loadError}
                onRetry={() => setRetryKey((value) => value + 1)}
                retryLabel="重新載入圖表"
              />
            </div>
          ) : null}
        </div>
      ) : (
        <p className="m-0 rounded-xl border border-dashed border-white/15 bg-black/15 p-5 text-center text-sm font-semibold text-neutral-400">
          本次分析沒有可顯示的有效三維尖端標記。
        </p>
      )}

      {validCount ? (
        <p className="m-0 text-xs font-semibold text-neutral-400">
          圖例可切換各模式；白色點為人工修正，空心圓為起點、實心圓為終點、菱形為世界原點。
        </p>
      ) : null}
    </InnerPanel>
  );
}
