const PhytoUI = {
  chipBase:
    "inline-flex min-h-[32px] min-w-0 items-center justify-center gap-2 whitespace-nowrap rounded-full border bg-[#06100c]/55 px-3 py-1.5 text-center text-[11px] font-black leading-none tracking-[0.06em] shadow-[0_8px_24px_rgba(0,0,0,0.18),inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-2xl before:size-1.5 before:shrink-0 before:rounded-full before:bg-current before:opacity-90",
  chipAccent:
    "inline-flex min-h-[32px] min-w-0 items-center justify-center gap-2 whitespace-nowrap rounded-full border border-cyan-200/[0.78] bg-cyan-600/[0.18] px-3 py-1.5 text-center text-[11px] font-black leading-none tracking-[0.06em] text-cyan-300 shadow-[0_0_18px_rgba(6,182,212,0.20),inset_0_1px_0_rgba(236,254,255,0.18)] backdrop-blur-2xl before:size-1.5 before:shrink-0 before:rounded-full before:bg-current before:opacity-90",
  chipInfo:
    "inline-flex min-h-[32px] min-w-0 items-center justify-center gap-2 whitespace-nowrap rounded-full border border-cyan-200/[0.78] bg-cyan-600/[0.18] px-3 py-1.5 text-center text-[11px] font-black leading-none tracking-[0.06em] text-cyan-300 shadow-[0_0_18px_rgba(6,182,212,0.20),inset_0_1px_0_rgba(236,254,255,0.18)] backdrop-blur-2xl before:size-1.5 before:shrink-0 before:rounded-full before:bg-current before:opacity-90",
  chipOnline:
    "inline-flex min-h-[32px] min-w-0 items-center justify-center gap-2 whitespace-nowrap rounded-full border border-emerald-200/[0.78] bg-emerald-600/[0.18] px-3 py-1.5 text-center text-[11px] font-black leading-none tracking-[0.06em] text-emerald-300 shadow-[0_0_18px_rgba(16,185,129,0.20),inset_0_1px_0_rgba(236,253,245,0.18)] backdrop-blur-2xl before:size-1.5 before:shrink-0 before:rounded-full before:bg-current before:opacity-90",
  chipWarning:
    "inline-flex min-h-[32px] min-w-0 items-center justify-center gap-2 whitespace-nowrap rounded-full border border-amber-200/[0.82] bg-amber-600/[0.18] px-3 py-1.5 text-center text-[11px] font-black leading-none tracking-[0.06em] text-amber-300 shadow-[0_0_18px_rgba(245,158,11,0.20),inset_0_1px_0_rgba(255,251,235,0.18)] backdrop-blur-2xl before:size-1.5 before:shrink-0 before:rounded-full before:bg-current before:opacity-90",
  chipOffline:
    "inline-flex min-h-[32px] min-w-0 items-center justify-center gap-2 whitespace-nowrap rounded-full border border-rose-200/[0.82] bg-rose-600/[0.18] px-3 py-1.5 text-center text-[11px] font-black leading-none tracking-[0.06em] text-rose-300 shadow-[0_0_18px_rgba(244,63,94,0.20),inset_0_1px_0_rgba(255,241,242,0.18)] backdrop-blur-2xl before:size-1.5 before:shrink-0 before:rounded-full before:bg-current before:opacity-90",
  cameraChipOnline:
    "inline-flex min-h-[27px] min-w-[62px] items-center justify-center gap-1.5 whitespace-nowrap rounded-full border border-emerald-200/[0.78] bg-emerald-600/[0.18] px-2 py-1 text-center text-[10px] font-black leading-none tracking-[0.04em] text-emerald-300 shadow-[inset_0_1px_0_rgba(236,253,245,0.18)] before:size-1 before:shrink-0 before:rounded-full before:bg-current",
  cameraChipOffline:
    "inline-flex min-h-[27px] min-w-[62px] items-center justify-center gap-1.5 whitespace-nowrap rounded-full border border-rose-200/[0.82] bg-rose-600/[0.18] px-2 py-1 text-center text-[10px] font-black leading-none tracking-[0.04em] text-rose-300 shadow-[inset_0_1px_0_rgba(255,241,242,0.18)] before:size-1 before:shrink-0 before:rounded-full before:bg-current",
  row:
    "flex items-center justify-between gap-3 border-b border-white/[0.08] py-2.5 first:pt-0 last:border-b-0 last:pb-0",
  rowLabel: "text-sm text-white",
  rowValue: "m-0 text-right text-sm font-black text-white",
  buttonRow: "flex flex-wrap items-center gap-2",
  button:
    "inline-flex min-h-[42px] min-w-0 items-center justify-center gap-2 rounded-xl border border-white/[0.12] bg-white/[0.07] px-4 py-2 text-center text-sm font-black leading-tight text-white/[0.82] no-underline shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-xl transition duration-200 hover:-translate-y-0.5 hover:border-white/[0.22] hover:bg-white/[0.13] hover:text-white hover:shadow-[0_12px_30px_rgba(0,0,0,0.22)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300/[0.45] disabled:pointer-events-none disabled:opacity-40 cursor-pointer",
  buttonStrong:
    "inline-flex min-h-[42px] min-w-0 items-center justify-center gap-2 rounded-xl border border-emerald-200/[0.32] bg-emerald-300/[0.92] px-4 py-2 text-center text-sm font-black leading-tight text-emerald-950 no-underline shadow-[0_10px_30px_rgba(16,185,129,0.16),inset_0_1px_0_rgba(255,255,255,0.28)] transition duration-200 hover:-translate-y-0.5 hover:border-emerald-100/[0.50] hover:bg-emerald-200 hover:shadow-[0_14px_36px_rgba(16,185,129,0.24)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200/[0.70] disabled:pointer-events-none disabled:opacity-40 cursor-pointer",
  buttonDanger:
    "inline-flex min-h-[42px] min-w-0 items-center justify-center gap-2 rounded-xl border border-red-300/[0.90] bg-red-600/[0.94] px-4 py-2 text-center text-sm font-black leading-tight text-white no-underline shadow-[0_0_22px_rgba(239,68,68,0.34),0_10px_28px_rgba(127,29,29,0.28)] transition duration-200 hover:-translate-y-0.5 hover:border-red-200 hover:bg-red-500 hover:shadow-[0_0_28px_rgba(248,113,113,0.48),0_14px_34px_rgba(127,29,29,0.34)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-300/[0.65] disabled:pointer-events-none disabled:opacity-40 cursor-pointer",
  field: "settings-field",
  fieldLabel: "settings-field__label",
  input: "settings-control",
  checkboxField: "settings-check",
  checkboxLabel: "settings-check__label",
  checkbox: "settings-check__input",
  settingsGroup: "settings-group",
  settingsGroupTitle: "settings-group__title",
  settingsFields: "settings-fields",
  settingsMessage: "settings-message",
  errorRow:
    "rounded-xl border border-rose-200/[0.15] bg-rose-300/[0.08] px-3 py-2 text-sm leading-6 text-rose-100/80 backdrop-blur-xl",
  tableCell: "border-b border-white/[0.08] px-4 py-3 align-top text-sm text-white",
  tableCellStrong:
    "border-b border-white/[0.08] px-4 py-3 align-top text-sm font-black text-white",
};

