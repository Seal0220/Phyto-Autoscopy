const SETTINGS_GROUPS = [
  ["default", "預設"],
  ["cameras", "相機"],
  ["motor", "馬達"],
  ["experiment", "實驗"],
  ["logging", "紀錄"],
];
const SETTINGS_GROUP_IDS = new Set(SETTINGS_GROUPS.map(([group]) => group));
const SETTINGS_TAB_STORAGE_KEY = "phyto-autoscopy.settings.active-tab";
const settingsState = {
  activeTab: "default",
};

function settingLabel(key) {
  const labels = {
    acceleration_deg_s2: "加速度（度/秒²）",
    calibration_dir: "校正資料夾",
    camera_scan_max_index: "相機掃描最大索引",
    capture_fixed_side: "擷取固定側視角",
    capture_fps: "擷取 FPS",
    capture_interval_seconds: "擷取間隔（秒）",
    capture_rotating_arm: "擷取旋臂視角",
    capture_top: "擷取頂視角",
    captures_dir: "擷取資料夾",
    controller: "控制器",
    current_limit_amp: "電流限制（安培）",
    database_path: "資料庫路徑",
    device_index: "裝置索引",
    device_name: "裝置名稱",
    device_version: "裝置版本",
    disengage_after_cycle: "循環後解除使用中",
    duration_minutes: "總時長（分鐘）",
    enabled: "啟用",
    end_deg: "結束角度",
    file_name: "檔案名稱",
    fixed_side: "固定側視角",
    full_step_angle_deg: "全步進角度",
    hardware: "硬體",
    height: "高度",
    holding_current_amp: "保持電流（安培）",
    jpeg_quality: "JPEG 品質",
    level: "層級",
    logging: "紀錄",
    logs_dir: "紀錄資料夾",
    maximum_acceleration_deg_s2: "最大加速度（度/秒²）",
    maximum_angle_deg: "最大角度",
    maximum_current_limit_amp: "最大電流（安培）",
    maximum_velocity_limit_deg_s: "最大速度（度/秒）",
    microstep_division: "微步進細分",
    minimum_angle_deg: "最小角度",
    mock_mode: "模擬模式",
    motor: "馬達",
    movement_timeout_seconds: "移動逾時（秒）",
    name: "名稱",
    name_zh: "中文名稱",
    origin_deg: "原點角度",
    paths: "路徑",
    preview_fps: "預覽 FPS",
    project: "專案",
    project_name: "專案名稱",
    project_name_zh: "專案中文名稱",
    return_to_origin: "回到原點",
    return_to_origin_after_cycle: "循環後回到原點",
    rotating_arm: "旋臂視角",
    rotation_enabled: "啟用旋轉",
    rotation_end_deg: "旋轉結束角度",
    rotation_start_deg: "旋轉起始角度",
    rotation_step_deg: "旋轉步進角度",
    stabilization_delay_ms: "穩定等待（毫秒）",
    temp_dir: "暫存資料夾",
    title: "標題",
    top: "頂視角",
    velocity_limit_deg_s: "速度限制（度/秒）",
    web: "網頁",
    width: "寬度",
  };
  return labels[key] || key;
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function fieldType(value) {
  if (typeof value === "boolean") return "boolean";
  if (typeof value === "number") return "number";
  return "string";
}

function createSettingField(path, key, value) {
  const type = fieldType(value);
  const label = settingLabel(key);

  if (type === "boolean") {
    const wrapper = document.createElement("label");
    wrapper.className = window.PhytoUI.checkboxField;

    const text = document.createElement("span");
    text.className = window.PhytoUI.checkboxLabel;
    text.textContent = label;

    const input = document.createElement("input");
    input.checked = Boolean(value);
    input.dataset.path = path.join(".");
    input.dataset.type = type;
    input.type = "checkbox";
    input.className = window.PhytoUI.checkbox;

    wrapper.append(text, input);
    return wrapper;
  }

  const wrapper = document.createElement("label");
  wrapper.className = window.PhytoUI.field;

  const text = document.createElement("span");
  text.className = window.PhytoUI.fieldLabel;
  text.textContent = label;

  const input = document.createElement("input");
  input.className = window.PhytoUI.input;
  input.dataset.path = path.join(".");
  input.dataset.type = type;
  input.type = type === "number" ? "number" : "text";
  input.value = value ?? "";

  if (type === "number" && !Number.isInteger(value)) {
    input.step = "0.1";
  }

  wrapper.append(text, input);
  return wrapper;
}

function createSettingsTree(value, path = []) {
  const fragment = document.createDocumentFragment();

  for (const [key, item] of Object.entries(value || {})) {
    const nextPath = [...path, key];

    if (isPlainObject(item)) {
      if (path.length === 0 && SETTINGS_GROUP_IDS.has(key)) {
        fragment.append(createSettingsTree(item, nextPath));
        continue;
      }

      const group = document.createElement("section");
      group.className = window.PhytoUI.settingsGroup;

      const title = document.createElement("div");
      title.className = window.PhytoUI.settingsGroupTitle;
      title.textContent = settingLabel(key);

      const fields = document.createElement("div");
      fields.className = window.PhytoUI.settingsFields;
      fields.append(createSettingsTree(item, nextPath));

      group.append(title, fields);
      fragment.append(group);
      continue;
    }

    fragment.append(createSettingField(nextPath, key, item));
  }

  return fragment;
}

function setNestedValue(target, path, value) {
  let current = target;
  for (let index = 0; index < path.length - 1; index += 1) {
    const key = path[index];
    current[key] = current[key] || {};
    current = current[key];
  }
  current[path[path.length - 1]] = value;
}

function collectSettingsPayload(container) {
  const payload = {};
  const fields = container.querySelectorAll("[data-path]");

  for (const field of fields) {
    const path = field.dataset.path.split(".");
    const type = field.dataset.type;
    let value = field.value;

    if (type === "boolean") {
      value = field.checked;
    } else if (type === "number") {
      value = Number(value);
    }

    setNestedValue(payload, path, value);
  }

  return payload;
}

async function saveSettingsGroup(group, container, message) {
  const payload = collectSettingsPayload(container);
  message.textContent = "儲存中...";
  await api(`/api/settings/${group}`, {
    method: "POST",
    body: JSON.stringify({ payload }),
  });
  message.textContent = "已儲存。部分硬體設定需重新啟動程式後才會套用。";
}

async function loadSettingsGroup(group, label) {
  const container = document.getElementById(`settings-${group}`);
  if (!container) return;

  container.textContent = "載入中...";
  const payload = await api(`/api/settings/${group}`);
  container.innerHTML = "";

  const header = document.createElement("div");
  header.className = window.PhytoUI.buttonRow;

  const saveButton = document.createElement("button");
  saveButton.className = window.PhytoUI.buttonStrong;
  saveButton.textContent = `儲存${label}設定`;
  saveButton.type = "button";

  const message = document.createElement("div");
  message.className = window.PhytoUI.settingsMessage;

  saveButton.addEventListener("click", async () => {
    saveButton.disabled = true;
    try {
      await saveSettingsGroup(group, container, message);
    } catch (error) {
      message.textContent = error.message;
    } finally {
      saveButton.disabled = false;
    }
  });

  header.append(saveButton, message);
  container.append(createSettingsTree(payload), header);
}

async function loadSettings() {
  await Promise.all(
    SETTINGS_GROUPS.map(([group, label]) => loadSettingsGroup(group, label)),
  );
}

function activateSettingsTab(group) {
  if (!SETTINGS_GROUP_IDS.has(group)) return;

  settingsState.activeTab = group;
  sessionStorage.setItem(SETTINGS_TAB_STORAGE_KEY, group);

  document.querySelectorAll("[data-settings-tab]").forEach((tab) => {
    const isActive = tab.dataset.settingsTab === group;
    tab.classList.toggle("is-active", isActive);
    tab.setAttribute("aria-selected", String(isActive));
    tab.tabIndex = isActive ? 0 : -1;
  });

  document.querySelectorAll("[data-settings-panel]").forEach((panel) => {
    const isActive = panel.dataset.settingsPanel === group;
    panel.hidden = !isActive;
    panel.setAttribute("aria-hidden", String(!isActive));
  });
}

function getInitialSettingsTab() {
  const storedTab = sessionStorage.getItem(SETTINGS_TAB_STORAGE_KEY);
  return SETTINGS_GROUP_IDS.has(storedTab) ? storedTab : settingsState.activeTab;
}

function setupSettingsTabs() {
  const tabList = document.querySelector("[role=tablist][aria-label='設定類別']");
  if (!tabList) return;

  tabList.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-settings-tab]");
    if (tab && tabList.contains(tab)) {
      activateSettingsTab(tab.dataset.settingsTab);
    }
  });

  tabList.addEventListener("keydown", (event) => {
    if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;

    const tabs = [...tabList.querySelectorAll("[data-settings-tab]")];
    const currentTab = event.target.closest("[data-settings-tab]");
    const currentIndex = tabs.indexOf(currentTab);
    if (currentIndex === -1) return;

    const nextIndex = event.key === "ArrowRight"
      ? (currentIndex + 1) % tabs.length
      : event.key === "ArrowLeft"
        ? (currentIndex - 1 + tabs.length) % tabs.length
        : event.key === "Home"
          ? 0
          : tabs.length - 1;
    const nextTab = tabs[nextIndex];

    event.preventDefault();
    activateSettingsTab(nextTab.dataset.settingsTab);
    nextTab.focus();
  });

  activateSettingsTab(getInitialSettingsTab());
}

function initializeSettings() {
  setupSettingsTabs();
  document.getElementById("reload-settings")?.addEventListener("click", () => {
    loadSettings().catch(console.error);
  });
  loadSettings().catch(console.error);
}

window.PhytoSettings = {
  state: settingsState,
  activateTab: activateSettingsTab,
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeSettings, { once: true });
} else {
  initializeSettings();
}
