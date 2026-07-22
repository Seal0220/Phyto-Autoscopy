export const STORAGE_PATH_FIELDS = [
  {
    key: "captures_dir",
    label: "擷取檔案儲存位置",
    description: "排程產生的影像、模式日誌與紀錄會儲存在此目錄。",
  },
  {
    key: "snapshots_dir",
    label: "單張影像儲存位置",
    description: "攝影機中的單張擷取會直接儲存在此目錄，不會建立排程紀錄。",
  },
  {
    key: "calibration_dir",
    label: "校正檔案位置",
  },
  {
    key: "logs_dir",
    label: "系統日誌位置",
  },
  {
    key: "temp_dir",
    label: "暫存檔案位置",
  },
];

export const RECORD_STATUS_LABELS = {
  idle: "待命",
  manual: "手動擷取",
  running: "執行中",
  paused: "已暫停",
  stopping: "停止中",
  stopped: "已停止",
  completed: "已完成",
  failed: "失敗",
};

export const RECORD_EXPORT_META = {
  csv: {
    endpoint: "metadata",
    filenameSuffix: "metadata.csv",
    label: "CSV",
  },
  json: {
    endpoint: "config-json",
    filenameSuffix: "config.json",
    label: "JSON",
  },
};
