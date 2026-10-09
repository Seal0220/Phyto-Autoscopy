export default function AnalysisRunImageFeatureMarkers({
  features = [],
  viewId,
  width,
  height,
  activeFeature,
  onActiveFeature,
}) {
  if (!width || !height) return null;
  return features.flatMap((feature) => {
    const point = feature.observations.find((item) => item.view_id === viewId);
    if (!point) return [];
    const active = activeFeature === feature.feature_id;
    return [(
      <button
        key={feature.feature_id}
        type="button"
        aria-label={`葉片特徵 ${feature.feature_id}，在 ${feature.observations.length} 個視角有對應點`}
        title={`特徵 ${feature.feature_id} · 配對誤差 ${feature.error_px.toFixed(2)} px`}
        className={`absolute z-10 size-2.5 -translate-x-1/2 -translate-y-1/2 cursor-pointer rounded-full border transition-colors focus-visible:outline-2 focus-visible:outline-white
          ${active ? "border-white bg-cyan-300 shadow-[0_0_0_5px_rgba(103,232,249,0.5)]" : "border-cyan-200 bg-cyan-500/70 shadow-[0_0_0_1px_rgba(0,0,0,0.8)]"}`}
        style={{ left: `${point.x_px / width * 100}%`, top: `${point.y_px / height * 100}%` }}
        onPointerEnter={() => onActiveFeature?.(feature.feature_id)}
        onPointerLeave={() => onActiveFeature?.(null)}
        onFocus={() => onActiveFeature?.(feature.feature_id)}
        onBlur={() => onActiveFeature?.(null)}
      />
    )];
  });
}
