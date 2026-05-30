# CIM Hybrid Edge Platform

## 🗺️ 文件地圖（權威來源）

| 想找什麼 | 看這裡（唯一權威） |
|----------|-------------------|
| 平台整體架構 | [`docs/platform/ARCHITECTURE.md`](platform/ARCHITECTURE.md) |
| AI 助理導覽 | [`docs/platform/AI_CONTEXT.md`](platform/AI_CONTEXT.md) |
| 系統資料流 | [`docs/platform/system-flow.md`](platform/system-flow.md) |
| **共用功能（DB / Log / config / UI 元件）在哪、怎麼用** | [`docs/platform/shared-components.md`](platform/shared-components.md) |
| 架構重構計畫與討論記錄 | [`docs/platform/architecture-restructure-discussion.md`](platform/architecture-restructure-discussion.md) |
| 模組總覽 | [`docs/MODULES.md`](MODULES.md) + [`docs/modules/`](modules/) |
| Labeling / X-AnyLabeling | [`docs/ANNOTATION_XANYLABELING.md`](ANNOTATION_XANYLABELING.md)、[`docs/Annotation_Platform_Interface.md`](Annotation_Platform_Interface.md) |

> 平台級文件一律放 `docs/platform/`，請勿在 `docs/` 根目錄建立同名重複檔（CI 之後會擋）。

## Current Annotation Workstream

The annotation common component and X-AnyLabeling integration are documented in:

```text
docs/ANNOTATION_XANYLABELING.md
```

Current implementation highlights:

- `sidecar/python-engine/annotation/` contains the canonical annotation model,
  validation, storage, services, and import/export adapters.
- `mcp/annotation_mcp/` exposes generic `annotation_*` MCP tools.
- X-AnyLabeling is installed in `.venv-xanylabeling` and verified as
  `4.0.0-beta.7`.
- Test gates: `npm run test:python` (sidecar) + `npm test` (JS shared-protocol /
  host-electron); see CI or the latest evaluation doc for current pass counts
  (not hardcoded here to avoid drift).

Windows 桌面應用程式，整合 Electron 主程式、React Portal UI 與 Python FastAPI 側車（Sidecar），提供電腦視覺影像處理工具的本地執行環境。

---

## 目錄

