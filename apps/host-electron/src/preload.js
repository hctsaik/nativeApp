const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("cimHost", {
  getAppConfig: () => ipcRenderer.invoke("get-app-config"),
  listTools: () => ipcRenderer.invoke("list-tools"),
  startTool: (toolId) => ipcRenderer.invoke("start-tool", toolId),
  startSheetTab: (pluginId) => ipcRenderer.invoke("start-sheet-tab", pluginId),
  stopTool: () => ipcRenderer.invoke("stop-tool"),
  chooseFile: (options) => ipcRenderer.invoke("choose-file", options),
  onSidecarExited: (handler) => {
    ipcRenderer.on("sidecar-exited", (_event, payload) => handler(payload));
  },
  onSidecarRestarting: (handler) => {
    ipcRenderer.on("sidecar-restarting", (_event, payload) => handler(payload));
  },
  onSidecarReady: (handler) => {
    ipcRenderer.on("sidecar-ready", (_event, payload) => handler(payload));
  },
  onSidecarRestartFailed: (handler) => {
    ipcRenderer.on("sidecar-restart-failed", (_event, payload) => handler(payload));
  },
  restartSidecar: () => ipcRenderer.invoke("restart-sidecar"),
  getToolStatus: () => ipcRenderer.invoke("get-tool-status"),
  startSheetTab: (pluginId) => ipcRenderer.invoke("start-sheet-tab", pluginId),
  getRuntimeStatus: () => ipcRenderer.invoke("get-runtime-status"),
  getDiagnostics: () => ipcRenderer.invoke("get-diagnostics"),
  log: (level, message) => ipcRenderer.send("renderer-log", level, message),
  externalOpenXanylabeling: (imageUrl, metadata) => ipcRenderer.invoke("external-open-xanylabeling", imageUrl, metadata),
  externalOpenLabelingTool: (tool, imageUrl, metadata) => ipcRenderer.invoke("external-open-labeling-tool", tool, imageUrl, metadata),
  externalQueueImage: (imageUrl, metadata) => ipcRenderer.invoke("external-queue-image", imageUrl, metadata),
  externalGetQueue: () => ipcRenderer.invoke("external-get-queue"),
  externalDequeue: (itemId) => ipcRenderer.invoke("external-dequeue", itemId),
});
