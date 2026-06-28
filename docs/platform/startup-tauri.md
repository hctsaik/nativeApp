# 啟動方式 = Tauri（新架構正式主線）

> **一句話：啟動一律用 Tauri 殼（`nativeApp_Light`）。** Electron 殼退為備援。
> 殼以外**完全不變**：Python engine、portal（React dist）、cim-modules、Streamlit 工具、外部 GUI
> 與 Electron 版**共用同一份**——只有「殼」從 Electron 換成 Tauri（Rust + 系統 WebView2）。

## 為什麼換 Tauri
- **WDAC 友善**：Electron 要跑 `electron.exe` + 多個未簽章 helper + 打包整個 Chromium；Tauri 是
  **單一可簽章的 Rust exe + 系統 WebView2（微軟簽章、WDAC 信任）**。release `tauri build` 產**簽章 nsis**
  （`tauri.conf.json` 已設 `certificateThumbprint`）。
- **dev 不跑 esbuild**：`tauri.conf.json` 的 `frontendDist` 直接指向**預建** `apps/portal-react/dist`，
  沒有 `devUrl`/`beforeDevCommand` → `tauri dev` **不啟動 Vite**，天生避開本機 WDAC 對 `esbuild.exe` 的封鎖。
- **輕量**：不打包 Chromium，體積/記憶體小很多。

## 怎麼啟動（DEV）
```powershell
# 根目錄任一支都會自動轉導到 Tauri：
start-dev.bat          # → start-dev-tauri.bat
start-dev-nowdac.bat   # → start-dev-tauri.bat
# 或直接：
start-dev-tauri.bat
```
`start-dev-tauri.bat` 做的事：preflight submodule → 檢查 Tauri 專案/`node_modules`/`cargo`/預建 dist/Python3.11 →
清殘留 engine → 設 `CIM_ENGINE_EXE=…\engine.py`、`CIM_ENGINE_PYTHON=<py3.11>` → 在
`..\nativeApp_Light\5_PG_Develop` 跑 `npm run tauri:dev`（首次會編譯 Rust）。

### 前置需求（首次）
1. **`nativeApp_Light` 放在 `nativeApp` 同層**（例如都在 `C:\code\claude\` 下）。
2. `cd ..\nativeApp_Light\5_PG_Develop && npm install`（Tauri 前端相依）。
3. **Rust toolchain（rustup）** + Tauri 系統需求（Windows: WebView2 Runtime，通常已內建）。
4. **預建 portal dist**：`apps/portal-react/dist` 要存在（在可用 esbuild 的機器 `npm --prefix apps/portal-react run build`）。

### engine 解析（sidecar.rs）
- `CIM_ENGINE_EXE` 副檔名 `.py` → 用 `CIM_ENGINE_PYTHON` 跑**原始碼 engine**（DEV）。
- 預設（未設 env）→ frozen `sidecar/python-engine/dist/engine.exe`（對映 packaged）。
- engine 的 `--control-port`／`--log-dir` 由 Rust 端注入；log 落在 `nativeApp_Light/5_PG_Develop/logs`。

## ⚠️ 與 Electron 殼的差異（測試/工具要注意）
- **沒有 `127.0.0.1:19222` dev-log server**：那是 **Electron 殼專屬**（`apps/host-electron/src/main.js`）。
  Tauri 殼的 portal 改由 `window.cimHost.getAppConfig()`（`cimhost-shim.js` + `bridge.rs`）取得 sidecar 控制埠。
  → 依賴 19222 探測埠的工具（`cim-gui` MCP、舊 E2E harness）對 Tauri 殼**要改用** `nativeApp_Light/5_PG_Develop/e2e/`
  的 CDP（`connectOverCDP` WebView2）流程（見 `/e2e-test` skill）。
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

相關：根目錄 `CLAUDE.md`「啟動方式 / 啟動鏈」、`nativeApp_Light/CLAUDE.md`（Tauri 殼設計與驗收）。