1. [專案概覽](#專案概覽)
2. [功能特色](#功能特色)
3. [架構總覽](#架構總覽)
4. [系統需求](#系統需求)
5. [安裝與設定](#安裝與設定)
6. [DEV 模式啟動](#dev-模式啟動)
7. [PROD 模式啟動](#prod-模式啟動)
8. [模組目錄](#模組目錄)
9. [管理中心](#管理中心)
10. [打包發布](#打包發布)
11. [測試](#測試)
12. [專案結構](#專案結構)

---

## 專案概覽

CIM Hybrid Edge Platform 是一個 Windows 桌面應用，專為工廠/邊緣端影像品質分析設計。使用者透過 Electron 視窗操作 React Portal UI，Portal 呼叫本地 Python FastAPI Sidecar，Sidecar 再以子程序方式啟動 Streamlit 工具介面。

本平台支援兩種執行模式：

- **DEV 模式**（`CIM_DEV_MODE=1`）：從檔案系統即時讀取模組原始碼，適合開發與測試。
- **PROD 模式**（`CIM_DEV_MODE=0`）：僅執行已透過管理中心「發布」至資料庫的模組快照，確保生產環境一致性。

---

## 功能特色

- 本地執行所有運算，不依賴雲端服務，資料不離廠
- 模組化架構：每個工具為獨立的 Input / Process / Output 三層模組
- 雙模式切換：DEV（即時開發）/ PROD（已發布快照）
- 版本管理與回溯：透過管理中心發布新版本、回溯至舊版本
- Sheet 頁面組合：將多個模組組合成多分頁工作流程
- Bounding Box 影像標注（module_006）
- Canny 邊緣偵測與品質分析（module_004）
- 歷史記錄查詢（module_005）
- 自動重啟：Sidecar 崩潰時 Electron 自動在 3 秒後重啟
- Portable 發布：打包為單一 `.exe`，免安裝即可部署

---

## 架構總覽

Electron 主程式（`apps/host-electron/src/main.js`）負責啟動 Python FastAPI Sidecar、建立 BrowserWindow 載入 React Portal。Portal 透過 `window.cimHost` IPC Bridge 向 Electron 傳遞指令，Electron 再以 HTTP 呼叫 Sidecar 的 `/tools/{id}/start` 端點。Sidecar 啟動兩個 Streamlit 子程序（Input / Output），各自在隨機埠口運行，Portal 以 iframe 方式嵌入。模組原始碼在 DEV 模式直接從 `scripts/module_NNN/` 讀取，PROD 模式從 `logs/data/tools.sqlite` 的 `tool_versions` 資料表載入已發布的程式碼快照。

---

## 系統需求

| 項目 | 最低版本 |
|------|---------|
| 作業系統 | Windows 10/11 (64-bit) |
| Node.js | 18 LTS 以上 |
| npm | 9 以上（隨 Node.js 附帶） |
| Python | 3.11 以上 |
| pip | 隨 Python 附帶 |
| Electron | 39（自動由 `npm install` 安裝） |

---

## 安裝與設定

### 1. 安裝 Node.js 依賴

```bat
cd C:\code\claude\nativeApp
npm install
```

此指令會安裝根目錄、`apps/host-electron`、`apps/portal-react` 及 `packages/` 下的所有依賴。

### 2. 安裝 Python 依賴

```bat
cd C:\code\claude\nativeApp\sidecar\python-engine
pip install -r requirements.txt
```

主要依賴套件：`fastapi`、`uvicorn`、`streamlit`、`opencv-python-headless`、`streamlit-image-annotation`、`pyyaml`、`numpy`、`scipy`、`Pillow`、`scikit-learn`

### 3. 確認目錄結構

安裝完成後，以下目錄應存在：

```
apps/host-electron/node_modules/
apps/portal-react/node_modules/
```

---

## DEV 模式啟動

DEV 模式下，所有 `scripts/module_*/` 的模組都會直接從檔案系統讀取，即時反映程式碼變更。

### 方法一：直接執行批次檔（推薦）

```bat
start-dev.bat
```

此批次檔會：
1. 終止殘留的 Electron 程序與占用埠口的程序
2. 在新的 cmd 視窗中設定 `CIM_DEV_MODE=1` 並執行 `npm run dev`

### 方法二：手動執行

```bat
cd apps\host-electron
set CIM_DEV_MODE=1
npm run dev
```

`npm run dev` 會同時啟動 Vite dev server（`portal-react`，port 5173）與 Electron，Electron 等待 Vite 就緒後自動開啟視窗。

啟動後，Portal 頂端狀態列會顯示 **DEV** 徽章。

---

## PROD 模式啟動

PROD 模式下，只有透過管理中心「發布至 Prod」的模組才會顯示。

### 方法一：直接執行批次檔（推薦）

```bat
start-prod.bat
```

### 方法二：手動執行

```bat
cd apps\host-electron
set CIM_DEV_MODE=0
npm run dev
```

啟動後，Portal 頂端狀態列會顯示 **PROD** 徽章。

> **注意**：首次以 PROD 模式執行前，請先在 DEV 模式下透過「管理中心」對需要的模組點選「🚀 發布到 Prod」。

---

## 模組目錄

| 工具 ID | 模組編號 | 名稱 | 描述 | 狀態 |
|---------|---------|------|------|------|
| `module_001` | 001 | OpenCV 影像處理 | 以 OpenCV 對影像進行基本處理（灰階、模糊、邊緣偵測等） | 啟用 |
| `module_002` | 002 | 影像資訊讀取 | 讀取並顯示影像的基本資訊（尺寸、色彩空間、像素統計） | 停用（Sheet 專用，不在 Portal 顯示）|
| `module_003` | 003 | 不規則邊框產生器 | 以純數學方式生成帶有可控凹凸紋理的矩形影像，含梯度方向變異與 PSD 頻率分析 | 啟用 |
| `module_004` | 004 | 邊緣完整度偵測 | 上傳影像後進行 Canny 邊緣偵測，量測粗糙度、梯度方向變異與 PSD 高頻能量比，並儲存至資料庫 | 啟用 |
| `module_005` | 005 | 邊緣記錄查詢 | 依日期範圍查詢歷史邊緣量測記錄，含影像預覽與下載 | 啟用 |
| `module_006` | 006 | 動物影像標記 | 動物影像資料集標記工具，支援多類別篩選與互動式標記 | 啟用 |
| `sheet-edge-analysis` | 008 | 邊緣品質分析（套件） | 組合多個邊緣分析模組的 Sheet 頁面工作流程 | 啟用 |
| `management-center` | 009 | 管理中心 | 工具發布/回溯、版本管理、Sheet 編輯、系統備份 | 啟用（僅 DEV 模式可見） |

---

## 管理中心

管理中心（tool ID: `management-center`）是平台的後台介面，**僅在 DEV 模式下可見**。

### 功能頁籤

| 頁籤 | 說明 |
|------|------|
| 工具管理 | 查看所有工具狀態、一鍵發布至 Prod、版本回溯、封存/還原 |
| 頁面（Sheet） | 建立/編輯多分頁組合工作流程，從 sheet.yaml 同步 |
| 權限設定 | 檢視角色與權限矩陣（功能佔位，正式整合待後續版本） |
| 系統 | 資料庫資訊與 JSON 備份下載 |

### 發布模組流程

1. 以 DEV 模式啟動平台
2. 從 Portal 下拉選單選擇「009 - 管理中心」並按下 **Start Tool**
3. 在「工具管理」頁籤找到目標模組
4. 點選「🚀 發布到 Prod」按鈕
5. 重新以 PROD 模式啟動，該模組即可顯示並執行

---

## 打包發布

打包流程請使用 Claude 指令 `/package-build`，或依以下步驟手動執行：

### 1. 編譯 Python Sidecar

```bat
cd sidecar\python-engine
pyinstaller engine.spec
```

輸出：`sidecar/python-engine/dist/engine.exe`

### 2. 建置 React Portal

```bat
cd apps\portal-react
npm run build
```

### 3. 打包 Electron Portable

```bat
cd apps\host-electron
npm run package:portable
```

輸出：`release\CIM Hybrid Edge Platform*.exe`（Portable，免安裝）

> 詳細步驟與注意事項請參閱 `.claude/commands/package-build.md`。

---

## 測試

### JavaScript 單元測試

```bat
npm test
```

等同於同時執行：
- `packages/shared-protocol` 的 vitest 測試
- `apps/host-electron` 的 vitest 測試（包含 ELECTRON_RUN_AS_NODE 問題說明）

### Python 單元測試

```bat
npm run test:python
```

等同於：

```bat
python -m pytest sidecar/python-engine/tests/ -v
```

測試覆蓋範圍：
- `tests/` — API、Plugin Registry、Plugin Loader、SQLite Adapter、Auth Provider、Tool Comms、Log Utils 等
- `scripts/module_*/NNN_process_test.py` — 各模組 Process 層的單元測試

---

## 專案結構

> 平台已完成架構重構：**共用碼在 `core/`、Labeling 收成 `plugins/labeling/`**。下圖為現況。

```
nativeApp/
├── apps/
│   ├── host-electron/           # Electron 主程式（src/main.js、preload.js、launch-electron.js）
│   └── portal-react/            # React Portal UI（src/main.jsx：工具選擇、iframe、重新載入鈕、角色切換）
├── sidecar/
│   └── python-engine/           # Python FastAPI Sidecar
│       ├── engine.py            # FastAPI 主程式 + SQLiteToolAdapter（plugin.yaml 自動掃描、/reload 熱載、/whoami /set-role）
│       ├── plugin_registry.py   # PluginRegistry（發布/回溯/enabled flags；雙根掃描 scripts/ + plugins/*/modules/）
│       ├── plugin_loader.py     # PluginLoader（DEV 檔案系統 / PROD DB snapshot；dual-root 解析）
│       ├── auth_provider.py     # AuthProvider（RBAC enforce + 可切換身分 get_current_role/set_identity）
│       ├── engine.spec          # PyInstaller 設定（自動 collect 每個 plugins/*/domain）
│       ├── core/                # ★平台共用層（不依賴 plugins）
│       │   ├── forms.py         #   宣告式 form:（含 date/time）
│       │   ├── output.py        #   宣告式 output:
│       │   ├── external_gui.py  #   宣告式 external_gui:（啟動外部 GUI + 回收）
│       │   ├── rbac.py          #   宣告式 RBAC（config/permissions.yaml）
│       │   ├── sandbox.py / guidance.py
│       │   └── integrations/    #   connector.py / tenant.py / registry.py(autodiscover) / connectors/
│       ├── tools/               # Runner + CLI（cv_framework_runner / management_runner / sheet_runner /
│       │   │                    #   scaffold.py / set_role.py / db_utils / tool_comms / tool_result / log_utils）
│       ├── scripts/             # 平台/範例模組（module_001-005、007 零-code 範例）+ shared/（_config_base、UI 元件）
│       ├── plugins/
│       │   └── labeling/        # ★Labeling plugin（標竿工具）
│       │       ├── domain/      #   services / models / adapters / formats / storage / integrations
│       │       ├── modules/     #   GUI 模組 module_006/008/012-020/026
│       │       ├── sheets/      #   annotation.yaml（🐜 影像標註，4 tabs）
│       │       ├── mcp/         #   annotation MCP server（python -m plugins.labeling.mcp.server）
│       │       └── plugin.manifest.yaml
│       ├── config/              # tools.sqlite + permissions.yaml / sandbox_policy.yaml / external_systems.yaml
│       ├── sheets/              # 平台級 sheet YAML
│       └── tests/               # Python 單元測試
├── mcp/                         # 根 MCP servers（platform_mcp / cim_gui_mcp）；由 .mcp.json 設定
├── packages/
│   └── shared-protocol/         # Electron ↔ Portal 共用訊息協定
├── scripts/                     # 開發/E2E 工具（e2e/ Puppeteer、win/ electron-cache、manual/ 整合腳本）
├── docs/                        # 文件（README 地圖、MODULES、modules/、platform/、patterns/）
├── openspec/                    # ADR / changes / project.md
├── external-system-reference/   # 外部系統 mock server + sample data
├── .mcp.json                    # MCP server 設定（repo 根）
├── start-dev.bat / start-prod.bat / start-trusted.bat / build-release.bat
└── package.json                 # Monorepo 根設定（workspaces: apps/*, packages/*）
```

> 模組完整清單見 [`MODULES.md`](MODULES.md)；Labeling GUI 模組（006/008/012–026）物理位置在 `sidecar/python-engine/plugins/labeling/modules/`。
