document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-motor-action]");
  if (!button) return;
  const action = button.dataset.motorAction.replaceAll("-", "_");
  button.disabled = true;
  try {
    await window.PhytoSocket.command(`motor.${action}`);
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
  }
});

document.addEventListener("submit", async (event) => {
  if (event.target.id !== "move-form") return;
  event.preventDefault();
  const angle = Number(new FormData(event.target).get("angle"));
  try {
    await window.PhytoSocket.command("motor.move", { angle_deg: angle });
  } catch (error) {
    alert(error.message);
  }
});
