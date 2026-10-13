export function tipCorrectionPayload(
  roundKey,
  views,
  points,
  modelSelection,
  { initializing = false, requireModel = false } = {},
) {
  let modelFields = {};
  if (modelSelection) {
    if (!Number.isInteger(modelSelection.pointId) || modelSelection.pointId < 0
      || !/^[a-f0-9]{64}$/.test(modelSelection.signature || "")) {
      throw new Error("模型尖端選點無效，請重新讀取模型再點選。");
    }
    modelFields = { model_point_id: modelSelection.pointId, model_signature: modelSelection.signature };
  }
  const selected = views.filter((view) => ["top", "side"].includes(view.camera_id) && points[view.view_id]);
  if (!selected.length && modelSelection && !initializing) {
    return { round_key: roundKey, ...modelFields, reason: "每輪模型人工尖端標記", invalid: false };
  }
  if (new Set(selected.map((view) => view.camera_id)).size < 2) {
    throw new Error("請在同一組擷取的俯視與側視兩個鏡頭上標記同一尖端，或在模型點選尖端。");
  }
  if (new Set(selected.map((view) => view.snapshot_id)).size > 1) {
    throw new Error("請使用同一組擷取的影像標記尖端。");
  }
  const observations = selected.map((view) => ({ view_id: view.view_id, ...points[view.view_id] }));
  if (observations.some((point) => !Number.isFinite(point.x_px) || !Number.isFinite(point.y_px))) {
    throw new Error("尖端標記座標無效，請重新點選。");
  }
  if (initializing && requireModel && !modelSelection) {
    throw new Error("請一起標記第一輪模型的尖端，再確認追蹤起點。");
  }
  return { round_key: roundKey, ...modelFields, observations, reason: "每輪影像人工尖端標記", invalid: false };
}
