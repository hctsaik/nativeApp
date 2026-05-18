# 設計：Portal Workspace 版面

## 一、版面結構

### 整體 Grid

```
.shell（移除左側 sidebar，改為單欄）
  └── .workspace
        ├── .top-bar          ← 原 toolbar，保留所有功能
        ├── .sidecar-error    ← 不變
        ├── .pathbar          ← 不變
        └── .workspace-body   ← 新：左右分割
              ├── .left-panel ← 新：Input/Output tabs
              └── .right-panel← 新：Display Area
```

**分割比例：** left 38% / right 62%（桌面版）

---

## 二、Top Bar 變更

移除：
- 整個左側 `<aside class="sidebar">` 元件（含 Brand、mode 按鈕）
- `activeMode` state 與相關邏輯

保留：
- 功能下拉（`<select>`）
- Choose File 按鈕
- Start Tool / Stop Tool 按鈕

新增：
- Brand 文字移入 Top Bar 左側（`<span class="brand">CIM Platform</span>`）
- 工具狀態說明文字（`status`）維持在 Top Bar

---

## 三、Left Panel — Input / Output 頁籤

### Tab 切換控制

```
.left-panel
  ├── .tab-bar
  │     ├── <button class="tab [active]">Input</button>
  │     └── <button class="tab [active]">Output</button>
  └── .tab-content
        └── (iframe 或 empty state)
```

React state：`activeTab: "input" | "output"`（預設 "input"）

### Input Tab 內容
- 工具已啟動且有 URL → `<iframe src={inputUrl} />`
- 工具未啟動 → Empty state：「請先選擇功能並按下 Start Tool」

### Output Tab 內容
- 執行完成後 → `<iframe src={outputUrl} />`
- 執行前 → Empty state：「尚未執行，請在 Input 頁籤完成輸入」

### URL 邏輯（Streamlit 模組工具）

每個模組工具啟動時，sidecar 同時啟動**兩個獨立的 Streamlit process**：

```
inputUrl  = http://127.0.0.1:{input_port}   ← 跑 {module_id}_input.py
outputUrl = http://127.0.0.1:{output_port}  ← 跑 {module_id}_output.py
```

`ToolStartResponse` 由原本的 `{ url, port }` 改為 `{ input_url, output_url, input_port, output_port }`。

### URL 邏輯（React micro-frontend）

```js
inputUrl  = toolUrl        // 或 enterpriseAppUrl（保持不變）
outputUrl = toolUrl        // 同上，由 React app 自己處理 Input/Output 狀態
```

---

## 四、Right Panel — Display Area

### 顯示邏輯

| 狀態 | Right Panel 顯示 |
|------|-----------------|
| 未啟動工具 | Empty（灰字提示） |
| Input tab + 有選取路徑 | 選取影像的 `<img>` 預覽 |
| Input tab + 無選取路徑 | Empty（灰字：「選擇影像以預覽」） |
| Output tab + 執行完成 | 處理後影像（由 DISPLAY_UPDATE 訊息帶入 URL） |
| Output tab + 尚未執行 | Empty（灰字：「執行後結果將顯示於此」） |

### 影像預覽（Input tab）

```js
// selectedPaths[0] 用 file:// 協議載入
<img src={`file://${selectedPaths[0]}`} className="display-image" />
```

### 處理後影像（Output tab）

由子 iframe 透過 `DISPLAY_UPDATE` 訊息送入：

```js
// React state
const [displayImageUrl, setDisplayImageUrl] = useState(null);

// 監聽訊息
if (event.data.type === MessageTypes.DISPLAY_UPDATE) {
  setDisplayImageUrl(event.data.payload.imageUrl);
}
```

---

## 五、新增 shared-protocol MessageTypes

在 `packages/shared-protocol/src/index.js` 新增三個 MessageType：

```js
export const MessageTypes = Object.freeze({
  // 既有
  CHILD_READY:    "CHILD_READY",
  AUTH_TOKEN:     "AUTH_TOKEN",
  ROUTE_CHANGED:  "ROUTE_CHANGED",
  HOST_NAVIGATE:  "HOST_NAVIGATE",
  ERROR:          "ERROR",

  // 新增
  EXECUTE_START:    "EXECUTE_START",    // 子 app → portal：開始執行
  EXECUTE_COMPLETE: "EXECUTE_COMPLETE", // 子 app → portal：執行完成
  DISPLAY_UPDATE:   "DISPLAY_UPDATE",  // 子 app → portal：更新 Display 影像
});
```

### EXECUTE_START

```js
// 子 app 送出（Streamlit 透過 components.html 注入 JS）
createMessage("EXECUTE_START", {})

