import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { AlertTriangle, CheckCircle2, Clock3, FileText, RefreshCw, Square } from "lucide-react";
import { MessageTypes, isProtocolMessage } from "@cim/shared-protocol";
import "./styles.css";

const fallbackApi = {
  async getAppConfig() {
    return { mockJwt: "mock.jwt.token", allowedOrigins: ["*"] };
  },
  async startTool() {
    return { input_url: "", output_url: "", input_port: 0, output_port: 0, category: "module", sheet_tabs: [] };
  },
  async stopTool() {
    return {};
  },
  async listTools() {
    return [{ tool_id: "sample-csv", name: "Sample CSV Analyzer", version: "0.1.0", category: "tool" }];
  },
  async restartSidecar() {
    return {};
  },
  async getToolStatus() {
    return { active: false };
  },
  async getRuntimeStatus() {
    return { ok: true };
  },
  async getDiagnostics() {
    return { ok: true, active_tool: { active: false } };
  },
};

const nativeApi = window.cimHost ?? fallbackApi;

function cimLog(level, message) {
  console[level]?.(`[cim:${level}]`, message);
  nativeApi.log?.(level, message);
}

function isAllowedOrigin(origin, allowedOrigins = []) {
  return allowedOrigins.includes("*") || allowedOrigins.includes(origin);
}

// ── Tool category grouping ────────────────────────────────
const CATEGORY_LABELS = {
  module:     "模組",
  sheet:      "頁面套件",
  management: "管理",
  external: "External",
};
const CATEGORY_ORDER = ["module", "sheet", "external", "management"];

function groupTools(tools) {
  const groups = {};
  for (const t of tools) {
    const cat = t.category ?? "tool";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(t);
  }
  return groups;
}

// ── Sub-components ────────────────────────────────────────

function SidecarError({ restarting, onRestart }) {
  if (restarting) {
    return (
      <div className="sidecar-error sidecar-restarting">
        <RefreshCw size={16} className="spin" />
        Local engine restarting…
      </div>
    );
  }
  return (
    <div className="sidecar-error">
      <AlertTriangle size={16} />
      Local engine stopped.
      {onRestart && (
        <button className="btn-restart" onClick={onRestart}>
          <RefreshCw size={14} /> Restart
        </button>
      )}
    </div>
  );
}

function ToolError({ message }) {
  return (
    <div className="sidecar-error">
      <AlertTriangle size={16} />
      {message}
    </div>
  );
}

function TopBar({ tools, selectedToolId, onToolChange, activeTool, onStart, onStop, status, sidecarDown, devMode }) {
  return (
    <header className="toolbar">
      <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
        <span className="top-bar-brand">CIM Platform</span>
        <span className={`mode-badge ${devMode ? "mode-badge-dev" : "mode-badge-prod"}`}>
          {devMode ? "DEV" : "PROD"}
        </span>
        <div className="toolbar-title">
          <p>{status}</p>
        </div>
      </div>
      <div className="actions">
        <div className="toolSelectGroup">
          <label className="toolSelectLabel">Portal 功能下拉選擇</label>
          <select
            className="toolSelect"
            value={selectedToolId}
            onChange={(e) => onToolChange(e.target.value)}
            disabled={sidecarDown || !!activeTool}
          >
            {(() => {
              const groups = groupTools(tools);
              return CATEGORY_ORDER
                .filter(cat => groups[cat]?.length)
                .map(cat => (
                  <optgroup key={cat} label={CATEGORY_LABELS[cat] ?? cat}>
                    {groups[cat].map(t => (
                      <option key={t.tool_id} value={t.tool_id}>{t.name}</option>
                    ))}
                  </optgroup>
                ));
            })()}
          </select>
        </div>
        {activeTool ? (
          <button onClick={onStop} className="btn-danger">
            <Square size={17} />
            Stop {activeTool.name}
          </button>
        ) : (
          <button onClick={onStart} disabled={!selectedToolId || sidecarDown}>
            <RefreshCw size={17} />
            Start Tool
          </button>
        )}
      </div>
    </header>
  );
}


// ── Regular (module) panel ────────────────────────────────

