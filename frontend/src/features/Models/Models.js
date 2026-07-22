import InnerPanel from "@/components/panels/InnerPanel";
import {
  Panel,
  PanelHeader,
} from "@/components/panels/Panel";

export default function Models() {
  return (
    <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-24 max-[980px]:pt-32">
        <Panel>
          <PanelHeader title="模型" />
          <div className="grid gap-4 p-5 max-sm:p-4">
            <InnerPanel>
              <p className="m-0 text-sm font-bold text-neutral-300">
                模型模組尚未啟用
              </p>
            </InnerPanel>
          </div>
        </Panel>
    </div>
  );
}
