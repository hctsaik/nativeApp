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
  async startSheetTab() {
    return { input_url: "", output_url: "", input_port: 0, output_port: 0, ready: false };
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
  async externalOpenXanylabeling() { return {}; },
  async externalQueueImage() { return { queue_size: 0 }; },
  async externalGetQueue() { return { items: [], count: 0 }; },
  async externalDequeue() { return {}; },
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

// ── Vision DIY help modal ─────────────────────────────────────────────────────

function VisionDiyHelpModal({ onClose }) {
  return (
    <div className="vd-overlay" onClick={onClose}>
      <div className="vd-modal" onClick={e => e.stopPropagation()}>
        <button className="vd-close" onClick={onClose} title="關閉">✕</button>
        <h2 className="vd-title">🔭 Vision DIY 1.0 — 整合指南</h2>
        <p className="vd-lead">將外部 React / Web 應用透過 iframe 嵌入 CIM Platform，並讓它能直接觸發本地標注工具。</p>

        <h3>1. 設定 URL</h3>
        <p>點擊 TopBar 的 <strong>✏️</strong> 圖示，輸入你的 HTTPS 應用網址後按確認。網址會存在 localStorage，重開後自動載入。</p>

        <h3>2. 在你的 React App 裡傳送指令</h3>
        <p>使用 <code>window.parent.postMessage</code>，格式如下：</p>

        <pre className="vd-code">{`// ① 直接開啟 X-AnyLabeling 標記指定圖片
window.parent.postMessage({
  cim: "v1",
  action: "open_xanylabeling",
  imageUrl: "https://your-server.com/images/sample.jpg"
}, "*");

// ② 將圖片加入標注佇列（批次處理）
window.parent.postMessage({
  cim: "v1",
  action: "queue_image",
  imageUrl: "https://your-server.com/images/sample.jpg",
  metadata: { label: "defect", source: "inspection" }  // 選填
}, "*");`}</pre>

        <h3>3. 執行流程</h3>
        <table className="vd-table">
          <thead><tr><th>Action</th><th>Platform 做了什麼</th></tr></thead>
          <tbody>
            <tr>
              <td><code>open_xanylabeling</code></td>
              <td>Engine 從 URL 下載圖片 → 存至本機 <code>external-queue/</code> → 直接啟動 X-AnyLabeling 並載入該圖，標注結果（.json）存在同目錄</td>
            </tr>
            <tr>
              <td><code>queue_image</code></td>
              <td>Engine 下載圖片 → 加入記憶體佇列 → TopBar 顯示紅色計數徽章，點 🗑️ 清空</td>
            </tr>
          </tbody>
        </table>

        <h3>4. 安全性注意</h3>
        <ul>
          <li>只支援 <strong>HTTPS</strong> 圖片 URL（Engine 用 urllib 下載，需可公開存取或帶 Token）</li>
          <li>你的 k8s App 需允許被 iframe 嵌入（移除 <code>X-Frame-Options: DENY</code> 或設 <code>frame-ancestors 'self' *</code>）</li>
          <li>postMessage target 設 <code>"*"</code> 即可，Platform 端不檢查來源</li>
        </ul>

        <h3>5. 本機存放路徑</h3>
        <pre className="vd-code">{`{CIM_LOG_DIR}/external-queue/          ← 下載的圖片
{CIM_LOG_DIR}/xanylabeling_state/external/  ← xanylabeling GUI 狀態`}</pre>

        <p className="vd-footer">CIM Platform · Vision DIY 1.0 Bridge Protocol v1</p>
      </div>
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

const VISION_DIY_IDX = -1;  // sentinel: Vision DIY tab is active

function SheetLayout({
  sheetTabs,
  activeSheetTabIdx,
  onSheetTabChange,
  activeTab,
  onTabChange,
  isExecuting,
  isStarting,
  sheetOutputNonces = {},
  tabStartingSet = new Set(),
  visitedTabIndices = new Set([0]),
  webAppUrl = "",
  queueCount = 0,
}) {
  const visionDiyActive = activeSheetTabIdx === VISION_DIY_IDX;
  const selectedSheetTab = visionDiyActive ? null : sheetTabs[activeSheetTabIdx];
  const activeTabStarting = selectedSheetTab ? tabStartingSet.has(selectedSheetTab.plugin_id) : false;

  return (
    <div className="left-panel">
      {/* Sheet module tabs + Vision DIY tab */}
      <div className="sheet-module-bar">
        {sheetTabs.map((tab, i) => {
          const isActive = i === activeSheetTabIdx;
          const isStartingTab = tabStartingSet.has(tab.plugin_id);
          const isPending = !tab.ready && !isStartingTab;
          return (
            <button
              key={tab.plugin_id}
              className={`sheet-module-tab${isActive ? " active" : ""}${isPending ? " tab-pending" : ""}`}
              onClick={() => onSheetTabChange(i)}
              title={isStartingTab ? "Starting tab" : isPending ? "Starts when selected" : tab.label}
            >
              {tab.label}
              {isStartingTab && <span className="tab-loading-dot" />}
            </button>
          );
        })}
        <button
          className={`sheet-module-tab vd-sheet-tab${visionDiyActive ? " active" : ""}`}
          onClick={() => onSheetTabChange(VISION_DIY_IDX)}
          title="Vision DIY 1.0 — 外部 Web App"
        >
          🔭 Vision DIY 1.0
          {queueCount > 0 && <span className="queue-badge">{queueCount}</span>}
        </button>
      </div>

      {visionDiyActive ? (
        /* Vision DIY: 外部 iframe，不顯示 Input/Output sub-tabs */
        <div className="tab-content">
          {webAppUrl
            ? <iframe title="Vision DIY" src={webAppUrl} className="web-app-iframe" allow="camera; microphone" />
            : <div className="tab-empty">請在 TopBar 點擊 ✏️ 設定 Vision DIY URL</div>
          }
          {queueCount > 0 && (
            <div className="vd-queue-overlay">📥 {queueCount} 張圖片已加入標注佇列</div>
          )}
        </div>
      ) : (
        <>
          {/* Input / Output sub-tabs */}
          <div className="tab-bar">
            <button className={`tab${activeTab === "input" ? " active" : ""}`} onClick={() => onTabChange("input")}>
              Input
            </button>
            <button className={`tab${activeTab === "output" ? " active" : ""}`} onClick={() => onTabChange("output")}>
              Output
            </button>
          </div>

          {/* Iframes: mount only visited, ready tabs so startup stays responsive. */}
          <div className="tab-content">
            {sheetTabs.map((tab, i) => {
              const isActive = i === activeSheetTabIdx;
              const hasBeenVisited = visitedTabIndices.has(i);
              const nonce = sheetOutputNonces[tab.plugin_id] ?? 0;
              const outputSrc = nonce > 0 ? `${tab.output_url}?_r=${nonce}` : tab.output_url;
              if (!hasBeenVisited || !tab.ready) return null;
              return (
                <React.Fragment key={tab.plugin_id}>
                  <iframe
                    title={`${tab.plugin_id}-input`}
                    src={tab.input_url}
                    style={{ display: isActive && activeTab === "input" ? "block" : "none" }}
                  />
                  <iframe
                    title={`${tab.plugin_id}-output`}
                    src={outputSrc}
                    style={{ display: isActive && activeTab === "output" ? "block" : "none" }}
                  />
                </React.Fragment>
              );
            })}
          </div>
        </>
      )}

      {isStarting && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <span>套件載入中，請稍候…</span>
        </div>
      )}
      {!isStarting && activeTabStarting && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <span>Starting tab...</span>
        </div>
      )}
      {!isStarting && !activeTabStarting && isExecuting && (
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

// ── External Web App (iframe bridge) ─────────────────────────────────────────


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
  const [tabStartingSet, setTabStartingSet] = useState(new Set());
  const [visitedTabIndices, setVisitedTabIndices] = useState(new Set([0]));
  // Ref so the polling closure always sees the latest sheetTabs without restarting the interval
  const sheetTabsRef = useRef([]);
  useEffect(() => { sheetTabsRef.current = sheetTabs; }, [sheetTabs]);
  // Suppress poller-driven nav after EXECUTE_START / SWITCH_TAB to avoid race condition
  const suppressPollerNavUntilRef = useRef(0);

  // External Web App state
  const [webAppUrl, setWebAppUrl] = useState(() => localStorage.getItem("cim_web_app_url") ?? "");

  const [extQueue, setExtQueue] = useState([]);
  useEffect(() => { if (webAppUrl) localStorage.setItem("cim_web_app_url", webAppUrl); }, [webAppUrl]);

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
        setTabStartingSet(new Set());
        setVisitedTabIndices(new Set([0]));
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
          if (s.sheet_tab_ready) {
            setSheetTabs(prev => {
              let changed = false;
              const next = prev.map(t => {
                if (t.ready) return t;
                const nowReady = Boolean(s.sheet_tab_ready[t.plugin_id]);
                if (!nowReady) return t;
                const urls = s.sheet_tab_urls?.[t.plugin_id] ?? {};
                changed = true;
                return {
                  ...t,
                  ready: true,
                  input_url: urls.input_url || t.input_url,
                  output_url: urls.output_url || t.output_url,
                };
              });
              return changed ? next : prev;
            });
          }
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
                  setVisitedTabIndices(prev => new Set(prev).add(idx));
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

  // ── External Web App bridge ───────────────────────────────────────────────
  useEffect(() => {
    function onExtMessage(event) {
      const data = event.data;
      if (!data || data.cim !== "v1") return;
      const { action, imageUrl, metadata } = data;
      if (!imageUrl) return;
      cimLog("info", `[ext-bridge] action=${action} url=${imageUrl}`);

      if (action === "open_xanylabeling") {
        nativeApi.externalOpenXanylabeling(imageUrl, metadata ?? {})
          .then(() => setStatus("xanylabeling 已開啟"))
          .catch(err => setStatus(`xanylabeling 啟動失敗: ${err.message}`));
      } else if (action === "queue_image") {
        nativeApi.externalQueueImage(imageUrl, metadata ?? {})
          .then(res => {
            setExtQueue(prev => [...prev, { id: res.id, local_path: res.local_path, original_url: imageUrl }]);
            setStatus(`圖片已加入標注佇列（共 ${res.queue_size} 張）`);
          })
          .catch(err => setStatus(`圖片佇列失敗: ${err.message}`));
      }
    }
    window.addEventListener("message", onExtMessage);
    return () => window.removeEventListener("message", onExtMessage);
  }, []);

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
              if (idx >= 0) {
                setActiveSheetTabIdx(idx);
                setVisitedTabIndices(prev => new Set(prev).add(idx));
                setSheetOutputNonces(prev => ({ ...prev, [payload.plugin_id]: (prev[payload.plugin_id] ?? 0) + 1 }));
                ensureTabStarted(payload.plugin_id);
              }
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
              setVisitedTabIndices(prev => new Set(prev).add(switchIdx));
              setActiveTab(payload.tab === "output" ? "output" : "input");
              ensureTabStarted(payload.plugin_id);
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

  async function ensureTabStarted(pluginId) {
    const tab = sheetTabsRef.current.find(t => t.plugin_id === pluginId);
    if (!tab || tab.ready || tabStartingSet.has(pluginId)) return;
    setTabStartingSet(prev => new Set(prev).add(pluginId));
    try {
      const res = await nativeApi.startSheetTab(pluginId);
      setSheetTabs(prev => prev.map(t =>
        t.plugin_id === pluginId
          ? { ...t, input_url: res.input_url, output_url: res.output_url, ready: true }
          : t
      ));
    } catch (err) {
      cimLog("error", `startSheetTab(${pluginId}) failed: ${err.message}`);
    } finally {
      setTabStartingSet(prev => {
        const next = new Set(prev);
        next.delete(pluginId);
        return next;
      });
    }
  }

  async function handleSheetTabChange(i) {
    if (i === VISION_DIY_IDX) {
      setActiveSheetTabIdx(VISION_DIY_IDX);
      return;
    }
    const tab = sheetTabsRef.current[i];
    if (!tab) return;
    setActiveSheetTabIdx(i);
    setActiveTab("input");
    setVisitedTabIndices(prev => new Set(prev).add(i));
    if (!tab.ready) {
      await ensureTabStarted(tab.plugin_id);
    }
  }

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
        setVisitedTabIndices(new Set([0]));
        setTabStartingSet(new Set());
      } else {
        setSheetTabs([]);
        setActiveSheetTabIdx(0);
        setVisitedTabIndices(new Set([0]));
        setTabStartingSet(new Set());
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
    setVisitedTabIndices(new Set([0]));
    setTabStartingSet(new Set());
    setStatus("Tool stopped");
  }

  async function handleClearQueue() {
    for (const item of extQueue) {
      try { await nativeApi.externalDequeue(item.id); } catch { /* best-effort */ }
    }
    setExtQueue([]);
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
            onSheetTabChange={handleSheetTabChange}
            activeTab={activeTab}
            onTabChange={setActiveTab}
            isExecuting={isExecuting}
            isStarting={isStarting}
            sheetOutputNonces={sheetOutputNonces}
            tabStartingSet={tabStartingSet}
            visitedTabIndices={visitedTabIndices}
            webAppUrl={webAppUrl}
            queueCount={extQueue.length}
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