function LeftPanel({ activeTab, onTabChange, inputUrl, outputUrl, isExecuting, isStarting }) {
  return (
    <div className="left-panel">
      <div className="tab-bar">
        <button className={`tab${activeTab === "input" ? " active" : ""}`} onClick={() => onTabChange("input")}>
          Input
        </button>
        <button className={`tab${activeTab === "output" ? " active" : ""}`} onClick={() => onTabChange("output")}>
          Output
        </button>
      </div>

      <div className="tab-content">
        {inputUrl
          ? <iframe title="Input" src={inputUrl} style={{ display: activeTab === "input" ? "block" : "none" }} />
          : activeTab === "input" && <div className="tab-empty">請先選擇功能並按下 Start Tool</div>
        }
        {outputUrl
          ? <iframe title="Output" src={outputUrl} style={{ display: activeTab === "output" ? "block" : "none" }} />
          : activeTab === "output" && <div className="tab-empty">尚未執行，請在 Input 頁籤完成輸入</div>
        }
      </div>

      {isStarting && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <span>模組載入中，請稍候…</span>
        </div>
      )}
      {!isStarting && isExecuting && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <span>執行中…</span>
        </div>
      )}
    </div>
  );
}


// ── Sheet panel ───────────────────────────────────────────
// Each sheet tab has its own dedicated input + output Streamlit process.
// All iframes are kept mounted (display:none when inactive) to preserve session state.

