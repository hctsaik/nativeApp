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
  async externalOpenLabelingTool() { return {}; },
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

// ── Top-level menu groups (display) ───────────────────────
// A tool's menu group is decoupled from its runtime category: 'sheet' tools are
// multi-tab, 'app' tools are a single iframe, 'management' is the admin center —
// but how they're grouped/labeled in the portal menu is a product decision set
// here. Runtime routing (SheetLayout vs AppPanel) still keys off the real
// category and is unaffected by this grouping.
const MENU_GROUP_LABELS = {
  common:     "共同應用程式",
  dedicated:  "專屬應用程式",
  management: "CIM 管理中心",
};
const MENU_GROUP_ORDER = ["common", "dedicated", "management"];

// 影像標註 (sheet-annotation) runs as a multi-tab sheet, but is a platform-wide
// shared capability, so it sits under 共同應用程式 next to AI4BI. List any other
// "common but technically a sheet" tool here.
const COMMON_GROUP_TOOL_IDS = new Set(["app-ai4bi", "sheet-annotation"]);

// Map a tool to its top-level menu group, or null to hide it from the menu
// (module / external tools are used via sheets, not selected directly).
function menuGroupFor(tool) {
  if (tool.category === "management") return "management";
  if (COMMON_GROUP_TOOL_IDS.has(tool.tool_id)) return "common";
  if (tool.category === "app") return "common";       // apps are 共同 by default
  if (tool.category === "sheet") return "dedicated";  // sheets = 專屬 (domain-specific) packages
  return null;
}

function groupToolsByMenu(tools) {
  const groups = {};
  for (const t of tools) {
    const g = menuGroupFor(t);
    if (!g) continue;
    (groups[g] ??= []).push(t);
  }
  return groups;
}

// ── Sub-components ────────────────────────────────────────

