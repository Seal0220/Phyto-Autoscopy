function sessionStatusText(value) {
  return window.PhytoFormat?.statusText?.(value) || value || "-";
}

async function refreshSessions() {
  const sessions = await window.PhytoSocket.command("sessions.list");
  const ui = window.PhytoUI;
  const body = document.getElementById("sessions-body");
  body.innerHTML = "";
  if (!sessions.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td class="${ui.tableCell}" colspan="4">目前沒有工作階段紀錄</td>`;
    body.appendChild(row);
    return;
  }
  for (const session of sessions) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td class="${ui.tableCellStrong}">${session.session_id}</td>
      <td class="${ui.tableCell}"><span class="${ui.chipAccent}">${sessionStatusText(session.status)}</span></td>
      <td class="${ui.tableCell}">${session.created_at}</td>
      <td class="${ui.tableCell}">
        <div class="${ui.buttonRow}">
          <a class="${ui.button}" href="/api/sessions/${session.session_id}/metadata">中繼資料</a>
          <a class="${ui.button}" href="/api/sessions/${session.session_id}/session-json">工作階段資料</a>
        </div>
      </td>
    `;
    body.appendChild(row);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("refresh-sessions")?.addEventListener("click", refreshSessions);
  refreshSessions().catch(console.error);
});
