// module 03 shim 單元測試(/pm 擁有,PG 唯讀)。對映 3_Architect_Design/10_module-contracts.md。
// 不需 Tauri/瀏覽器:讀 shim 原始碼,用假 window.__TAURI__ 評估,斷言介面與 invoke 對映。
import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const shimSrc = readFileSync(join(here, "..", "src-tauri", "cimhost-shim.js"), "utf8");

function loadShim() {
  const invoke = vi.fn(() => Promise.resolve({}));
  const listen = vi.fn();
  const window = { __TAURI__: { core: { invoke }, event: { listen } } };
  // shim 是 IIFE,內部引用 `window`;用 Function 把它注入。
  new Function("window", shimSrc)(window);
  return { window, invoke, listen };
}

const METHODS = [
  "getAppConfig", "listTools", "startTool", "startSheetTab", "stopTool", "chooseFile",
  "restartSidecar", "getToolStatus", "getRuntimeStatus", "getDiagnostics", "log",
  "externalOpenXanylabeling", "externalOpenLabelingTool", "externalQueueImage",
  "externalGetQueue", "externalDequeue",
];
const EVENTS = ["onSidecarExited", "onSidecarRestarting", "onSidecarReady", "onSidecarRestartFailed"];

describe("cimhost-shim", () => {
  it("AC3.1 暴露全部 16 方法 + 4 事件,一個不缺、不多", () => {
    const { window } = loadShim();
    for (const k of [...METHODS, ...EVENTS]) {
      expect(typeof window.cimHost[k], `cimHost.${k} 應為 function`).toBe("function");
    }
    expect(Object.keys(window.cimHost).sort()).toEqual([...METHODS, ...EVENTS].sort());
  });

  it("AC3.2 方法 → invoke(command, args) 對映正確", () => {
    const { window, invoke } = loadShim();
    window.cimHost.listTools();
    expect(invoke).toHaveBeenCalledWith("list_tools");
    window.cimHost.startTool("m7");
    expect(invoke).toHaveBeenCalledWith("start_tool", { toolId: "m7" });
    window.cimHost.startSheetTab("p1");
    expect(invoke).toHaveBeenCalledWith("start_sheet_tab", { pluginId: "p1" });
    window.cimHost.stopTool();
    expect(invoke).toHaveBeenCalledWith("stop_tool");
    window.cimHost.externalDequeue("id1");
    expect(invoke).toHaveBeenCalledWith("external_dequeue", { itemId: "id1" });
    window.cimHost.log("info", "hello");
    expect(invoke).toHaveBeenCalledWith("renderer_log", { level: "info", message: "hello" });
    window.cimHost.externalOpenLabelingTool("x-anylabeling", "u", { a: 1 });
    expect(invoke).toHaveBeenCalledWith("external_open_labeling_tool", {
      tool: "x-anylabeling", imageUrl: "u", metadata: { a: 1 },
    });
  });

  it("AC3.1 事件訂閱 → Tauri listen,並把 payload 轉交 handler", () => {
    const { window, listen } = loadShim();
    const handler = vi.fn();
    window.cimHost.onSidecarReady(handler);
    expect(listen).toHaveBeenCalledWith("sidecar-ready", expect.any(Function));
    const forwarded = listen.mock.calls[0][1];
    forwarded({ payload: { code: 0 } });
    expect(handler).toHaveBeenCalledWith({ code: 0 });
  });
});
