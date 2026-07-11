import SettingsPanel from "@/components/settings-panel";
import Button from "@/components/ui/button";
import { NumericField } from "@/components/ui/field";
import InnerPanel from "@/components/ui/inner-panel";
import { Panel, PanelHeader } from "@/components/ui/panel";
import SettingsGear from "@/components/ui/settings-gear";

const SCHEDULE_FIELDS = [
  ["capture_interval_seconds", "擷取間隔（秒）"],
  ["duration_minutes", "總時長（分鐘）"],
  ["rotation_start_deg", "起始角度"],
  ["rotation_end_deg", "結束角度"],
  ["rotation_step_deg", "步進角度"],
];

const ROTATION_FIELDS = [
  ["cycle_id", "循環編號"],
  ["start_deg", "起始角度"],
  ["end_deg", "結束角度"],
  ["step_deg", "步進角度"],
];

export default function ExperimentSection({ isConnected, busyAction, open, onToggle, onNotify, onRunAction, schedule, setSchedule, rotation, setRotation, onScheduleSubmit, onRotationSubmit }) {
  return (
    <Panel id="schedule" className="min-[981px]:col-start-1 min-[981px]:row-start-2 [scroll-margin-top:5.6rem] max-[980px]:[scroll-margin-top:8.8rem]" aria-label="實驗排程">
      <PanelHeader title="實驗排程" action={<SettingsGear label="實驗" open={open} onClick={onToggle} />} />
      <div className="grid gap-4 p-5 min-[720px]:grid-cols-2 max-sm:p-4">
        <InnerPanel as="form" onSubmit={onScheduleSubmit}>
          <h3 className="m-0 text-base font-black text-white">開始實驗</h3>
          <div className="grid gap-3 min-[520px]:grid-cols-2">
            {SCHEDULE_FIELDS.map(([key, label]) => <NumericField key={key} label={label} value={schedule[key]} onValueChange={(nextValue) => setSchedule((previous) => ({ ...previous, [key]: nextValue }))} required />)}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" type="submit" disabled={!isConnected || busyAction === "experiment.start"}>開始</Button>
            <Button disabled={!isConnected || busyAction === "experiment.pause"} onClick={() => void onRunAction("experiment.pause", {}, "實驗已暫停。")}>暫停</Button>
            <Button disabled={!isConnected || busyAction === "experiment.resume"} onClick={() => void onRunAction("experiment.resume", {}, "實驗已繼續。")}>繼續</Button>
            <Button variant="danger" disabled={!isConnected || busyAction === "experiment.stop"} onClick={() => void onRunAction("experiment.stop", {}, "實驗已停止。")}>停止</Button>
          </div>
        </InnerPanel>
        <InnerPanel as="form" onSubmit={onRotationSubmit}>
          <h3 className="m-0 text-base font-black text-white">手動旋轉擷取</h3>
          <div className="grid gap-3 min-[520px]:grid-cols-2">
            {ROTATION_FIELDS.map(([key, label]) => <NumericField key={key} label={label} value={rotation[key]} onValueChange={(nextValue) => setRotation((previous) => ({ ...previous, [key]: nextValue }))} required />)}
          </div>
          <Button className="justify-self-start" variant="primary" type="submit" disabled={!isConnected || busyAction === "capture.rotation_cycle"}>執行旋轉擷取</Button>
        </InnerPanel>
      </div>
      <SettingsPanel group="experiment" label="實驗" onNotify={onNotify} open={open} />
    </Panel>
  );
}
