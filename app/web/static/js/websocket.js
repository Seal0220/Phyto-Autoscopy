(function () {
  const state = {
    socket: null,
    commandId: 0,
    pending: new Map(),
    openWaiters: [],
    reconnectTimer: null,
    snapshot: null,
  };

  function socketUrl() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/ws/status`;
  }

  function updateIndicator(text, connected) {
    const indicator = document.getElementById("ws-indicator");
    if (!indicator) return;
    indicator.textContent = text;
    indicator.className = connected
      ? window.PhytoUI.chipOnline
      : window.PhytoUI.chipOffline;
    indicator.dataset.statusTone = connected ? "success" : "offline";
  }

  function resolveOpenWaiters() {
    const waiters = state.openWaiters.splice(0);
    for (const waiter of waiters) waiter.resolve();
  }

  function rejectOpenWaiters(error) {
    const waiters = state.openWaiters.splice(0);
    for (const waiter of waiters) waiter.reject(error);
  }

  function publishSnapshot(snapshot) {
    state.snapshot = snapshot;
    document.dispatchEvent(new CustomEvent("phyto:snapshot", { detail: snapshot }));
  }

  function handleMessage(event) {
    const message = JSON.parse(event.data);
    if (message.type === "snapshot") {
      publishSnapshot(message.payload);
      return;
    }
    if (message.type === "command_result") {
      const pending = state.pending.get(message.id);
      if (!pending) return;
      state.pending.delete(message.id);
      if (message.ok) {
        pending.resolve(message.payload);
      } else {
        pending.reject(new Error(message.detail || "即時命令執行失敗"));
      }
      return;
    }
    if (message.type === "error") {
      console.error(message.detail);
    }
  }

  function connect() {
    if (state.socket && state.socket.readyState <= WebSocket.OPEN) return;
    state.socket = new WebSocket(socketUrl());
    updateIndicator("連線中", false);

    state.socket.addEventListener("open", () => {
      updateIndicator("連線正常", true);
      resolveOpenWaiters();
    });
    state.socket.addEventListener("message", handleMessage);
    state.socket.addEventListener("close", () => {
      updateIndicator("連線離線", false);
      rejectOpenWaiters(new Error("即時連線已關閉"));
      for (const pending of state.pending.values()) {
        pending.reject(new Error("即時連線已關閉"));
      }
      state.pending.clear();
      window.clearTimeout(state.reconnectTimer);
      state.reconnectTimer = window.setTimeout(connect, 1200);
    });
    state.socket.addEventListener("error", () => {
      updateIndicator("連線錯誤", false);
    });
  }

  function waitForOpen() {
    connect();
    if (state.socket && state.socket.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }
    return new Promise((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        reject(new Error("即時連線逾時"));
      }, 6000);
      state.openWaiters.push({
        resolve: () => {
          window.clearTimeout(timeout);
          resolve();
        },
        reject: (error) => {
          window.clearTimeout(timeout);
          reject(error);
        },
      });
    });
  }

  async function command(action, payload = {}) {
    await waitForOpen();
    const id = `cmd_${Date.now()}_${state.commandId++}`;
    const message = { type: "command", id, action, payload };
    const result = new Promise((resolve, reject) => {
      state.pending.set(id, { resolve, reject });
    });
    state.socket.send(JSON.stringify(message));
    return result;
  }

  window.PhytoSocket = {
    command,
    connect,
    getSnapshot: () => state.snapshot,
  };

  document.addEventListener("DOMContentLoaded", connect);
})();
