# 啟動方式 = Tauri（新架構正式主線）

> **一句話：啟動一律用 Tauri 殼（已併入本 repo `apps/host-tauri/`）。** Electron 殼退為備援。
> 殼以外**完全不變**：Python engine、portal（React dist）、cim-modules、Streamlit 工具、外部 GUI
> 與 Electron 版**共用同一份**——只有「殼」從 Electron 換成 Tauri（Rust + 系統 WebView2）。

## 為什麼換 Tauri（以及 WDAC 的真相）
- **部署/runtime 對 WDAC 友善（真正的勝場）**：Electron 要跑 `electron.exe` + 多個未簽章 helper +
  打包整個 Chromium；Tauri 是 **單一可簽章的 Rust exe + 系統 WebView2（微軟簽章、WDAC 信任）**。
  release `npm run tauri:build` 產**簽章 nsis**（`tauri.conf.json` 已設 `certificateThumbprint`）→
  裝到 WDAC 機器上，簽章 runtime 直接放行。
- **輕量**：不打包 Chromium，體積/記憶體小很多。

### ⚠️ WDAC 實測結論（2026-06-29 更正，務必看）
> **關鍵區別：「本機新編譯出來的未簽章 exe」被擋，「跑既有的 exe」通常不會。**
> - **被擋（本機新編譯）**：`cargo` 在 `tauri dev`/`tauri build` 會產出並執行**新的 build-script / debug exe**，
>   被 WDAC 封鎖：
>   ```
>   error: failed to run custom build command for `cim-light`
>     could not execute process `...\src-tauri\target\debug\build\...\build-script-build`
>     應用程式控制原則已封鎖此檔案。 (os error 4551)
>   ```
> - **可跑（既有 exe）**：實測**隨 repo 附帶的預建** `cim-light.exe`（Tauri 殼，`apps/host-tauri/prebuilt/cim-light.exe`）
>   **在 WDAC 下直接執行 OK**（portal + engine 都載入；疑似 ISG 檔案信譽）。
>
> **本機現行做法（已更正）**：
> - **主線 = 直接跑隨 repo 附帶的預建 `cim-light.exe`**（`apps\host-tauri\prebuilt\cim-light.exe`，設 `CIM_ENGINE_EXE=…\engine.py`
>   + `CIM_ENGINE_PYTHON=<py3.11>`）。`start-dev.bat` → `start-dev-tauri.bat` 就是這樣做，**絕不在本機跑 `tauri dev`/`tauri build`**。
> - 日常 dev 改 portal dist / Python engine / 模組（runtime 載入，**不需重編 Rust 殼**）→ 本機 Tauri 完全夠用。
> - **只有要改 Rust 殼本身**才需重編：在「沒有 WDAC 強制的機器」`cd apps\host-tauri && npm install && npm run tauri:build`（簽章版），
>   再把產物**覆蓋回 `apps\host-tauri\prebuilt\cim-light.exe`**；或請 IT 放行 `apps\host-tauri\src-tauri\target`。
> - **Electron（no-WDAC）退為最終備援**（`start-dev-nowdac-electron.bat`）：只在「沒有既有 Tauri exe 或它也跑不起來」時用。

## 怎麼啟動（DEV）
```powershell
# 根目錄任一支都會自動轉導到 Tauri：
start-dev.bat          # → start-dev-tauri.bat
start-dev-nowdac.bat   # → start-dev-tauri.bat
# 或直接：
start-dev-tauri.bat
```
`start-dev-tauri.bat` 做的事：preflight submodule → 找**既有已 build 的** `cim-light.exe`
（依序：`apps\host-tauri\prebuilt` → 本機 `apps\host-tauri\src-tauri\target\release|debug` → 舊 sibling 備援；
找不到才轉 Electron 備援，**不在本機 cargo 重編**）→ 檢查預建 dist/Python3.11 →
清殘留 engine → 設 `CIM_ENGINE_EXE=…\engine.py`、`CIM_ENGINE_PYTHON=<py3.11>` → **直接執行那顆 `cim-light.exe`**。

