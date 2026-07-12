import {
  FiAlertTriangle,
  FiCheckCircle,
  FiInfo,
} from "react-icons/fi";

export const NOTIFICATION_META = {
  success: {
    border: "border-l-emerald-300",
    icon: "text-emerald-300",
    label: "成功",
    Icon: FiCheckCircle,
  },
  error: {
    border: "border-l-rose-400",
    icon: "text-rose-300",
    label: "錯誤",
    Icon: FiAlertTriangle,
  },
  info: {
    border: "border-l-slate-400",
    icon: "text-slate-300",
    label: "訊息",
    Icon: FiInfo,
  },
};
