import * as THREE from "three";
import * as GaussianSplats3D from "@mkkellogg/gaussian-splats-3d";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { gaussianPointIndex } from "./analysisModelReferenceUtils";
import { createModelMarkerLayer, createTipMarkerLayer } from "./analysisModelMarkers";

export function createModelViewer({
  element,
  reference,
  onPick,
  onMove,
  onRemove,
  onNotice,
  onProgress,
  tipPicking = false,
}) {
  const { radius } = reference;
  const scene = new THREE.Scene();
  const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x07100c, 1);
  element.appendChild(renderer.domElement);
  const camera = new THREE.PerspectiveCamera(40, 1, radius * .001, radius * 100);
  const tipMarker = createTipMarkerLayer({ element, camera });
  const markers = createModelMarkerLayer({
    element,
    camera,
    pickPoint: (x, y) => pickPoint(x, y),
    onSelect: onPick,
    onMove,
    onRemove,
    onNotice,
    tipPicking,
    onDragState: (active) => {
      dragging = active;
      controls.enabled = !disabled && !dragging && !disposed;
    },
  });
  const target = new THREE.Vector3().fromArray(reference.center);
  camera.up.fromArray(reference.initial_camera.up).normalize();
  const originalPosition = new THREE.Vector3().fromArray(reference.initial_camera.position);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(target);
  controls.enableDamping = false;
  // Zoom changes the field of view so the trained camera position stays fixed.
  controls.enableZoom = false;
  controls.rotateSpeed = .65;
  controls.minDistance = radius * .05;
  controls.maxDistance = radius * 50;
  renderer.domElement.style.touchAction = "pan-y";
  const resize = () => {
    const width = element.clientWidth, height = element.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    markers.update();
    tipMarker.update();
  };
  resize();
  const reset = () => {
    const distance = originalPosition.distanceTo(target);
    const angle = Math.atan(radius * 1.25 / (distance * Math.min(camera.aspect, 1)));
    camera.fov = THREE.MathUtils.clamp(THREE.MathUtils.radToDeg(angle) * 2, 5, 80);
    camera.updateProjectionMatrix();
    controls.target.copy(target);
    camera.position.copy(originalPosition);
    camera.up.fromArray(reference.initial_camera.up).normalize();
    camera.lookAt(target);
    controls.update();
    markers.update();
    tipMarker.update();
  };
  reset();
  const viewer = new GaussianSplats3D.Viewer({
    rootElement: element,
    renderer,
    camera,
    threeScene: scene,
    useBuiltInControls: false,
    selfDrivenMode: true,
    sharedMemoryForWorkers: false,
    gpuAcceleratedSort: true,
    integerBasedSort: true,
    sphericalHarmonicsDegree: 3,
    antialiased: reference.model_quality?.rasterize_mode === "antialiased",
    optimizeSplatData: false,
    inMemoryCompressionLevel: 0,
    renderMode: GaussianSplats3D.RenderMode.OnChange,
    sceneRevealMode: GaussianSplats3D.SceneRevealMode.Instant,
  });
  const observer = new ResizeObserver(() => { resize(); viewer.forceRenderNextFrame(); });
  observer.observe(element);
  const cameraChanged = () => {
    markers.update();
    tipMarker.update();
    viewer.forceRenderNextFrame();
  };
  controls.addEventListener("change", cameraChanged);
  const pointPosition = (pointId) => {
    const index = gaussianPointIndex(reference, pointId);
    if (index !== null && loaded) {
      const position = new THREE.Vector3();
      viewer.splatMesh.getSplatCenter(index, position);
      return position;
    }
    const sparse = reference.points.find((point) => point.id === pointId);
    return sparse ? new THREE.Vector3().fromArray(sparse.xyz) : null;
  };
  const raycaster = viewer.raycaster;
  raycaster.raycastAgainstTrueSplatEllipsoid = true;
  const download = new AbortController();
  let finishTree;
  const treeReady = new Promise((resolve) => { finishTree = resolve; });
  viewer.splatMesh.onSplatTreeReady(() => finishTree());
  const center = new THREE.Vector3();
  const color = new THREE.Vector4();
  let disposed = false;
  let loaded = false;
  let disabled = false;
  let dragging = false;
  let gesture = null;
  const down = (event) => {
    if (event.button !== 0 || !event.isPrimary) { gesture = null; return; }
    gesture = { x: event.clientX, y: event.clientY, moved: false };
    element.focus({ preventScroll: true });
  };
  const move = (event) => {
    if (gesture && Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) > 5) gesture.moved = true;
  };
  const pickPoint = (clientX, clientY) => {
    if (disposed || disabled || !loaded || !viewer.splatMesh.getSplatTree()) return null;
    const bounds = renderer.domElement.getBoundingClientRect();
    if (!bounds.width || !bounds.height || clientX < bounds.left || clientY < bounds.top
      || clientX >= bounds.right || clientY >= bounds.bottom) return null;
    raycaster.setFromCameraAndScreenPosition(camera,
      new THREE.Vector2(clientX - bounds.left, clientY - bounds.top),
      new THREE.Vector2(bounds.width, bounds.height));
    const hits = [];
    raycaster.intersectSplatMesh(viewer.splatMesh, hits);
    // Ignore faint floaters and distant ellipsoid centres; the marker shows the exact anchor.
    for (const hit of hits) {
      viewer.splatMesh.getSplatColor(hit.splatIndex, color);
      if (color.w < 64 || Math.max(color.x, color.y, color.z) < 30) continue;
      viewer.splatMesh.getSplatCenter(hit.splatIndex, center);
      const screen = center.clone().project(camera);
      const pixelX = (screen.x + 1) * bounds.width / 2;
      const pixelY = (1 - screen.y) * bounds.height / 2;
      if (Math.abs(screen.z) > 1 || Math.hypot(pixelX - (clientX - bounds.left), pixelY - (clientY - bounds.top)) > 14) continue;
      return { pointId: reference.gaussian_point_offset + hit.splatIndex, anchor: center.clone() };
    }
    return null;
  };
  const up = (event) => {
    const click = gesture && !gesture.moved && event.button === 0;
    gesture = null;
    if (!click || disabled || !loaded || !onPick) return;
    if (!viewer.splatMesh.getSplatTree()) { onNotice("選點準備中，請稍候。"); return; }
    const hit = pickPoint(event.clientX, event.clientY);
    if (hit) {
      onNotice("");
      onPick(hit.pointId);
      return;
    }
    onNotice("這裡沒有清楚的模型點，請放大後再選。");
  };
  const cancel = () => { gesture = null; };
  renderer.domElement.addEventListener("pointerdown", down);
  renderer.domElement.addEventListener("pointermove", move);
  renderer.domElement.addEventListener("pointerup", up);
  renderer.domElement.addEventListener("pointercancel", cancel);
  const zoom = (factor) => {
    camera.fov = THREE.MathUtils.clamp(camera.fov * factor, 3, 100);
    camera.updateProjectionMatrix();
    controls.update();
    markers.update();
    tipMarker.update();
    viewer.forceRenderNextFrame();
  };
  const wheel = (event) => {
    if (disposed || !loaded || disabled || event.deltaY === 0) return;
    event.preventDefault();
    event.stopPropagation();
    if (dragging) return;
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? element.clientHeight : 1;
    const delta = THREE.MathUtils.clamp(event.deltaY * unit, -250, 250);
    zoom(Math.exp(delta * .002));
  };
  element.addEventListener("wheel", wheel, { passive: false });
  const keyboard = (event) => {
    if (event.target !== element || disposed || !loaded || disabled) return;
    const directions = { ArrowLeft: [1, 0], ArrowRight: [-1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] };
    if (directions[event.key]) {
      const [x, y] = directions[event.key];
      if (event.shiftKey) controls.pan(x * 24, y * 24);
      else { controls.rotateLeft(x * .12); controls.rotateUp(y * .12); }
      controls.update();
    } else if (["+", "="].includes(event.key)) zoom(.8);
    else if (event.key === "-") zoom(1.25);
    else if (event.key === "0") reset();
    else return;
    event.preventDefault();
    viewer.forceRenderNextFrame();
  };
  element.addEventListener("keydown", keyboard);
  viewer.start();
  return {
    async load(url) {
      const response = await fetch(url, { signal: download.signal, cache: "no-store" });
      if (!response.ok) throw new Error("模型下載失敗。");
      const size = Number(response.headers.get("content-length"));
      const reader = response.body.getReader();
      const chunks = [];
      let length = 0;
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          chunks.push(value);
          length += value.length;
          if (!disposed && size > 0) onProgress(Math.min(99, Math.round(length / size * 100)));
        }
      } finally { reader.releaseLock(); }
      if (disposed) return;
      const bytes = new Uint8Array(length);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      const hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
      if (hash !== reference.gaussian_sha256) throw new Error("模型已變更，請重新讀取。");
      if (disposed) return;
      onProgress(100);
      // The normal loader buckets/reorders even uncompressed splats. Parse directly to retain PLY IDs.
      const buffer = GaussianSplats3D.PlyParser.parseToUncompressedSplatBuffer(bytes.buffer, 3);
      await viewer.addSplatBuffers([buffer], [{ splatAlphaRemovalThreshold: 0 }], true, false, false);
      await treeReady;
      if (disposed) return;
      // v0.4.7's GPU sorter still requires the worker's uploaded vertex count to be initialized.
      const data = viewer.splatMesh.getDataForDistancesComputation(0, reference.gaussian_count - 1);
      viewer.sortWorker.postMessage({
        centers: data.centers.buffer,
        sceneIndexes: data.sceneIndexes.buffer,
        range: { from: 0, to: reference.gaussian_count - 1, count: reference.gaussian_count },
      });
      await viewer.runSplatSort(true, true);
      if (viewer.sortPromise) await viewer.sortPromise;
      // Every anchor uses the original world-space PLY vertex, never a guessed 2D depth.
      if (viewer.splatMesh.getSplatCount() !== reference.gaussian_count) {
        throw new Error("Gaussian 頂點順序不一致。");
      }
      loaded = true;
      viewer.forceRenderNextFrame();
    },
    setSelection(pointId, pointIds = [pointId]) {
      const anchors = [];
      if (loaded) pointIds.forEach((id, number) => {
        const anchor = pointPosition(id);
        if (!anchor) return;
        anchors.push({ anchor, pointId: id, number: number + 1, selected: id === pointId });
      });
      markers.setMarkers(anchors);
      viewer.forceRenderNextFrame();
    },
    setTip(landmark) { tipMarker.setTip(landmark); },
    setDisabled(locked) {
      disabled = locked;
      markers.setDisabled(locked);
      controls.enabled = !locked && !dragging;
    },
    reset() { reset(); viewer.forceRenderNextFrame(); },
    async dispose() {
      if (disposed) return;
      disposed = true;
      download.abort();
      finishTree();
      observer.disconnect();
      renderer.domElement.removeEventListener("pointerdown", down);
      renderer.domElement.removeEventListener("pointermove", move);
      renderer.domElement.removeEventListener("pointerup", up);
      renderer.domElement.removeEventListener("pointercancel", cancel);
      element.removeEventListener("wheel", wheel);
      element.removeEventListener("keydown", keyboard);
      controls.removeEventListener("change", cameraChanged);
      controls.dispose();
      markers.dispose();
      tipMarker.dispose();
      viewer.stop();
      try { await viewer.dispose(); }
      finally {
        renderer.dispose();
        renderer.forceContextLoss();
        renderer.domElement.remove();
      }
    },
  };
}
