import * as THREE from "three";
import { Viewer, RenderMode, SceneRevealMode } from "@mkkellogg/gaussian-splats-3d";
import { trajectoryOverlayCamera } from "./trajectoryModelOverlayUtils";

export function createTrajectoryModelOverlay({
  element,
  plotElement,
  onError,
  antialiased = false,
}) {
  const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.domElement.setAttribute("aria-hidden", "true");
  renderer.domElement.dataset.trajectoryModels = "true";
  renderer.domElement.style.position = "absolute";
  renderer.domElement.style.pointerEvents = "none";
  element.appendChild(renderer.domElement);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
  camera.matrixAutoUpdate = false;
  camera.matrixWorldAutoUpdate = false;
  let viewer;
  try {
    viewer = new Viewer({
      rootElement: element,
      renderer,
      camera,
      useBuiltInControls: false,
      selfDrivenMode: false,
      sharedMemoryForWorkers: false,
      gpuAcceleratedSort: false,
      integerBasedSort: false,
      dynamicScene: true,
      enableOptionalEffects: true,
      antialiased,
      sphericalHarmonicsDegree: 2,
      optimizeSplatData: false,
      inMemoryCompressionLevel: 0,
      renderMode: RenderMode.OnChange,
      sceneRevealMode: SceneRevealMode.Instant,
    });
  } catch {
    renderer.domElement.remove();
    renderer.dispose();
    renderer.forceContextLoss();
    throw new Error("無法建立模型疊加畫面，請確認瀏覽器支援 WebGL 後重試。");
  }
  // Plotly owns all input, including keys. The auxiliary renderer must never
  // steal gestures or change its camera independently.
  viewer.removeEventHandlers();
  let disposed = false, loaded = false, visible = false;
  let frame = null, opacity = 0.35, previous = "", size = "", finishTree, sortPending = false;

  const sync = () => {
    const snapshot = trajectoryOverlayCamera(plotElement);
    if (!snapshot) return false;
    const bounds = snapshot.canvas.getBoundingClientRect(), parent = element.getBoundingClientRect();
    const width = bounds.width, height = bounds.height;
    if (!width || !height) return false;
    const signature = JSON.stringify([snapshot.view, snapshot.projection, snapshot.world, width, height, opacity]);
    renderer.domElement.style.left = `${bounds.left - parent.left}px`;
    renderer.domElement.style.top = `${bounds.top - parent.top}px`;
    const nextSize = `${width}:${height}`;
    if (size !== nextSize) {
      renderer.setSize(width, height, true);
      size = nextSize;
    }
    camera.projectionMatrix.fromArray(snapshot.projection);
    camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
    camera.matrixWorldInverse.fromArray(snapshot.view);
    camera.matrixWorld.copy(camera.matrixWorldInverse).invert();
    camera.matrix.copy(camera.matrixWorld);
    camera.position.setFromMatrixPosition(camera.matrixWorld);
    camera.quaternion.setFromRotationMatrix(camera.matrixWorld);
    camera.isOrthographicCamera = snapshot.orthographic;
    camera.isPerspectiveCamera = !snapshot.orthographic;
    if (loaded) {
      const scene = viewer.splatMesh.getScene(0);
      scene.matrixAutoUpdate = false;
      scene.matrixWorldAutoUpdate = false;
      scene.matrixWorld.fromArray(snapshot.world);
      scene.opacity = 1;
    }
    const changed = previous !== signature;
    previous = signature;
    return changed;
  };
  sync();

  const tick = () => {
    if (disposed) return;
    frame = requestAnimationFrame(tick);
    if (!loaded || !visible || document.hidden) return;
    try {
      const changed = sync();
      viewer.updateSplatMesh();
      sortPending ||= changed;
      if (sortPending && !viewer.sortRunning) {
        sortPending = false;
        void viewer.runSplatSort(true, true).catch(() => {
          if (!disposed) onError("模型深度排序失敗，請重新載入模型。");
        });
      }
      if (changed || viewer.renderNextFrame || viewer.shouldRender()) {
        // The installed viewer uses the instance count as the quad's draw
        // range. Draw the full quad even when only a few Gaussians are visible.
        const geometry = viewer.splatMesh.geometry;
        geometry.setDrawRange(0, geometry.index.count);
        renderer.clear();
        viewer.render();
        viewer.renderNextFrame = false;
      }
    } catch {
      visible = false;
      renderer.domElement.style.visibility = "hidden";
      onError("模型疊加繪圖失敗，請重新載入模型。");
    }
  };
  frame = requestAnimationFrame(tick);

  return {
    async show(buffer) {
      if (disposed) return;
      this.hide();
      loaded = false;
      const treeReady = new Promise((resolve) => { finishTree = resolve; });
      viewer.splatMesh.onSplatTreeReady(() => finishTree());
      await viewer.addSplatBuffers([buffer], [{ splatAlphaRemovalThreshold: 0 }], true, false, false, true);
      await treeReady;
      if (disposed) return;
      loaded = true;
      sync();
      viewer.updateSplatMesh();
      await viewer.runSplatSort(true, true);
      if (viewer.sortPromise) await viewer.sortPromise;
      if (disposed) return;
      renderer.domElement.dataset.gaussianCount = String(buffer.getSplatCount());
      renderer.domElement.style.visibility = "visible";
      visible = true;
      viewer.forceRenderNextFrame();
    },
    hide() {
      visible = false;
      renderer.domElement.style.visibility = "hidden";
    },
    setOpacity(value) {
      opacity = value;
      // Apply display transparency after compositing. Preserve trained
      // Gaussian opacity, and keep dense models from covering measurements.
      renderer.domElement.style.opacity = String(value);
      viewer.forceRenderNextFrame();
    },
    async dispose() {
      if (disposed) return;
      disposed = true;
      cancelAnimationFrame(frame);
      finishTree?.();
      renderer.domElement.remove();
      try { await viewer.dispose(); }
      finally {
        renderer.dispose();
        renderer.forceContextLoss();
      }
    },
  };
}