function SheetLayout({ sheetTabs, activeSheetTabIdx, onSheetTabChange, activeTab, onTabChange, isExecuting, isStarting, sheetOutputNonces = {} }) {
  return (
    <div className="left-panel">
      {/* Sheet module tabs */}
      <div className="sheet-module-bar">
        {sheetTabs.map((tab, i) => (
          <button
            key={tab.plugin_id}
            className={`sheet-module-tab${i === activeSheetTabIdx ? " active" : ""}`}
            onClick={() => onSheetTabChange(i)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Input / Output sub-tabs */}
      <div className="tab-bar">
        <button className={`tab${activeTab === "input" ? " active" : ""}`} onClick={() => onTabChange("input")}>
          Input
        </button>
        <button className={`tab${activeTab === "output" ? " active" : ""}`} onClick={() => onTabChange("output")}>
          Output
        </button>
      </div>

      {/* Iframes: all tabs rendered, only active shown */}
      <div className="tab-content">
        {sheetTabs.map((tab, i) => {
          const nonce = sheetOutputNonces[tab.plugin_id] ?? 0;
          const outputSrc = nonce > 0 ? `${tab.output_url}?_r=${nonce}` : tab.output_url;
          return (
            <React.Fragment key={tab.plugin_id}>
              <iframe
                title={`${tab.plugin_id}-input`}
                src={tab.input_url}
                style={{ display: i === activeSheetTabIdx && activeTab === "input" ? "block" : "none" }}
              />
              <iframe
                title={`${tab.plugin_id}-output`}
                src={outputSrc}
                style={{ display: i === activeSheetTabIdx && activeTab === "output" ? "block" : "none" }}
              />
            </React.Fragment>
          );
        })}
      </div>

      {isStarting && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <span>套件載入中，請稍候…</span>
        </div>
      )}
      {!isStarting && isExecuting && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <span>執行中…</span>
        </div>
      )}
    </div>
  );
}

// ── App ───────────────────────────────────────────────────

function ExternalToolPanel({ activeTool, isStarting, runtimeStatus }) {
  const ready = !!activeTool?.ready;
  const runtimeOk = runtimeStatus?.labelme_dino?.ok ?? runtimeStatus?.ok;
  const probe = runtimeStatus?.labelme_dino?.probe ?? activeTool?.runtime ?? {};
  return (
    <div className="external-panel">
      <div className="external-panel-main">
        <div className="external-heading">
          {ready ? <CheckCircle2 size={22} /> : <Clock3 size={22} className={isStarting ? "spin" : ""} />}
          <div>
            <h2>{activeTool?.name ?? "External tool"}</h2>
            <p>{isStarting ? "Starting external window..." : ready ? "External window is ready." : "Waiting for external readiness."}</p>
          </div>
        </div>
        <div className="external-status-grid">
          <div>
            <span>Status</span>
            <strong>{ready ? "Ready" : isStarting ? "Starting" : "Running"}</strong>
          </div>
          <div>
            <span>Runtime</span>
            <strong>{runtimeOk ? "OK" : "Check needed"}</strong>
          </div>
          <div>
            <span>PID</span>
            <strong>{activeTool?.pid ?? "-"}</strong>
          </div>
          <div>
            <span>Run ID</span>
            <strong>{activeTool?.run_id ?? "-"}</strong>
          </div>
        </div>
        {probe?.torch && (
          <p className="external-runtime">torch {probe.torch} / cv2 {probe.cv2 ?? "-"} / qt {probe.qt ?? "-"}</p>
        )}
        {activeTool?.log_path && (
          <div className="external-log-path">
            <FileText size={16} />
            <span>{activeTool.log_path}</span>
          </div>
        )}
        {activeTool?.message && <p className="external-message">{activeTool.message}</p>}
      </div>
    </div>
  );
}

function App() {
  const [config, setConfig] = useState(null);
  const [tools, setTools] = useState([]);
  const [selectedToolId, setSelectedToolId] = useState("");
  const [activeTool, setActiveTool] = useState(null);
  const [inputUrl, setInputUrl] = useState("");
  const [outputBaseUrl, setOutputBaseUrl] = useState("");
  const [outputNonce, setOutputNonce] = useState(0);
  const [activeTab, setActiveTab] = useState("input");
  const [isExecuting, setIsExecuting] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [displayImageUrl, setDisplayImageUrl] = useState(null);
  const [status, setStatus] = useState("Ready");
  const [sidecarDown, setSidecarDown] = useState(false);
  const [sidecarRestarting, setSidecarRestarting] = useState(false);
  const [toolError, setToolError] = useState(null);
  const [runtimeStatus, setRuntimeStatus] = useState(null);

  // Sheet-specific state
  const [sheetTabs, setSheetTabs] = useState([]);
  const [activeSheetTabIdx, setActiveSheetTabIdx] = useState(0);
  const [sheetOutputNonces, setSheetOutputNonces] = useState({});
  // Ref so the polling closure always sees the latest sheetTabs without restarting the interval
  const sheetTabsRef = useRef([]);
  useEffect(() => { sheetTabsRef.current = sheetTabs; }, [sheetTabs]);
  // Suppress poller-driven nav after EXECUTE_START / SWITCH_TAB to avoid race condition
  const suppressPollerNavUntilRef = useRef(0);

  useEffect(() => {
    nativeApi.getAppConfig().then(setConfig).catch((err) => {
      cimLog("error", `getAppConfig failed: ${err.message}`);
      setStatus(`Config error: ${err.message}`);
    });
    nativeApi.listTools().then((items) => {
      cimLog("info", `listTools: ${items.map(t => t.tool_id).join(", ")}`);
      setTools(items);
      if (items[0]?.tool_id) setSelectedToolId(items[0].tool_id);
    }).catch((err) => {
      cimLog("error", `listTools failed: ${err.message}`);
      setStatus(`Tool list error: ${err.message}`);
    });
    nativeApi.getRuntimeStatus?.().then(setRuntimeStatus).catch((err) => {
      cimLog("warn", `getRuntimeStatus failed: ${err.message}`);
    });
    if (nativeApi.onSidecarExited) {
      nativeApi.onSidecarExited(({ code, signal }) => {
        cimLog("warn", `sidecar exited code=${code} signal=${signal}`);
        setSidecarDown(true);
        setInputUrl("");
        setOutputBaseUrl("");
        setOutputNonce(0);
        setActiveTool(null);
        setSheetTabs([]);
        setStatus(`Sidecar stopped (code=${code ?? "–"} signal=${signal ?? "–"})`);
      });
    }
    if (nativeApi.onSidecarRestarting) {
      nativeApi.onSidecarRestarting(() => {
        cimLog("info", "sidecar restarting");
        setSidecarRestarting(true);
        setStatus("Restarting engine…");
      });
    }
    if (nativeApi.onSidecarReady) {
      nativeApi.onSidecarReady(() => {
        cimLog("info", "sidecar ready after restart");
        setSidecarDown(false);
        setSidecarRestarting(false);
        setStatus("Ready");
        nativeApi.listTools().then((items) => {
          setTools(items);
          if (items[0]?.tool_id) setSelectedToolId(items[0].tool_id);
        }).catch(() => {});
      });
    }
    if (nativeApi.onSidecarRestartFailed) {
      nativeApi.onSidecarRestartFailed(({ error }) => {
        cimLog("error", `sidecar restart failed: ${error}`);
        setSidecarRestarting(false);
        setStatus(`Engine restart failed: ${error}`);
      });
    }
  }, []);

  // Poll engine every 2 s while a tool is active:
  //  • sheet_tab_mtimes change → switch to that tab's Output
  //  • result_mtime change (regular tool) → reload output iframe + switch to output tab
  //  • process crash → show error banner
  useEffect(() => {
    if (!activeTool || !nativeApi.getToolStatus) return;
    let lastMtime = -1;
    const lastTabMtimes = {};
    const id = setInterval(async () => {
      try {
        const s = await nativeApi.getToolStatus();
        if (!s.active) return;

        if (s.sheet_tab_mtimes) {
          // Sheet tool: per-tab mtime watch
          for (const [pluginId, mtime] of Object.entries(s.sheet_tab_mtimes)) {
            const prev = lastTabMtimes[pluginId] ?? -1;
            if (mtime > 0 && mtime !== prev) {
              lastTabMtimes[pluginId] = mtime;
              const idx = sheetTabsRef.current.findIndex(t => t.plugin_id === pluginId);
              if (idx >= 0) {
                cimLog("info", `sheet tab result changed plugin=${pluginId} → switching to tab ${idx} output`);
                if (Date.now() > suppressPollerNavUntilRef.current) {
                  setActiveSheetTabIdx(idx);
                  setActiveTab("output");
                  setIsExecuting(false);
                }
                // Always reload the output iframe when mtime changes, regardless of suppression
                setSheetOutputNonces(prev => ({ ...prev, [pluginId]: (prev[pluginId] ?? 0) + 1 }));
              }
            }
          }
        } else if (s.category === "external") {
          setActiveTool((prev) => prev ? {
            ...prev,
            pid: s.pid ?? prev.pid,
            ready: s.ready ?? prev.ready,
            run_id: s.run_id ?? prev.run_id,
            log_path: s.log_path ?? prev.log_path,
            started_at: s.started_at ?? prev.started_at,
          } : prev);
          if (!s.input_alive || !s.output_alive) {
            setToolError(`${activeTool.name} has stopped. Please start it again.`);
            setStatus(`${activeTool.name} stopped`);
          }
        } else {
          // Regular tool: heartbeat + result watch
          if (!s.input_alive || !s.output_alive) {
            const layer = !s.input_alive ? "Input" : "Output";
            setToolError(`${layer} process crashed — please Stop and restart the tool`);
            cimLog("warn", `heartbeat: ${layer} process dead for ${s.tool_id}`);
          }
          const mtime = s.result_mtime ?? -1;
          if (mtime > 0 && mtime !== lastMtime) {
            lastMtime = mtime;
            cimLog("info", `result changed mtime=${mtime} → reloading output`);
            setOutputNonce((n) => n + 1);
            setActiveTab("output");
            setIsExecuting(false);
          }
        }
      } catch { /* engine down — handled by onSidecarExited */ }
    }, 2000);
    return () => clearInterval(id);
  }, [activeTool]);

  useEffect(() => {
    function onMessage(event) {
      if (!isProtocolMessage(event.data)) return;
      if (!isAllowedOrigin(event.origin, config?.allowedOrigins ?? ["*"])) return;

      const { type, payload } = event.data;
      cimLog("info", `postMessage: ${type} from ${event.origin}`);
      switch (type) {
        case MessageTypes.CHILD_READY:
          setStatus("Child app ready");
          break;
        case MessageTypes.ROUTE_CHANGED:
          setStatus(`Route: ${payload.path}`);
          break;
        case MessageTypes.EXECUTE_START:
          cimLog("info", "EXECUTE_START");
          setIsExecuting(true);
          suppressPollerNavUntilRef.current = Date.now() + 10000;
          break;
        case MessageTypes.EXECUTE_COMPLETE:
          cimLog("info", `EXECUTE_COMPLETE success=${payload.success} plugin_id=${payload.plugin_id ?? ""} error=${payload.error ?? ""}`);
          setIsExecuting(false);
          if (payload.success) {
            if (payload.plugin_id && sheetTabsRef.current.length > 0) {
              // Sheet tool: switch to the right module tab's Output and reload its iframe
              const idx = sheetTabsRef.current.findIndex(t => t.plugin_id === payload.plugin_id);
              if (idx >= 0) setActiveSheetTabIdx(idx);
              setSheetOutputNonces(prev => ({ ...prev, [payload.plugin_id]: (prev[payload.plugin_id] ?? 0) + 1 }));
            }
            setActiveTab("output");
          } else {
            setStatus(`執行失敗：${payload.error}`);
          }
          break;
        case MessageTypes.SWITCH_TAB: {
          cimLog("info", `SWITCH_TAB plugin_id=${payload.plugin_id} tab=${payload.tab}`);
          suppressPollerNavUntilRef.current = Date.now() + 6000;
          const tabs = sheetTabsRef.current;
          if (tabs.length > 0 && payload.plugin_id) {
            const switchIdx = tabs.findIndex(t => t.plugin_id === payload.plugin_id);
            if (switchIdx >= 0) {
              setActiveSheetTabIdx(switchIdx);
              setActiveTab(payload.tab === "output" ? "output" : "input");
            }
          }
          break;
        }
        case MessageTypes.DISPLAY_UPDATE:
          cimLog("info", `DISPLAY_UPDATE imageUrl=${payload.imageUrl}`);
          setDisplayImageUrl(payload.imageUrl);
          break;
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [config]);

  async function handleStart() {
    const tool = tools.find((t) => t.tool_id === selectedToolId);
    cimLog("info", `startTool: ${selectedToolId}`);
    setStatus(`Starting ${tool?.name ?? selectedToolId}…`);
    setIsStarting(true);
    try {
      const res = await nativeApi.startTool(selectedToolId);
      cimLog("info", `startTool response: category=${res.category} sheet_tabs=${res.sheet_tabs?.length ?? 0}`);
      setInputUrl(res.input_url ?? res.url ?? "");
      setOutputBaseUrl(res.output_url ?? "");
      setOutputNonce(0);
      setActiveTool({
        tool_id: selectedToolId,
        name: tool?.name ?? selectedToolId,
        category: res.category ?? tool?.category,
        pid: res.pid,
        ready: res.ready,
        run_id: res.run_id,
        log_path: res.log_path,
        message: res.message,
        runtime: res.runtime,
      });
      setActiveTab("input");
      setDisplayImageUrl(null);
      setToolError(null);
      setStatus(res.ready ? `${tool?.name ?? selectedToolId} ready` : `${tool?.name ?? selectedToolId} running`);
      nativeApi.getRuntimeStatus?.().then(setRuntimeStatus).catch(() => {});

      if (res.sheet_tabs?.length > 0) {
        setSheetTabs(res.sheet_tabs);
        setActiveSheetTabIdx(0);
      } else {
        setSheetTabs([]);
        setActiveSheetTabIdx(0);
      }
    } catch (err) {
      cimLog("error", `startTool failed: ${err.message}`);
      setStatus(`Failed to start tool: ${err.message}`);
    } finally {
      setIsStarting(false);
    }
  }

  async function handleRestartSidecar() {
    cimLog("info", "manual restart sidecar");
    setSidecarRestarting(true);
    setStatus("Restarting engine…");
    try {
      await nativeApi.restartSidecar();
      setSidecarDown(false);
      setSidecarRestarting(false);
      setStatus("Ready");
      const items = await nativeApi.listTools().catch(() => []);
      if (items.length) { setTools(items); setSelectedToolId(items[0].tool_id); }
    } catch (err) {
      cimLog("error", `manual restart failed: ${err.message}`);
      setSidecarRestarting(false);
      setStatus(`Engine restart failed: ${err.message}`);
    }
  }

  async function handleStop() {
    cimLog("info", `stopTool: ${activeTool?.tool_id ?? "unknown"}`);
    try { await nativeApi.stopTool(); } catch { /* best-effort */ }
    setInputUrl("");
    setOutputBaseUrl("");
    setOutputNonce(0);
    setActiveTool(null);
    setActiveTab("input");
    setIsExecuting(false);
    setDisplayImageUrl(null);
    setToolError(null);
    setSheetTabs([]);
    setActiveSheetTabIdx(0);
    setStatus("Tool stopped");
  }

  const outputUrl = outputBaseUrl
    ? `${outputBaseUrl}${outputNonce > 0 ? `?_r=${outputNonce}` : ""}`
    : "";

  return (
    <div className="workspace">
      {sidecarDown && (
        <SidecarError
          restarting={sidecarRestarting}
          onRestart={!sidecarRestarting ? handleRestartSidecar : null}
        />
      )}
      {toolError && <ToolError message={toolError} />}
      <TopBar
        tools={tools}
        selectedToolId={selectedToolId}
        onToolChange={setSelectedToolId}
        activeTool={activeTool}
        onStart={handleStart}
        onStop={handleStop}
        status={status}
        sidecarDown={sidecarDown}
        devMode={config?.devMode ?? true}
      />
      <div className="workspace-body">
        {activeTool?.category === "external" ? (
          <ExternalToolPanel activeTool={activeTool} isStarting={isStarting} runtimeStatus={runtimeStatus} />
        ) : sheetTabs.length > 0 ? (
          <SheetLayout
            sheetTabs={sheetTabs}
            activeSheetTabIdx={activeSheetTabIdx}
            onSheetTabChange={(i) => { setActiveSheetTabIdx(i); setActiveTab("input"); }}
            activeTab={activeTab}
            onTabChange={setActiveTab}
            isExecuting={isExecuting}
            isStarting={isStarting}
            sheetOutputNonces={sheetOutputNonces}
          />
        ) : (
          <LeftPanel
            activeTab={activeTab}
            onTabChange={setActiveTab}
            inputUrl={inputUrl}
            outputUrl={outputUrl}
            isExecuting={isExecuting}
            isStarting={isStarting}
          />
        )}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
