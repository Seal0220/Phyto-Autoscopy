export function analysisViewImageUrl(
  analysisId,
  viewId,
  coordinateSpace = "reprojection",
) {
  const query = new URLSearchParams({ coordinate_space: coordinateSpace });
  return `/api/analysis/${encodeURIComponent(analysisId)}/views/${encodeURIComponent(viewId)}/image?${query}`;
}

export function analysisArtifactUrl(
  analysisId,
  artifactPath,
) {
  const encodedPath = String(artifactPath || "")
    .split(/[\\/]+/)
    .map(encodeURIComponent)
    .join("/");
  return `/api/analysis/${encodeURIComponent(analysisId)}/artifacts/${encodedPath}`;
}
