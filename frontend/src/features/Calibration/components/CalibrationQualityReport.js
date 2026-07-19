import StatusCard from "@/components/cards/StatusCard";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { StatusPill } from "@/components/panels/Panel";

import {
  formatCalibrationNumber,
  formatCalibrationPercent,
} from "../lib/calibrationUtils";

const CAMERA_LABELS = {
  top: "俯視角",
  side: "側視角",
  stereo: "雙鏡頭",
  "stereo:top": "雙鏡頭俯視角",
  "stereo:side": "雙鏡頭側視角",
};

function errorLabel(value) {
  const formatted = formatCalibrationNumber(value);
  return formatted === "—" ? formatted : `${formatted} px`;
}

function coverageRows(pointCoverage) {
  const rows = [];
  for (const key of ["top", "side"]) {
    if (pointCoverage?.[key]) {
      rows.push({
        key,
        label: CAMERA_LABELS[key],
        value: pointCoverage[key],
      });
    }
  }
  const stereo = pointCoverage?.stereo;
  if (stereo?.top || stereo?.side) {
    for (const key of ["top", "side"]) {
      if (stereo[key]) {
        rows.push({
          key: `stereo:${key}`,
          label: CAMERA_LABELS[`stereo:${key}`],
          value: stereo[key],
        });
      }
    }
  } else if (stereo) {
    rows.push({
      key: "stereo",
      label: CAMERA_LABELS.stereo,
      value: stereo,
    });
  }
  return rows;
}

function cornerRows(cornerDetections) {
  const rows = [];
  for (const cameraId of ["top", "side"]) {
    for (const item of cornerDetections?.[cameraId] || []) {
      rows.push({
        cameraId,
        id: item.image_id,
        found: Boolean(item.found),
        cornerCount: item.corner_count ?? item.corners?.length ?? 0,
        width: item.image_width,
        height: item.image_height,
      });
    }
  }
  for (const pair of cornerDetections?.stereo || []) {
    for (const cameraId of ["top", "side"]) {
      const item = pair?.[cameraId] || {};
      rows.push({
        cameraId: `stereo:${cameraId}`,
        id: `${pair.pair_id} · ${item.image_id || "—"}`,
        found: Boolean(item.found),
        cornerCount: item.corner_count ?? item.corners?.length ?? 0,
        width: item.image_width,
        height: item.image_height,
      });
    }
  }
  return rows;
}

function errorRows(reprojectionErrors) {
  const rows = [];
  for (const cameraId of ["top", "side", "stereo"]) {
    for (const item of reprojectionErrors?.[cameraId] || []) {
      rows.push({
        cameraId,
        ...item,
      });
    }
  }
  return rows;
}