### 前置需求（首次）
> **日常啟動不需要任何額外設定**：Tauri 殼已併入本 repo（`apps/host-tauri/`），預建 exe
> `apps/host-tauri/prebuilt/cim-light.exe` **隨 clone 附帶、開箱即跑**——不必 clone sibling、不必為殼 `npm install`、不需 Rust toolchain。
1. **預建 portal dist**：`apps/portal-react/dist` 要存在（在可用 esbuild 的機器 `npm --prefix apps/portal-react run build`）。
2. Python 3.11（給原始碼 engine）。
3. **只有要重編 Rust 殼時**才需要：在「沒有 WDAC 強制的機器」`cd apps\host-tauri && npm install`（Tauri 前端相依）
   + **Rust toolchain（rustup）** + Tauri 系統需求（Windows: WebView2 Runtime，通常已內建），`npm run tauri:build` 後把產物覆蓋回 `apps/host-tauri/prebuilt/cim-light.exe`。

### engine 解析（sidecar.rs）
- `CIM_ENGINE_EXE` 副檔名 `.py` → 用 `CIM_ENGINE_PYTHON` 跑**原始碼 engine**（DEV）。
- 預設（未設 env）→ frozen `sidecar/python-engine/dist/engine.exe`（對映 packaged）。
- engine 的 `--control-port`／`--log-dir` 由 Rust 端注入；log 落在 `apps/host-tauri/logs`。

## ⚠️ 與 Electron 殼的差異（測試/工具要注意）
- **沒有 `127.0.0.1:19222` dev-log server**：那是 **Electron 殼專屬**（`apps/host-electron/src/main.js`）。
  Tauri 殼的 portal 改由 `window.cimHost.getAppConfig()`（`cimhost-shim.js` + `bridge.rs`）取得 sidecar 控制埠。
  → 依賴 19222 探測埠的工具（`cim-gui` MCP、舊 E2E harness）對 Tauri 殼**要改用** `apps/host-tauri/e2e/`
  的 CDP（`connectOverCDP` WebView2）流程（`cd apps/host-tauri && node e2e/run-all.mjs`；見 `/e2e-test` skill）。
- module 的 RWD/版面驗證：因 portal/engine 共用，**直接驅動 Streamlit URL 或 portal-mimic 的結果，Electron 與 Tauri 一致**。

## 全部啟動 / 打包 .bat 的處置（盤點，確保沒有漏改）
| .bat | 舊用途 | 新處置 |
|------|--------|--------|
| `start-dev.bat` | Electron DEV | ✅ **轉導 → `start-dev-tauri.bat`** |
| `start-dev-nowdac.bat` | Electron DEV（WDAC 繞 esbuild） | ✅ **轉導 → `start-dev-tauri.bat`** |
| `start-dev-tauri.bat` | （新增） | ✅ **Tauri DEV 啟動器（正式主線）** |
| `start-dev-electron.bat` | （新增＝舊 `start-dev`） | Electron DEV **備援** |
| `start-dev-nowdac-electron.bat` | （新增＝舊 `start-dev-nowdac`） | Electron DEV（WDAC）**備援** |
| `start-prod.bat` | Electron PROD | ⏳ 仍 Electron；**Tauri prod = `npm run tauri:build`（簽章 nsis）**，待 PROD 遷移 |
| `start-trusted.bat` | WDAC trusted Electron 啟動 | ⏳ 仍 Electron；Tauri 的簽章 runtime 取代之，待 PROD 遷移 |
| `prepare-trusted-electron.bat` | WDAC trusted electron 準備 | Electron-only；**Tauri 不需此步驟** |
| `build-release.bat` | Electron 打包 | Electron 打包；**Tauri 打包改 `npm run tauri:build`** |
| `start-fleet.bat` | fleet 模擬（engine×2 + registry） | 殼無關（純 engine 層）→ **不動** |
| `scripts/win/link-labeling.bat` | 掛 labeling junction | 殼無關 → **不動** |
| `scripts/win/preflight-submodules.bat` | submodule preflight | 殼無關；Tauri bat 也呼叫它 → **不動** |

> **DEV 啟動已全數導向 Tauri。** PROD/trusted/打包（`start-prod` / `start-trusted` /
> `prepare-trusted-electron` / `build-release`）目前仍是 Electron 路徑——Tauri 的 PROD 對應是
> `npm run tauri:build`（簽章 nsis），屬下一階段「PROD 遷移」，尚未轉導（這些 bat 已加註指引）。

## 真的要用舊 Electron 殼（備援）
```powershell
start-dev-electron.bat          # 一般 Electron DEV
start-dev-nowdac-electron.bat   # WDAC 環境的 Electron DEV（靜態服務 dist + dev Electron）
```
僅在「Tauri 殼真的起不來」時暫用；用完請回到 Tauri。

相關：根目錄 `CLAUDE.md`「啟動方式 / 啟動鏈」、`apps/host-tauri/`（Tauri 殼原始碼、預建 exe 與 e2e 驗收）。
