import { Panel, PanelHeader } from "@/components/ui/panel";

export default function RecentMessagesSection({ errors = [] }) {
  return (
    <Panel id="recent-messages" aria-label="近期訊息">
      <PanelHeader title="近期訊息" />
      <div className="p-5 max-sm:p-4">
        <div className="rounded-xl border border-rose-200/15 bg-rose-950/30 p-3 text-sm text-rose-100/85">
          {errors.length ? <ul className="grid gap-2">{errors.map((error, index) => <li key={`${error}-${index}`}>{error}</li>)}</ul> : <p>尚無近期錯誤</p>}
        </div>
      </div>
    </Panel>
  );
}
