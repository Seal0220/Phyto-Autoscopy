"use client";

import {
  FiPause,
  FiPlay,
  FiSquare,
} from "react-icons/fi";

import ActionRow from "@/components/actions/ActionRow";
import Button from "@/components/buttons/Button";
import { Panel, PanelHeader } from "@/components/panels/Panel";
import SettingsGear from "@/components/panels/SettingsGear";
import Settings from "@/features/Settings/Settings";

import ScheduleCommonControls from "./components/ScheduleCommonControls";
import ScheduleModes from "./components/ScheduleModes";
import ScheduleRuntimeStatus from "./components/ScheduleRuntimeStatus";
import useSchedule from "./hooks/useSchedule";

export default function Schedule({
  experiment,
  motor,
  isConnected,
  busyAction,
  scheduleActive,
  open,
  onToggle,
  onNotify,
  onRunAction,
  onStarted,
}) {
  const {
    schedule,
    setSchedule,
    handleSubmit,
  } = useSchedule({
    onNotify,
    onRunAction,
    onStarted,
  });
  const status = experiment.status || "idle";
  const canEdit = ["idle", "stopped", "completed", "failed"].includes(status);
  const active = ["running", "paused", "stopping"].includes(status);
  const paused = status === "paused";
  const stopping = status === "stopping" || busyAction === "experiment.stop";

  return (
    <>
      <ScheduleRuntimeStatus
        experiment={experiment}
        motor={motor}
        schedule={schedule}
      />
      <Panel
        id="schedule"
        className="min-[981px]:col-start-1 min-[981px]:row-start-3 scroll-mt-[5.6rem] max-[980px]:scroll-mt-[8.8rem]"
        aria-label="排程"
      >
        <PanelHeader
          title="排程"
          action={(
            <SettingsGear
              label="排程"
              open={open}
              onClick={onToggle}
            />
          )}
        />
        <form
          className="grid gap-4 p-5 max-sm:p-4"
          onSubmit={handleSubmit}
        >
          <fieldset
            className={`grid gap-4 border-0 p-0 ${scheduleActive ? "grayscale opacity-60" : ""}`}
            disabled={!canEdit}
          >
            <ScheduleCommonControls
              schedule={schedule}
              setSchedule={setSchedule}
            />
            <hr />
            <ScheduleModes
              schedule={schedule}
              setSchedule={setSchedule}
              canEdit={canEdit}
            />
          </fieldset>

          <ActionRow>
            {active ? (
              <Button
                variant="danger"
                disabled={!isConnected || stopping || Boolean(busyAction)}
                onClick={() => void onRunAction("experiment.stop", {}, "正在停止排程。")}
              >
                <FiSquare
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                {stopping ? "停止中…" : "停止排程"}
              </Button>
            ) : (
              <Button
                variant="primary"
                type="submit"
                disabled={!isConnected || !canEdit || !schedule.modes.length || Boolean(busyAction)}
              >
                <FiPlay
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
                開始排程
              </Button>
            )}
            <Button
              disabled={!isConnected || !["running", "paused"].includes(status) || Boolean(busyAction)}
              onClick={() => void onRunAction(
                paused ? "experiment.resume" : "experiment.pause",
                {},
                paused ? "排程已繼續。" : "排程已暫停。",
              )}
            >
              {paused ? (
                <FiPlay
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
              ) : (
                <FiPause
                  className="size-4 shrink-0"
                  aria-hidden="true"
                />
              )}
              {paused ? "繼續" : "暫停"}
            </Button>
          </ActionRow>
        </form>
        <Settings
          group="experiment"
          label="排程"
          onNotify={onNotify}
          open={open}
          locked={scheduleActive}
        />
      </Panel>
    </>
  );
}