// Portal 收到後：
// 1. 在 Left Panel 覆蓋 Loading Overlay
// 2. setIsExecuting(true)
```

### EXECUTE_COMPLETE

```js
// 子 app 送出
createMessage("EXECUTE_COMPLETE", {
  success: true,          // boolean
  error: null             // string | null
})

// Portal 收到後：
// 1. 移除 Loading Overlay → setIsExecuting(false)
// 2. setActiveTab("output")  ← 自動切換到 Output 頁籤
```

### DISPLAY_UPDATE

```js
// 子 app 送出（可在 EXECUTE_START 時送 input 預覽，在 EXECUTE_COMPLETE 時送 output）
createMessage("DISPLAY_UPDATE", {
  imageUrl: "http://127.0.0.1:{port}/static/result.png",  // Streamlit static URL
  // 或
  imageUrl: "data:image/png;base64,..."                    // base64
})

// Portal 收到後：
// setDisplayImageUrl(event.data.payload.imageUrl)
```

---

## 六、Loading Overlay

當 `isExecuting === true`，在 `.left-panel` 上方覆蓋：

```jsx
{isExecuting && (
  <div className="loading-overlay">
    <div className="loading-spinner" />
    <span>執行中…</span>
  </div>
)}
```

CSS：半透明白底（`background: rgba(255,255,255,0.80)`），spinner 動畫，z-index 在 iframe 之上。

---

## 七、CSS 架構變更

### 移除
- `.shell` grid（移除 sidebar 欄）
- `.sidebar`、`.brand`（sidebar 版本）、`.nav`

### 新增

```css
/* 整體容器 */
.workspace {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

/* 下半部左右分割 */
.workspace-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

/* Left Panel */
.left-panel {
  display: flex;
  flex-direction: column;
  flex: 0 0 38%;
  border-right: 1px solid #d9e2ec;
  position: relative;  /* for loading overlay */
}

.tab-bar {
  display: flex;
  border-bottom: 1px solid #d9e2ec;
  background: #f8fafc;
}

.tab {
  flex: 1;
  border: none;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  padding: 10px;
  font-weight: 500;
  color: #52606d;
}

.tab.active {
  border-bottom-color: #2563eb;
  color: #2563eb;
  background: white;
}

.tab-content {
  flex: 1;
  min-height: 0;
  position: relative;
}

.tab-content iframe {
  border: 0;
  width: 100%;
  height: 100%;
  display: block;
}

/* Loading Overlay */
.loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.80);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  z-index: 10;
  font-size: 15px;
  color: #374151;
}

/* Right Panel */
.right-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f1f5f9;
  overflow: hidden;
}

.display-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.display-empty {
  color: #94a3b8;
  font-size: 15px;
  text-align: center;
}

/* Top Bar Brand（sidebar 移除後） */
.top-bar-brand {
  font-size: 17px;
  font-weight: 700;
  white-space: nowrap;
  margin-right: 8px;
}
```

---

## 八、React 元件結構

```
App
├── SidecarError（不變）
├── TopBar（原 toolbar，新增 brand）
│     ├── brand
│     ├── title + status
│     └── actions（select、Choose File、Start/Stop）
└── WorkspaceBody
      ├── LeftPanel
      │     ├── TabBar（[Input] [Output]）
      │     ├── TabContent（iframe 或 EmptyState）
      │     └── LoadingOverlay（isExecuting 時出現）
      └── RightPanel
            ├── DisplayImage（有影像時）
            └── DisplayEmpty（無影像時）
```

---

## 九、handleMessage 更新

```js
function onMessage(event) {
  if (!isProtocolMessage(event.data)) return;
  if (!isAllowedOrigin(event.origin, config?.allowedOrigins ?? ["*"])) return;

  switch (event.data.type) {
    case MessageTypes.CHILD_READY:
      // 不變
      break;
    case MessageTypes.ROUTE_CHANGED:
      // 不變
      break;
    case MessageTypes.EXECUTE_START:
      setIsExecuting(true);
      break;
    case MessageTypes.EXECUTE_COMPLETE:
      setIsExecuting(false);
      setActiveTab("output");
      if (!event.data.payload.success) {
        setStatus(`執行失敗：${event.data.payload.error}`);
      }
      break;
    case MessageTypes.DISPLAY_UPDATE:
      setDisplayImageUrl(event.data.payload.imageUrl);
      break;
  }
}
```
