import SettingsPanel from "@/components/settings-panel";
import Button from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import SettingsGear from "@/components/ui/settings-gear";

function formatDate(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-TW", { hour12: false });
}

export default function SessionsSection({ sessions, loading, open, onToggle, onNotify, onLoad }) {
  return (
    <Panel id="sessions" className="min-[981px]:col-start-1 min-[981px]:row-start-4 [scroll-margin-top:5.6rem] max-[980px]:[scroll-margin-top:8.8rem]" aria-label="工作階段">
      <PanelHeader title="工作階段" action={<div className="flex items-center gap-2"><Button onClick={() => void onLoad()} disabled={loading}>{loading ? "讀取中…" : "重新整理"}</Button><SettingsGear label="紀錄" open={open} onClick={onToggle} /></div>} />
      <div className="overflow-x-auto p-5 max-sm:p-4">
        <table className="w-full min-w-[38rem] border-collapse text-left text-sm">
          <thead><tr className="border-b border-white/10 bg-white/[0.03] text-[11px] font-black tracking-[0.12em] text-white/55"><th className="px-4 py-3">工作階段</th><th className="px-4 py-3">狀態</th><th className="px-4 py-3">建立時間</th><th className="px-4 py-3">匯出</th></tr></thead>
          <tbody>
            {sessions.length ? sessions.map((session) => (
              <tr className="border-b border-white/10 text-white/85 last:border-b-0" key={session.session_id}>
                <td className="px-4 py-3.5">{session.session_id}</td>
                <td className="px-4 py-3.5">{session.status}</td>
                <td className="px-4 py-3.5">{formatDate(session.created_at)}</td>
                <td className="flex gap-3 px-4 py-3.5"><a className="font-black text-emerald-200 hover:text-emerald-100" href={`/api/sessions/${encodeURIComponent(session.session_id)}/metadata`}>CSV</a><a className="font-black text-emerald-200 hover:text-emerald-100" href={`/api/sessions/${encodeURIComponent(session.session_id)}/session-json`}>JSON</a></td>
              </tr>
            )) : <tr><td colSpan="4">尚無工作階段。</td></tr>}
          </tbody>
        </table>
      </div>
      <SettingsPanel group="logging" label="紀錄" onNotify={onNotify} open={open} />
    </Panel>
  );
}
