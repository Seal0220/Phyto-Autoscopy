document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-camera-action]");
  if (!button) return;
  const action = button.dataset.cameraAction;
  const cameraId = button.dataset.cameraId;
  button.disabled = true;
  try {
    if (action === "capture") {
      await window.PhytoSocket.command("camera.capture", { camera_id: cameraId });
    }
    if (action === "capture-all") {
      await window.PhytoSocket.command("camera.capture_all");
    }
    if (action === "reconnect") {
      await window.PhytoSocket.command("camera.reconnect", { camera_id: cameraId });
    }
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
  }
});
