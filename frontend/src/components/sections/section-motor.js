import MotorDirectControls from "@/components/motor/motor-direct-controls";
import SettingsPanel from "@/components/settings-panel";
import { Panel, PanelHeader } from "@/components/ui/panel";
import SettingsGear from "@/components/ui/settings-gear";

export default function MotorSection({
  motor,
  isConnected,
  busyAction,
  scheduleActive,
  open,
  onToggle,
  onNotify,
  onRunAction,
}) {
  return (
    <Panel id="motor" className="min-[981px]:col-start-1 min-[981px]:row-start-3 scroll-mt-[5.6rem] max-[980px]:scroll-mt-[8.8rem]" aria-label="控制">
      <PanelHeader
        title="控制"
        action={<SettingsGear label="馬達" open={open} onClick={onToggle} />}
        muted={scheduleActive}
      />
      <div className="p-5 max-sm:p-4">
        <MotorDirectControls
          motor={motor}
          isConnected={isConnected}
          busyAction={busyAction}
          scheduleActive={scheduleActive}
          onRunAction={onRunAction}
        />
      </div>
      <SettingsPanel
        group="motor"
        label="馬達"
        onNotify={onNotify}
        open={open}
        locked={scheduleActive}
      />
    </Panel>
  );
}
