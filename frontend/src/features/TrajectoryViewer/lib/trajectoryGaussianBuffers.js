import * as THREE from "three";
import { PlyParser, SplatBuffer } from "@mkkellogg/gaussian-splats-3d";
import { analysisArtifactUrl } from "@/lib/analysisImageUtils";
import { withRequestTimeout } from "@/lib/httpUtils";
import { trajectoryModelWorldMatrix } from "./trajectoryModelOverlayUtils";
import { TRAJECTORY_MODEL_LIMITS } from "../trajectoryViewerConfig";

export async function loadTrajectoryGaussian({
  analysisId,
  reference,
  transform,
  signal,
}) {
  const bytes = await withRequestTimeout(async (requestSignal) => {
    const response = await fetch(analysisArtifactUrl(analysisId, reference.gaussian_path), { signal: requestSignal, cache: "no-store" });
    if (!response.ok) throw new Error("模型下載失敗，請重試。");
    return response.arrayBuffer();
  }, { signal, timeoutMs: TRAJECTORY_MODEL_LIMITS.downloadTimeoutMs });
  signal.throwIfAborted();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  if (hash !== reference.gaussian_sha256) throw new Error("模型內容已更新，請重新載入模型。");
  signal.throwIfAborted();
  const source = PlyParser.parseToUncompressedSplatBuffer(bytes, 2);
  if (source.getSplatCount() !== reference.gaussian_count) throw new Error("模型內容不完整，請重新載入模型。");
  return gaussianInWorldSpace(source, transform, signal);
}

export async function gaussianInWorldSpace(
  source,
  transform,
  signal,
) {
  const count = source.getSplatCount();
  const degree = Math.min(2, source.getMinSphericalHarmonicsDegree());
  const shCount = degree === 2 ? 24 : degree === 1 ? 9 : 0;
  const matrix = new THREE.Matrix4().fromArray(trajectoryModelWorldMatrix(transform));
  const centers = new Float32Array(count * 3), scales = new Float32Array(count * 3);
  const rotations = new Float32Array(count * 4), colors = new Uint8Array(count * 4);
  const harmonics = new Float32Array(count * shCount);
  source.fillSplatCenterArray(centers, matrix);
  source.fillSplatScaleRotationArray(scales, rotations, matrix, undefined, undefined, undefined, 0);
  source.fillSplatColorArray(colors, 0);
  if (degree) source.fillSphericalHarmonicsArray(harmonics, degree, matrix, undefined, undefined, undefined, 0);
  const { splatBuffer, splatBufferDataOffsetBytes } = SplatBuffer.preallocateUncompressed(count, 2);
  const stride = SplatBuffer.CompressionLevels[0].SphericalHarmonicsDegrees[2].BytesPerSplat;
  // A display-only copy in world millimetres preserves Gaussian covariance,
  // opacity and rotated SH colour. Combining copies removes the 32-scene limit.
  const floats = new Float32Array(splatBuffer.bufferData);
  const bytes = new Uint8Array(splatBuffer.bufferData);
  for (let index = 0; index < count; index += 1) {
    const baseBytes = splatBufferDataOffsetBytes + index * stride;
    const base = baseBytes / 4;
    floats.set(centers.subarray(index * 3, index * 3 + 3), base);
    floats.set(scales.subarray(index * 3, index * 3 + 3), base + 3);
    floats[base + 6] = rotations[index * 4 + 3];
    floats.set(rotations.subarray(index * 4, index * 4 + 3), base + 7);
    bytes.set(colors.subarray(index * 4, index * 4 + 4), baseBytes + 40);
    if (shCount) floats.set(harmonics.subarray(index * shCount, index * shCount + shCount), base + 11);
    if (index && index % 16384 === 0) {
      await new Promise((resolve) => setTimeout(resolve, 0));
      signal.throwIfAborted();
    }
  }
  signal.throwIfAborted();
  return splatBuffer;
}

export function mergeTrajectoryGaussians(buffers) {
  if (buffers.length === 1) return buffers[0];
  const count = buffers.reduce((sum, buffer) => sum + buffer.getSplatCount(), 0);
  const { splatBuffer, splatBufferDataOffsetBytes } = SplatBuffer.preallocateUncompressed(count, 2);
  const destination = new Uint8Array(splatBuffer.bufferData);
  let offset = splatBufferDataOffsetBytes;
  for (const buffer of buffers) {
    const section = buffer.sections[0];
    const bytes = new Uint8Array(buffer.bufferData, section.dataBase, section.bytesPerSplat * buffer.getSplatCount());
    destination.set(bytes, offset);
    offset += bytes.length;
  }
  return splatBuffer;
}
