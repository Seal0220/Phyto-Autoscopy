import Settings from "@/features/Settings/Settings";
import { Panel, PanelHeader } from "@/components/panels/Panel";
import SettingsGear from "@/components/panels/SettingsGear";

import MotorControls from "./components/MotorControls";

export default function Control({
  motor,
  isConnected,
  busyActions,
  scheduleActive,
  open,
  onToggle,
  onNotify,
  onRunAction,
}) {
  return (
    <Panel
      id="control"
      className="min-[981px]:col-start-1 min-[981px]:row-start-4 scroll-mt-[8.75rem] max-[980px]:scroll-mt-[11.5rem]"
      aria-label="控制"
    >
      <PanelHeader
        title="控制"
        action={(
          <SettingsGear
            label="馬達"
            open={open}
            onClick={onToggle}
          />
        )}
        muted={scheduleActive}
      />
      <div className="p-5 max-sm:p-4">
        <MotorControls
          motor={motor}
          isConnected={isConnected}
          busyActions={busyActions}
          scheduleActive={scheduleActive}
          onRunAction={onRunAction}
        />
      </div>
      <Settings
        group="motor"
        label="馬達"
        onNotify={onNotify}
        open={open}
        locked={scheduleActive}
      />
    </Panel>
  );
}
