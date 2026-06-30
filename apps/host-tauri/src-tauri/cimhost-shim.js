// module 03 — cimhost-bridge(注入端)
// 在 portal bundle 執行前注入(Tauri initialization_script),定義 window.cimHost,
// 介面與 Electron preload.js 逐一同名同簽章。底層改走 Tauri invoke/listen。
// 對映:方法→#[tauri::command](camelCase 參數會被 Tauri 自動轉 snake_case)、事件→listen。
(function () {
  var tauri = (typeof window !== "undefined" && window.__TAURI__) || {};
  var invoke = tauri.core && tauri.core.invoke;
  var listen = tauri.event && tauri.event.listen;

  function on(eventName, handler) {
    // 對映 Electron ipcRenderer.on：把 Tauri event 的 payload 交給 handler。
    if (!listen) return;
    listen(eventName, function (e) { handler(e.payload); });
  }

  window.cimHost = {
    // ── 設定/清單 ──
    getAppConfig: function () { return invoke("get_app_config"); },
    listTools: function () { return invoke("list_tools"); },
    // ── 工具生命週期 ──
    startTool: function (toolId) { return invoke("start_tool", { toolId: toolId }); },
    startSheetTab: function (pluginId) { return invoke("start_sheet_tab", { pluginId: pluginId }); },
    stopTool: function () { return invoke("stop_tool"); },
    getToolStatus: function () { return invoke("get_tool_status"); },
    getRuntimeStatus: function () { return invoke("get_runtime_status"); },
    getDiagnostics: function () { return invoke("get_diagnostics"); },
    // ── 原生 ──
    chooseFile: function (options) { return invoke("choose_file", { options: options }); },
    restartSidecar: function () { return invoke("restart_sidecar"); },
    log: function (level, message) { return invoke("renderer_log", { level: level, message: message }); },
    // ── 外部標註工具 ──
    externalOpenXanylabeling: function (imageUrl, metadata) {
      return invoke("external_open_xanylabeling", { imageUrl: imageUrl, metadata: metadata });
    },
    externalOpenLabelingTool: function (tool, imageUrl, metadata) {
      return invoke("external_open_labeling_tool", { tool: tool, imageUrl: imageUrl, metadata: metadata });
    },
    externalQueueImage: function (imageUrl, metadata) {
      return invoke("external_queue_image", { imageUrl: imageUrl, metadata: metadata });
    },
    externalGetQueue: function () { return invoke("external_get_queue"); },
    externalDequeue: function (itemId) { return invoke("external_dequeue", { itemId: itemId }); },
    // ── sidecar 生命週期事件(對映 webContents.send）──
    onSidecarExited: function (handler) { on("sidecar-exited", handler); },
    onSidecarRestarting: function (handler) { on("sidecar-restarting", handler); },
    onSidecarReady: function (handler) { on("sidecar-ready", handler); },
    onSidecarRestartFailed: function (handler) { on("sidecar-restart-failed", handler); },
  };
})();
