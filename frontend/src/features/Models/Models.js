import InnerPanel from "@/components/panels/InnerPanel";
import {
  Panel,
  PanelHeader,
} from "@/components/panels/Panel";
import MainNavigation from "@/features/MainNavigation/MainNavigation";

export default function Models() {
  return (
    <main className="min-h-screen bg-[#06100c] px-5 pb-8 max-sm:px-3">
      <MainNavigation />

      <div className="mx-auto grid w-full max-w-[112.5rem] gap-4 pt-[5.6rem] max-[980px]:pt-[8.8rem]">
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
    </main>
  );
}
