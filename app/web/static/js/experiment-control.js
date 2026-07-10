function formPayload(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  for (const key of Object.keys(data)) {
    if (data[key] !== "") data[key] = Number(data[key]);
  }
  return data;
}

document.addEventListener("submit", async (event) => {
  if (event.target.id === "experiment-form") {
    event.preventDefault();
    await window.PhytoSocket.command("experiment.start", formPayload(event.target));
  }
  if (event.target.id === "rotation-form") {
    event.preventDefault();
    await window.PhytoSocket.command("capture.rotation_cycle", formPayload(event.target));
  }
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-experiment-action]");
  if (!button) return;
  await window.PhytoSocket.command(`experiment.${button.dataset.experimentAction}`);
});