export default function CalibrationQualityReport({ report }) {
  const counts = report?.image_count || {};
  const successes = report?.successful_corner_detections || {};
  const means = report?.mean_reprojection_errors || {};
  const coverages = coverageRows(report?.point_coverage);
  const corners = cornerRows(report?.corner_detections);
  const errors = errorRows(report?.reprojection_error_per_image);

  return (
    <div className="grid gap-5">
      <div className="grid gap-3 min-[520px]:grid-cols-3">
        <StatusCard
          title="俯視角平均誤差"
          content={errorLabel(means.top)}
          note={`${successes.top || 0} / ${counts.top || 0} 張角點成功`}
        />
        <StatusCard
          title="側視角平均誤差"
          content={errorLabel(means.side)}
          note={`${successes.side || 0} / ${counts.side || 0} 張角點成功`}
        />
        <StatusCard
          title="雙鏡頭平均誤差"
          content={errorLabel(means.stereo)}
          note={`${successes.stereo || 0} / ${counts.stereo || 0} 組可用`}
        />
      </div>

      <p className="m-0 text-xs font-semibold leading-5 text-neutral-300">
        重投影誤差與覆蓋率是描述性量測。論文未定義本裝置可直接採用的合格門檻，因此此頁不宣稱任何誤差值具有品質保證；應同時檢查逐圖誤差、角點分布及植物尖端預期活動區域。
      </p>

      <section className="grid gap-3">
        <SubsectionHeader
          title="校正點空間覆蓋"
          description="凸包、邊界框與 4 × 4 網格占用率用於描述角點在感測器上的分布，不套用虛構的通過門檻。"
        />
        {coverages.length ? (
          <div className="grid gap-3 min-[720px]:grid-cols-2">
            {coverages.map((coverage) => (
              <article
                className="grid gap-3 rounded-xl border border-white/10 bg-black/10 p-3"
                key={coverage.key}
              >
                <h4 className="m-0 text-sm font-black text-white">{coverage.label}</h4>
                <dl className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <dt className="font-black text-neutral-500">角點總數</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {formatCalibrationNumber(coverage.value.point_count, 0)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-black text-neutral-500">網格占用</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {coverage.value.grid
                        ? `${coverage.value.grid.occupied_cells} / ${coverage.value.grid.total_cells}（${formatCalibrationPercent(coverage.value.grid.coverage_ratio)}）`
                        : "—"
                      }
                    </dd>
                  </div>
                  <div>
                    <dt className="font-black text-neutral-500">水平跨度</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {formatCalibrationPercent(coverage.value.horizontal_span_ratio)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-black text-neutral-500">垂直跨度</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {formatCalibrationPercent(coverage.value.vertical_span_ratio)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-black text-neutral-500">邊界框面積</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {formatCalibrationPercent(coverage.value.bounding_box_area_ratio)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-black text-neutral-500">凸包面積</dt>
                    <dd className="mt-1 m-0 font-bold text-neutral-200">
                      {formatCalibrationPercent(coverage.value.convex_hull_area_ratio)}
                    </dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        ) : (
          <p className="m-0 rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-sm font-semibold text-neutral-400">
            完成單鏡頭與雙鏡頭校正後會顯示校正點覆蓋資料。
          </p>
        )}
      </section>

      <section className="grid gap-3">
        <SubsectionHeader
          title="逐圖角點偵測"
          description="每張來源影像均保留偵測狀態、角點數及解析度。"
        />
        {corners.length ? (
          <div className="max-h-96 overflow-auto rounded-xl border border-white/10">
            <table className="w-full min-w-[46rem] border-collapse text-left text-xs">
              <thead className="sticky top-0 z-10 bg-[#122019] text-neutral-300">
                <tr>
                  <th className="px-3 py-2 font-black">類型</th>
                  <th className="px-3 py-2 font-black">影像</th>
                  <th className="px-3 py-2 font-black">解析度</th>
                  <th className="px-3 py-2 font-black">角點數</th>
                  <th className="px-3 py-2 font-black">結果</th>
                </tr>
              </thead>
              <tbody>
                {corners.map((item) => (
                  <tr
                    className="border-t border-white/10 text-neutral-200"
                    key={`${item.cameraId}-${item.id}`}
                  >
                    <td className="px-3 py-2 font-bold">{CAMERA_LABELS[item.cameraId]}</td>
                    <td className="max-w-96 truncate px-3 py-2 font-semibold" title={item.id}>{item.id}</td>
                    <td className="px-3 py-2 font-semibold">{item.width} × {item.height}</td>
                    <td className="px-3 py-2 font-semibold">{item.cornerCount}</td>
                    <td className="px-3 py-2">
                      <StatusPill tone={item.found ? "success" : "offline"}>
                        {item.found ? "成功" : "失敗"}
                      </StatusPill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="m-0 rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-sm font-semibold text-neutral-400">
            尚無角點偵測紀錄。
          </p>
        )}
      </section>

      <section className="grid gap-3">
        <SubsectionHeader
          title="逐圖／逐配對重投影誤差"
          description="單鏡頭顯示 RMS 與最大誤差；雙鏡頭顯示兩側、合併與 Epipolar RMS 誤差。"
        />
        {errors.length ? (
          <div className="max-h-96 overflow-auto rounded-xl border border-white/10">
            <table className="w-full min-w-[72rem] border-collapse text-left text-xs">
              <thead className="sticky top-0 z-10 bg-[#122019] text-neutral-300">
                <tr>
                  <th className="px-3 py-2 font-black">類型</th>
                  <th className="px-3 py-2 font-black">影像／配對</th>
                  <th className="px-3 py-2 font-black">點數</th>
                  <th className="px-3 py-2 font-black">RMS</th>
                  <th className="px-3 py-2 font-black">最大</th>
                  <th className="px-3 py-2 font-black">俯視角 RMS</th>
                  <th className="px-3 py-2 font-black">側視角 RMS</th>
                  <th className="px-3 py-2 font-black">合併 RMS</th>
                  <th className="px-3 py-2 font-black">Epipolar RMS</th>
                </tr>
              </thead>
              <tbody>
                {errors.map((item) => (
                  <tr
                    className="border-t border-white/10 text-neutral-200"
                    key={`${item.cameraId}-${item.image_id || item.pair_id}`}
                  >
                    <td className="px-3 py-2 font-bold">{CAMERA_LABELS[item.cameraId]}</td>
                    <td className="max-w-96 truncate px-3 py-2 font-semibold" title={item.image_id || item.pair_id}>
                      {item.image_id || item.pair_id || "—"}
                    </td>
                    <td className="px-3 py-2 font-semibold">{formatCalibrationNumber(item.point_count, 0)}</td>
                    <td className="px-3 py-2 font-semibold">{errorLabel(item.rms_error_px)}</td>
                    <td className="px-3 py-2 font-semibold">{errorLabel(item.max_error_px)}</td>
                    <td className="px-3 py-2 font-semibold">{errorLabel(item.top_rms_error_px)}</td>
                    <td className="px-3 py-2 font-semibold">{errorLabel(item.side_rms_error_px)}</td>
                    <td className="px-3 py-2 font-semibold">{errorLabel(item.combined_rms_error_px)}</td>
                    <td className="px-3 py-2 font-semibold">{errorLabel(item.epipolar_rms_error_px)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="m-0 rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-sm font-semibold text-neutral-400">
            完成校正求解後會顯示逐圖與逐配對誤差。
          </p>
        )}
      </section>
    </div>
  );
}