window.PhytoUI = PhytoUI;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || response.statusText);
  }
  return response.json();
}

function formatBytes(value) {
  if (!Number.isFinite(value)) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function setChipState(id, text, connected) {
  const element = document.getElementById(id);
  if (!element) return;
  const isCamera = id.startsWith("cam-") || id.startsWith("camera-state-");
  const nextClassName = connected
    ? isCamera ? PhytoUI.cameraChipOnline : PhytoUI.chipOnline
    : isCamera ? PhytoUI.cameraChipOffline : PhytoUI.chipOffline;
  const nextTone = connected ? "success" : "offline";
  if (
    element.textContent === text
    && element.className === nextClassName
    && element.dataset.statusTone === nextTone
  ) return;
  element.textContent = text;
  element.className = nextClassName;
  element.dataset.statusTone = nextTone;
}

function booleanText(value) {
  return value ? "是" : "否";
}

function statusText(value) {
  const labels = {
    idle: "待命",
    running: "執行中",
    paused: "已暫停",
    stopped: "已停止",
    completed: "已完成",
    failed: "失敗",
  };
  return labels[value] || value || "-";
}

function setStatusChip(id, value) {
  const element = document.getElementById(id);
  if (!element) return;
  const nextClassName = value === "running"
    ? PhytoUI.chipOnline
    : value === "paused"
      ? PhytoUI.chipWarning
      : value === "failed"
        ? PhytoUI.chipOffline
        : PhytoUI.chipAccent;
  const nextTone = value === "running"
    ? "success"
    : value === "paused"
      ? "warning"
      : value === "failed"
        ? "offline"
        : "accent";
  const text = statusText(value);
  if (
    element.textContent === text
    && element.className === nextClassName
    && element.dataset.statusTone === nextTone
  ) return;
  element.textContent = text;
  element.className = nextClassName;
  element.dataset.statusTone = nextTone;
}

function renderSystem(status) {
  if (!status) return;
  const mockMode = document.getElementById("mock-mode");
  if (mockMode) {
    mockMode.textContent = status.mock_mode ? "模擬模式" : "硬體模式";
    mockMode.className = status.mock_mode ? PhytoUI.chipWarning : PhytoUI.chipInfo;
    mockMode.dataset.statusTone = status.mock_mode ? "warning" : "accent";
  }
  setStatusChip("experiment-status", status.experiment_status);
  setText("disk-free", formatBytes(status.disk.free_bytes));
  const errors = document.getElementById("recent-errors");
  if (errors) {
    errors.innerHTML = "";
    const items = status.recent_errors.length ? status.recent_errors : ["尚無近期錯誤"];
    for (const item of items) {
      const li = document.createElement("li");
      li.className = PhytoUI.errorRow;
      li.textContent = item;
      errors.appendChild(li);
    }
  }
}

function renderCameras(cameras) {
  if (!Array.isArray(cameras)) return;
  for (const camera of cameras) {
    const text = camera.connected ? "已連線" : "離線";
    setChipState(`cam-${camera.camera_id}`, text, camera.connected);
    setChipState(`camera-state-${camera.camera_id}`, text, camera.connected);
  }
}

function statusRow(label, value) {
  return `
    <div class="${PhytoUI.row}">
      <dt class="${PhytoUI.rowLabel}">${label}</dt>
      <dd class="${PhytoUI.rowValue}">${value}</dd>
    </div>
  `;
}

function renderMotor(motor) {
  if (!motor) return;
  setChipState("motor-connected", motor.connected ? "已連線" : "離線", motor.connected);

  const detail = document.getElementById("motor-detail");
  if (detail) {
    detail.innerHTML = [
      statusRow("使用中", booleanText(motor.engaged)),
      statusRow("命令角度", `${motor.command_position_deg.toFixed(1)} 度`),
      statusRow("速度限制", `${motor.velocity_limit_deg_s} 度/秒`),
      statusRow("加速度限制", `${motor.acceleration_deg_s2} 度/秒²`),
      statusRow("電流限制", `${motor.current_limit_amp} 安培`),
    ].join("");
  }
}

function renderExperiment(experiment) {
  if (!experiment) return;
  setStatusChip("experiment-page-status", experiment.status);
}

window.PhytoFormat = {
  statusText,
};

document.addEventListener("phyto:snapshot", (event) => {
  const snapshot = event.detail || {};
  renderSystem(snapshot.system);
  renderCameras(snapshot.cameras);
  renderMotor(snapshot.motor);
  renderExperiment(snapshot.experiment);
});
