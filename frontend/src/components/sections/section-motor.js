import SettingsPanel from "@/components/settings-panel";
import Button from "@/components/ui/button";
import { NumericField } from "@/components/ui/field";
import { Panel, PanelHeader, StatusPill } from "@/components/ui/panel";
import SettingsGear from "@/components/ui/settings-gear";

const MOTOR_ACTIONS = [
  ["motor.engage", "保持扭力"],
  ["motor.disengage", "釋放馬達"],
  ["motor.set_origin", "設為原點"],
  ["motor.return_origin", "回到原點"],
  ["motor.stop", "停止"],
];

export default function MotorSection({ motor, isConnected, busyAction, open, onToggle, onNotify, onRunAction, moveAngle, setMoveAngle, onMoveSubmit }) {
  return (
    <Panel id="motor" className="min-[981px]:col-start-1 min-[981px]:row-start-3 [scroll-margin-top:5.6rem] max-[980px]:[scroll-margin-top:8.8rem]" aria-label="馬達控制">
      <PanelHeader title="馬達控制" action={<SettingsGear label="馬達" open={open} onClick={onToggle} />} />
      <div className="grid gap-5 p-5 min-[720px]:grid-cols-[minmax(12rem,0.6fr)_minmax(0,1fr)] max-sm:p-4">
        <dl className="grid content-start">
          <div className="flex items-center justify-between gap-3 border-b border-white/10 py-2.5 first:pt-0"><dt className="text-sm text-white/65">連線</dt><dd><StatusPill tone={motor.connected ? "success" : "warning"}>{motor.connected ? "已連線" : "離線"}</StatusPill></dd></div>
          <div className="flex items-center justify-between gap-3 border-b border-white/10 py-2.5"><dt className="text-sm text-white/65">保持扭力</dt><dd className="text-right text-sm font-black text-white">{motor.engaged ? "已啟用" : "已釋放"}</dd></div>
          <div className="flex items-center justify-between gap-3 border-b border-white/10 py-2.5"><dt className="text-sm text-white/65">指令位置</dt><dd className="text-right text-sm font-black text-white">{Number.isFinite(motor.command_position_deg) ? `${motor.command_position_deg}°` : "—"}</dd></div>
          <div className="flex items-center justify-between gap-3 py-2.5 last:pb-0"><dt className="text-sm text-white/65">速度限制</dt><dd className="text-right text-sm font-black text-white">{motor.velocity_limit_deg_s ?? "—"}</dd></div>
        </dl>
        <div className="grid content-start gap-4">
          <div className="flex flex-wrap gap-2">
            {MOTOR_ACTIONS.map(([action, label]) => <Button key={action} disabled={!isConnected || busyAction === action} onClick={() => void onRunAction(action, {}, `${label}命令已送出。`)}>{label}</Button>)}
          </div>
          <form className="grid gap-2 min-[520px]:grid-cols-[minmax(0,1fr)_auto] min-[520px]:items-end" onSubmit={onMoveSubmit}>
            <NumericField id="move-angle" label="移動至角度" value={moveAngle} onValueChange={setMoveAngle} min={0} max={360} step={0.1} required />
            <Button variant="primary" type="submit" disabled={!isConnected || busyAction === "motor.move"}>移動</Button>
          </form>
        </div>
      </div>
      <SettingsPanel group="motor" label="馬達" onNotify={onNotify} open={open} />
    </Panel>
  );
}