function SidecarError({ restarting, onRestart }) {
  if (restarting) {
    return (
      <div className="sidecar-error sidecar-restarting">
        <RefreshCw size={16} className="spin" />
        本地引擎重新啟動中…
      </div>
    );
  }
  return (
    <div className="sidecar-error">
      <AlertTriangle size={16} />
      本地引擎已停止。
      {onRestart && (
        <button className="btn-restart" onClick={onRestart}>
          <RefreshCw size={14} /> 重新啟動
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

// ── Streamlit 錯誤彈窗攔截 ────────────────────────────────
// Streamlit 在程序崩潰或重連時，會在 iframe 內部彈出英文錯誤 Dialog。
// 由於 iframe 使用 localhost 同源，可注入 MutationObserver 攔截並中文化。

const STREAMLIT_ERROR_MAP = [
  {
    from: "Is Streamlit still running? If you accidentally stopped Streamlit, just restart it in your terminal:",
    to: "工具程序已停止回應。請按下「Stop」後重新啟動工具。",
  },
  {
    from: "streamlit run yourscript.py",
    to: "",
  },
  {
    from: "Streamlit server is not responding. Are you connected to the internet?",
    to: "工具伺服器未回應，請確認工具程序正常運行。",
  },
  {
    from: "Cannot connect to Streamlit",
    to: "無法連接到工具程序，請重新啟動工具。",
  },
  {
    from: "Connection timed out.",
    to: "連線逾時，工具程序可能已停止。",
  },
  {
    from: "Connection failed",
    to: "連線失敗，請重新啟動工具。",
  },
  // Streamlit 漢堡選單 → 管理快取對話框
  {
    from: "Clear cache",
    to: "清除快取",
  },
  {
    from: "Are you sure you want to clear the app's cache? This will remove all cached entries.",
    to: "確定要清除應用程式快取嗎？所有快取資料將會被移除。",
  },
  {
    from: "Clear All",
    to: "全部清除",
  },
  {
    from: "Cancel",
    to: "取消",
  },
];

function translateStreamlitErrors(doc) {
  if (!doc) return;
  // Streamlit 的連線錯誤 Dialog 會用 BaseUI Modal 渲染，
  // 內容放在 <p>、<div> 文字節點。用 TreeWalker 掃所有文字節點效率最高。
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT, null);
  let node;
  while ((node = walker.nextNode())) {
    const orig = node.nodeValue;
    if (!orig) continue;
    for (const { from, to } of STREAMLIT_ERROR_MAP) {
      if (orig.includes(from)) {
        node.nodeValue = to ? orig.replace(from, to) : "";
      }
    }
  }
}

function injectStreamlitErrorTranslator(iframeEl) {
  if (!iframeEl) return null;
  let observer = null;
  function setup() {
    try {
      const doc = iframeEl.contentDocument;
      if (!doc || !doc.body) return;
      // 立即掃一次（避免 load 後才注入的情況）
      translateStreamlitErrors(doc);
      // 監聽後續 DOM 變化（Streamlit 動態注入 Modal）
      observer = new MutationObserver(() => translateStreamlitErrors(doc));
      observer.observe(doc.body, { childList: true, subtree: true, characterData: true });
    } catch {
      // cross-origin guard — 若 origin 不允許則靜默略過
    }
  }
  iframeEl.addEventListener("load", setup);
  // 若已載入完成則立即執行
  if (iframeEl.contentDocument?.readyState === "complete") setup();
  return () => {
    iframeEl.removeEventListener("load", setup);
    observer?.disconnect();
  };
}


function TopBar({ tools, selectedToolId, onToolChange, activeTool, onStart, onStop, status, sidecarDown, devMode, role, roles, onSetRole }) {
  const visibleOrder = MENU_GROUP_ORDER;

  return (
    <header className="toolbar">
      <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
        <span className="top-bar-brand">CIM Platform</span>
        <span className={`mode-badge ${devMode ? "mode-badge-dev" : "mode-badge-prod"}`}>
          {devMode ? "DEV" : "PROD"}
        </span>
        {role && (
          devMode && onSetRole ? (
            <select
              className="role-select"
              value={role}
              onChange={(e) => onSetRole(e.target.value)}
              title="切換目前角色（DEV）：可即時看到 RBAC 對工具可見性/執行權限的效果"
            >
              {(roles ?? [role]).map(r => <option key={r} value={r}>角色：{r}</option>)}
            </select>
          ) : (
            <span className="mode-badge" title="目前 RBAC 角色">角色：{role}</span>
          )
        )}
        <div className="toolbar-title">
          <p>{status}</p>
        </div>
      </div>
      <div className="actions">
        <div className="toolSelectGroup">
          <label className="toolSelectLabel">工作流程</label>
          <select
            className="toolSelect"
            value={selectedToolId}
            onChange={(e) => onToolChange(e.target.value)}
            disabled={sidecarDown || !!activeTool}
          >
            {(() => {
              const groups = groupToolsByMenu(tools);
              return visibleOrder
                .filter(g => groups[g]?.length)
                .map(g => (
                  <optgroup key={g} label={MENU_GROUP_LABELS[g]}>
                    {groups[g].map(t => (
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
            Start
          </button>
        )}
      </div>
    </header>
  );
}


// ── Regular (module) panel ────────────────────────────────

function LeftPanel({ activeTab, onTabChange, inputUrl, outputUrl, isExecuting, isStarting }) {
  const inputIframeRef = useRef(null);
  const outputIframeRef = useRef(null);

  // 注入 Streamlit 錯誤訊息中文化攔截器
  useEffect(() => {
    const cleanupInput = injectStreamlitErrorTranslator(inputIframeRef.current);
    const cleanupOutput = injectStreamlitErrorTranslator(outputIframeRef.current);
    return () => { cleanupInput?.(); cleanupOutput?.(); };
  }, [inputUrl, outputUrl]);

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
          ? <iframe ref={inputIframeRef} title="Input" src={inputUrl} style={{ display: activeTab === "input" ? "block" : "none" }} />
          : activeTab === "input" && <div className="tab-empty">請先選擇功能並按下 Start Tool</div>
        }
        {outputUrl
          ? <iframe ref={outputIframeRef} title="Output" src={outputUrl} style={{ display: activeTab === "output" ? "block" : "none" }} />
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


// ── App panel ─────────────────────────────────────────────
// A self-contained external Streamlit app (category 'app', e.g. AI4BI):
// one full-height iframe, no Input/Output split — the app owns its own layout.
function AppPanel({ url, isStarting }) {
  const iframeRef = useRef(null);
  useEffect(() => {
    const cleanup = injectStreamlitErrorTranslator(iframeRef.current);
    return () => cleanup?.();
  }, [url]);
  return (
    <div className="left-panel">
      <div className="tab-content">
        {url
          ? <iframe ref={iframeRef} title="App" src={url} style={{ display: "block" }} />
          : <div className="tab-empty">應用程式準備中，請按下 Start Tool</div>}
      </div>
      {isStarting && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <span>應用程式載入中，請稍候…</span>
        </div>
      )}
    </div>
  );
}


// ── Sheet panel ───────────────────────────────────────────
// Each sheet tab has its own dedicated input + output Streamlit process.
// All iframes are kept mounted (display:none when inactive) to preserve session state.

// SheetIframe：每個 sheet tab 的 iframe，掛載 Streamlit 錯誤訊息攔截器
function SheetIframe({ title, src, style }) {
  const iframeRef = useRef(null);
  useEffect(() => {
    const cleanup = injectStreamlitErrorTranslator(iframeRef.current);
    return () => cleanup?.();
  }, [src]);
  return <iframe ref={iframeRef} title={title} src={src} style={style} />;
}

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
}) {
  const selectedSheetTab = sheetTabs[activeSheetTabIdx];
  const activeTabStarting = selectedSheetTab ? tabStartingSet.has(selectedSheetTab.plugin_id) : false;

  return (
    <div className="left-panel">
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
      </div>

      <>
        <div className="tab-bar">
          <button className={`tab${activeTab === "input" ? " active" : ""}`} onClick={() => onTabChange("input")}>
            Input
          </button>
          <button className={`tab${activeTab === "output" ? " active" : ""}`} onClick={() => onTabChange("output")}>
            Output
          </button>
        </div>

        <div className="tab-content">
          {sheetTabs.map((tab, i) => {
            const isActive = i === activeSheetTabIdx;
            const hasBeenVisited = visitedTabIndices.has(i);
            const nonce = sheetOutputNonces[tab.plugin_id] ?? 0;
            const outputSrc = nonce > 0 ? `${tab.output_url}?_r=${nonce}` : tab.output_url;
            if (!hasBeenVisited || !tab.ready) return null;
            return (
              <React.Fragment key={tab.plugin_id}>
                <SheetIframe
                  title={`${tab.plugin_id}-input`}
                  src={tab.input_url}
                  style={{ display: isActive && activeTab === "input" ? "block" : "none" }}
                />
                <SheetIframe
                  title={`${tab.plugin_id}-output`}
                  src={outputSrc}
                  style={{ display: isActive && activeTab === "output" ? "block" : "none" }}
                />
              </React.Fragment>
            );
          })}
        </div>
      </>

      {isStarting && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <span>套件載入中，請稍候…</span>
        </div>
      )}
      {!isStarting && activeTabStarting && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <span>頁籤啟動中，請稍候…</span>
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

// ── Preview Modal ─────────────────────────────────────────

function PreviewModal({ url, toolName, onClose }) {
  return (
    <div className="preview-modal-overlay">
      <div className="preview-modal-header">
        <span className="preview-modal-title">{toolName}</span>
        <span className="preview-modal-badge">Read-only Preview</span>
        <button className="preview-modal-close" onClick={onClose} title="Close preview">✕</button>
      </div>
      <iframe className="preview-modal-iframe" src={url} title="Module Preview" />
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
  const [role, setRole] = useState("admin");
  const [roles, setRoles] = useState(["admin", "operator", "viewer"]);
  const [toolError, setToolError] = useState(null);
  const [runtimeStatus, setRuntimeStatus] = useState(null);
  const [previewModal, setPreviewModal] = useState(null); // { url, toolName }

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
  // Track active tool so EXECUTE_COMPLETE closure can log sheet context
  const selectedToolIdRef = useRef("");
  useEffect(() => { selectedToolIdRef.current = selectedToolId; }, [selectedToolId]);
  // Latest handleStart, callable from the (config-scoped) message listener without
  // staleness. handleStart is a hoisted function declaration, so it's the current
  // render's instance here; this assignment runs every render.
  const handleStartRef = useRef(null);
  handleStartRef.current = handleStart;


  // Fetch the current RBAC role once the sidecar URL is known (proves RBAC live).
  useEffect(() => {
    if (!config?.sidecarControlUrl) return;
    fetch(`${config.sidecarControlUrl}/whoami`)
      .then(r => r.json())
      .then(d => { if (d?.role) setRole(d.role); if (Array.isArray(d?.roles)) setRoles(d.roles); })
      .catch(() => {});
  }, [config?.sidecarControlUrl]);

  useEffect(() => {
    nativeApi.getAppConfig().then(setConfig).catch((err) => {
      cimLog("error", `getAppConfig failed: ${err.message}`);
      setStatus(`Config error: ${err.message}`);
    });
    nativeApi.listTools().then((items) => {
      cimLog("info", `listTools: ${items.map(t => t.tool_id).join(", ")}`);
      setTools(items);
      // 預設選第一個 Sheet；找不到才 fallback 到第一個工具
      const first = items.find(t => t.category === "sheet") ?? items[0];
      if (first?.tool_id) setSelectedToolId(first.tool_id);
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
            setToolError(`⚠️ ${activeTool.name} 已停止，請重新啟動工具`);
            setStatus(`${activeTool.name} 已停止`);
          }
        } else {
          // Regular tool: heartbeat + result watch
          if (!s.input_alive || !s.output_alive) {
            const layer = !s.input_alive ? "Input（輸入）" : "Output（輸出）";
            setToolError(`⚠️ ${layer} 程序已停止 — 請按下 Stop 後重新啟動工具`);
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
      const { action, imageUrl, metadata, tool } = data;
      if (!imageUrl) return;
      cimLog("info", `[ext-bridge] action=${action} url=${imageUrl}`);

      if (action === "open_xanylabeling") {
        nativeApi.externalOpenXanylabeling(imageUrl, metadata ?? {})
          .then(() => setStatus("xanylabeling 已開啟"))
          .catch(err => setStatus(`xanylabeling 啟動失敗: ${err.message}`));
      } else if (action === "open_labeling_tool") {
        const selectedTool = tool || metadata?.tool || "x-anylabeling";
        nativeApi.externalOpenLabelingTool(selectedTool, imageUrl, metadata ?? {})
          .then(() => setStatus(`${selectedTool} launched`))
          .catch(err => setStatus(`${selectedTool} launch failed: ${err.message}`));
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
          if (payload.plugin_id && config?.sidecarControlUrl) {
            const activeToolId = selectedToolIdRef.current;
            const sheetId = activeToolId?.startsWith("sheet-") ? activeToolId.slice(6) : null;
            fetch(`${config.sidecarControlUrl}/tools/runs/log`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ plugin_id: payload.plugin_id, sheet_id: sheetId, success: !!payload.success, actor: "user" }),
            }).catch(() => {});
          }
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
        case MessageTypes.OPEN_PREVIEW:
          cimLog("info", `OPEN_PREVIEW url=${payload.url} toolName=${payload.toolName}`);
          setPreviewModal({ url: payload.url, toolName: payload.toolName });
          break;
        case MessageTypes.OPEN_TOOL: {
          // A tool iframe (e.g. VisualLatent) asks to switch the active tool —
          // same as picking it from the 工作流程 dropdown and pressing 啟動.
          cimLog("info", `OPEN_TOOL toolId=${payload.toolId}`);
          if (payload.toolId) {
            suppressPollerNavUntilRef.current = Date.now() + 12000;
            setSelectedToolId(payload.toolId);
            handleStartRef.current?.(payload.toolId);
          }
          break;
        }
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
    const tab = sheetTabsRef.current[i];
    if (!tab) return;
    setActiveSheetTabIdx(i);
    setActiveTab("input");
    setVisitedTabIndices(prev => new Set(prev).add(i));
    if (!tab.ready) {
      await ensureTabStarted(tab.plugin_id);
    }
  }

  async function handleClosePreview() {
    setPreviewModal(null);
    if (config?.sidecarControlUrl) {
      try { await fetch(`${config.sidecarControlUrl}/tools/preview/stop`, { method: "DELETE" }); } catch {}
    }
  }

  async function handleStart(toolIdArg) {
    const startId = (typeof toolIdArg === "string" && toolIdArg) ? toolIdArg : selectedToolId;
    const tool = tools.find((t) => t.tool_id === startId);
    cimLog("info", `startTool: ${startId}`);
    setStatus(`Starting ${tool?.name ?? startId}…`);
    setIsStarting(true);
    try {
      const res = await nativeApi.startTool(startId);
      cimLog("info", `startTool response: category=${res.category} sheet_tabs=${res.sheet_tabs?.length ?? 0}`);
      setInputUrl(res.input_url ?? res.url ?? "");
      setOutputBaseUrl(res.output_url ?? "");
      setOutputNonce(0);
      setActiveTool({
        tool_id: startId,
        name: tool?.name ?? startId,
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
      setStatus(res.ready ? `${tool?.name ?? startId} ready` : `${tool?.name ?? startId} running`);
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

  async function handleSetRole(r) {
    // DEV role switch so an admin can see RBAC take effect (operator/viewer see
    // fewer tools / cannot execute). PROD identity comes from SSO/IdP.
    if (!config?.sidecarControlUrl || r === role) return;
    try {
      await fetch(`${config.sidecarControlUrl}/set-role`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: r }),
      });
      setRole(r);
      const items = await nativeApi.listTools().catch(() => []);
      if (items.length) setTools(items);
      setStatus(`角色已切換為 ${r}`);
    } catch (e) { cimLog("error", `set-role failed: ${e.message}`); }
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

  const outputUrl = outputBaseUrl
    ? `${outputBaseUrl}${outputNonce > 0 ? `?_r=${outputNonce}` : ""}`
    : "";

  return (
    <div className="workspace">
      {previewModal && (
        <PreviewModal
          url={previewModal.url}
          toolName={previewModal.toolName}
          onClose={handleClosePreview}
        />
      )}
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
        role={role}
        roles={roles}
        onSetRole={handleSetRole}
      />
      <div className="workspace-body">
        {activeTool?.category === "external" ? (
          <ExternalToolPanel activeTool={activeTool} isStarting={isStarting} runtimeStatus={runtimeStatus} />
        ) : activeTool?.category === "app" ? (
          <AppPanel url={inputUrl} isStarting={isStarting} />
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
