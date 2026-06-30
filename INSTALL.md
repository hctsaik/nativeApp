# INSTALL.md — CIM Hybrid Edge Platform 安裝與建置手冊（Windows）

> 🤖 **AI AGENT: if you are setting up this project, READ AND EXECUTE THIS FILE TOP-TO-BOTTOM.**
> 由上到下逐步執行每個 PowerShell 區塊，即可從零安裝所有相依、建置並啟動 Tauri 殼。遇到錯誤先查最後一節「疑難排解」。
> 注意：本檔是「文件」，AI 不會自動執行——是否照做取決於使用者的開場指令（見專案根的 `AGENTS.md` / `README.md`）。

**本文件適用機器**：**具備編譯能力、且 _沒有_ WDAC 強制（WDAC enforce）的 Windows 機器**。
在這種機器上 `cargo` / `tauri build` / `vite build`（esbuild/rollup）都可以正常跑，所以可以**真的把 Tauri 殼 `cim-light.exe` 編出來**。
日常開發機（`COLA\hctsa`）因 WDAC 強制會擋掉新編譯出來的未簽章 exe（這就是為什麼要在「別的機器」建殼），詳見本文末「和 WDAC 的關係」與專案 [`CLAUDE.md`「## WDAC」](CLAUDE.md)。本文件**不重新討論 WDAC**，只負責「在可編譯機器上把東西裝好、建好、跑起來」。

---

## 0. 前置需求 (Prerequisites)

下表所有項目都要先裝好（Tauri 工具鏈是這次新增、舊 `docs/INSTALL.md` 沒有的部分）。

| 工具 | 版本 / 來源（直接下載備援） | 為什麼需要 |
|------|------------|-----------|
| **Git** | 任意近期版本，[git-scm.com](https://git-scm.com/) | clone 平台與 submodule、建立 junction 前置 |
| **Node.js LTS** | LTS 即可（實測可用：Node `v24.13.0` / npm `11.6.2`），[nodejs.org](https://nodejs.org/) | 跑 `@tauri-apps/cli`、portal（Vite）、root workspaces、shared-protocol |
| **Python 3.11** | **必須 3.11**，且是 engine 會用的同一支（`py -3.11`），[python.org](https://www.python.org/downloads/release/python-3119/) | engine（FastAPI/Streamlit）核心；per-tool venv 也以這支為基底 |
| **MSVC C++ Build Tools**（重量級特殊相依，約 **1–6 GB**） | Visual Studio **Build Tools 2022** 勾「**Desktop development with C++**」workload，[下載頁](https://visualstudio.microsoft.com/visual-cpp-build-tools/) | 提供 **`link.exe`**（MSVC linker）。Rust 的 `msvc` toolchain 連結階段一定要它，否則 `cargo build` 失敗。**必須在 rustup/第一次 cargo build 之前裝好** |
| **Rust（rustup）** | host **`x86_64-pc-windows-msvc`**；MSRV `1.77`（裝最新 stable 即可），[rustup.rs](https://rustup.rs/)（直接下載 `rustup-init.exe`） | 編譯 Tauri v2 的 Rust 殼（`cargo build`/`tauri build`） |
| **WebView2 Runtime** | Win11 已內建；舊 Win10 用 Microsoft **Evergreen Bootstrapper**，[下載頁](https://developer.microsoft.com/microsoft-edge/webview2/) | Tauri 殼用系統 WebView2 當渲染層；缺它則 `cim-light.exe` 啟動白屏/報錯 |

> ⚠️ **順序很重要**：**先裝 MSVC C++ Build Tools，再裝 Rust**。`rustup-init` 只會「偵測並提示」缺少 MSVC，**不會**幫你裝；若先裝 Rust，會在步驟 7 第一次 `cargo build` 才爆 `link.exe not found`。

安裝 Build Tools 與 Rust（PowerShell；**每裝完一項都開新終端讓 PATH 生效**）：

```powershell
# (1) 先裝 MSVC C++ Build Tools（含 Desktop development with C++ workload，提供 link.exe）
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
# (2) 開新終端後，再裝 rustup（msvc host）
winget install --id Rustlang.Rustup -e
# (3) 再開新終端，確認 toolchain
rustup default stable
rustc --version                  # 應 >= 1.77
rustup target list --installed   # 應含 x86_64-pc-windows-msvc
```

> **`where.exe link.exe` 可能在一般 shell 找不到也屬正常**——`link.exe` 只在「Developer」環境的 PATH 內，但 `cargo` 會透過 MSVC toolchain 自行定位它。所以**不要**只因 `where.exe link.exe` 失敗就判定沒裝好；真正的判準是步驟 7 的 `cargo`/`tauri build` 能否連結成功。
> **若機器沒有 `winget`**（精簡/受控的 Windows 映像、舊 Win10、LTSC/Server 常見）：到 Microsoft Store 安裝「App Installer」取得 winget，或直接用上表「直接下載備援」連結逐一安裝。

---

## 1. 選定並建立「工作根目錄」（sibling 佈局的前提）

`nativeApp` 與 `ANnoTation` 兩個 repo **必須是同層 sibling**（Labeling 外掛 junction 用相對路徑 `..\ANnoTation`）。Tauri 殼已**併入 nativeApp 本體**（`apps\host-tauri\`），不再是外部 sibling repo。本文件範例用 `C:\code\claude` 當工作根，**你可以換成自己的路徑，但之後每個指令裡的這個前綴都要一起換**。

```powershell
# 選一個工作根（可自訂），先建好再進去
$WORK = "C:\code\claude"
New-Item -ItemType Directory -Force $WORK | Out-Null
Set-Location $WORK
```

> 下文所有 `cd C:\code\claude...` 都代表「你的 `$WORK`」。若你改了 `$WORK`，請整份文件一致替換。

---

## 2. Clone 平台 nativeApp（含 submodule）

submodule **只有三個**：`vendor/AI4BI`、`vendor/LV`（branch `uihuang_dev`）、`plugins/cim-modules`（= `nativeApp_modules.git`）。
**Labeling（ANnoTation）不是 submodule**（不在 `.gitmodules`），步驟 4 再處理。

```powershell
Set-Location C:\code\claude
git clone --recurse-submodules https://github.com/hctsaik/nativeApp.git
Set-Location C:\code\claude\nativeApp
# 若忘了 --recurse-submodules，事後補：
git submodule update --init --recursive
```

> ℹ️ **分支注意**：本文件描述的內容（`apps/host-tauri`、三個 submodule 接線含 `cim-modules`、以及本文件最新版）目前在分支 **`feat/extract-cim-modules`**。若 GitHub 預設分支 `main` 尚未合併這些，純 `git clone`（落在 main）可能拿不到它們——請改用帶分支的 clone：
> `git clone -b feat/extract-cim-modules --recurse-submodules https://github.com/hctsaik/nativeApp.git`

---

## 3. Tauri 殼（已併入本體；日常無需額外動作）

Tauri 殼已**併入 nativeApp 本體**：Rust 原始碼在 `apps\host-tauri\src-tauri\`，npm/tauri-cli 包裝在 `apps\host-tauri\package.json`，app 名 `cim-light`。
**預建可執行檔已隨 repo 版控**：`apps\host-tauri\prebuilt\cim-light.exe`（每次 clone 都帶，免編譯即可跑）。
**日常使用/啟動不需任何額外步驟**——不必 clone sibling、不必為殼跑 `npm install`、也不必 Rust 工具鏈。只有**要重建 Rust 殼**（少見）才需步驟 0 的工具鏈與步驟 8。

> `tauri.conf` **沒有** `beforeDevCommand` / `devUrl`，所以 Tauri **不會自己跑 Vite**；
> portal dist 必須由我們在步驟 7 預先建好（這也是步驟 7 必須在步驟 8「Tauri 建置」之前的原因）。

---

## 4. Clone ANnoTation（同層 sibling）並建立 junction（Labeling 外掛）

Labeling 是**獨立 repo，用 directory JUNCTION 掛進平台**（**不是** git submodule、**不在** `.gitmodules`）。junction 不需 admin 權限。

```powershell
Set-Location C:\code\claude        # 與 nativeApp 同一層
git clone https://github.com/hctsaik/ANnoTation.git
Set-Location C:\code\claude\nativeApp
scripts\win\link-labeling.bat
# 會把 sidecar\python-engine\plugins\labeling -> ..\ANnoTation 建成 junction
```

> 每次重新 clone `nativeApp` 都要重跑一次 `link-labeling.bat`（junction 不在 git 樹內）。
> `link-labeling.bat` 以來源資料夾內是否有 **`plugin.manifest.yaml`** 判定 ANnoTation 是否有效（`verify-setup.ps1` 也以此檔為準）。若報「Labeling source not found」，代表 `..\ANnoTation` 缺該檔（clone 不完整/淺 clone）——重新完整 clone 即可。
> 來源預設找同層 `..\ANnoTation`；要指定他處：`set "LABELING_SRC=D:\path\to\ANnoTation"` 後再跑。背景見 [`docs/platform/repo-topology.md`](docs/platform/repo-topology.md)。

---

## 5. 安裝 root Node 相依（workspaces）

root 是 npm workspaces（glob `apps/*`、`packages/*`；目前含 `apps/host-electron`、`apps/portal-react`、`packages/shared-protocol`）。

```powershell
Set-Location C:\code\claude\nativeApp
npm install
```

---

## 6. 安裝 Python 相依（**全部裝進 `py -3.11`**）

四層相依，依序裝進同一支 Python 3.11（與 engine 使用的同一支）：

```powershell
Set-Location C:\code\claude\nativeApp
$env:PYTHONUTF8 = "1"   # ⚠️ 繁中(cp950)Windows 必設！否則 (a)/(c) 讀含非 ASCII 註解的 requirements 會 UnicodeDecodeError（見疑難排解「cp950」列）
# (a) engine 核心（fastapi/uvicorn/streamlit/requests/pandas/numpy/scipy/Pillow/matplotlib...）
py -3.11 -m pip install -r sidecar\python-engine\requirements.txt
# (b) AI4BI（可編輯安裝，含 llm extras）— 非選用！
py -3.11 -m pip install -e "sidecar\python-engine\vendor\AI4BI[llm]"
# (c) Labeling 專屬（torch / torchvision / transformers / ultralytics ...，體積大、首次安裝慢）
py -3.11 -m pip install -r sidecar\python-engine\plugins\labeling\requirements-labeling.txt
# (d) 測試相依（驗證步驟必裝）— pytest / respx 故意不在任何 requirements*.txt 內，必須單獨裝
py -3.11 -m pip install pytest respx
```

> - **步驟 (b) 是 doctor 通過的硬性前置**：`verify-setup.ps1` 會把缺 `ai4bi`/`duckdb`/`plotly` 判為 **FAIL（非 WARN）**，所以**不要把 AI4BI 當選用而略過**。
> - 步驟 (d) 的 `pytest`/`respx` **刻意未列在任何 `requirements*.txt`**，因此這行 `pip install` 是**必裝、不是選裝**（部分 engine 測試需要 `respx`）。
> - **重量級 per-tool 相依走 per-tool venv 的，是「沒列在上述三層內」的工具相依**（例如 **LV 模組各自 `plugin.yaml` 的 `requires:`，如 umap**）——engine 首次啟動該工具時依宣告自動建隔離 venv 安裝（`core/tool_deps.py`），不必手動全域安裝。**注意：Labeling 的 `torch`/`ultralytics`/`torchvision`/`transformers` 不走這條，它們已在步驟 (c) 直接裝進全域 3.11。**
> - ⚠️ 專案內的 `python` 可能指向 `.venv-xanylabeling`（沒有 pytest/fastapi）；**安裝與測試一律用 `py -3.11`**。
> - ⚠️ **繁中(cp950)機器先設 `$env:PYTHONUTF8 = "1"`**：requirements 檔的「註解」含 UTF-8 字元（em-dash `—`、ellipsis `…`），pip（≤24）在無 BOM 時用系統 ANSI 編碼 cp950 解碼會崩。設了 UTF-8 模式即可，或改用較新版 pip。詳見疑難排解。
> - ⚠️ **步驟 (b) 是「全域 editable」——多 clone 共用同一支 `py -3.11` 時，最後一個跑 (b) 的 clone 會獨佔機器層級的 `ai4bi` 來源**。請把 (b) 指向**穩定主 clone**（如 `C:\code\claude\nativeApp`），**勿指向臨時/備份資料夾**；該路徑被刪/搬，所有 clone 的 `import ai4bi` 會一起壞（症狀：`pip show ai4bi` 看似已裝，但 `import ai4bi` 報 `ModuleNotFoundError`，doctor FAIL）。修法：重跑 (b) 指向有效路徑。

---

## 7. 預先建置 portal dist（**必須在 Tauri 建置之前**）

Tauri 載入的是預建好的 `apps/portal-react/dist`（`tauri.conf` 的 `frontendDist` 指向它）。**先有 dist，Tauri 才建得起來 / 跑得起來。**

```powershell
Set-Location C:\code\claude\nativeApp
npm --prefix apps\portal-react run build      # = vite build → 產出 apps\portal-react\dist
```

> 本機是 no-WDAC 機器，所以 `vite build`（內部用 esbuild/rollup）可以正常跑。
> （WDAC 強制機器才會擋 esbuild，那種機器就不該在本機 build，改帶這個 dist 過去用。）

---

## 8. 建置 Tauri 殼（簽章 NSIS）— 或直接 dev

Tauri v2；`bundle.targets = ['nsis']`；`productName = "CIM Hybrid Edge Platform"`；`identifier = com.cim.hybrid-edge-platform.light`。

> 殼已隨 repo 帶**預建可執行檔** `apps\host-tauri\prebuilt\cim-light.exe`，**一般無需執行本節**——只有改了 Rust 殼本身才需重建。

```powershell
Set-Location C:\code\claude\nativeApp\apps\host-tauri
npm install                # 重建殼才需要：安裝 @tauri-apps/cli ^2 等
npm run tauri:build        # = tauri build → 簽章 NSIS 安裝包 + src-tauri\target\release\cim-light.exe
# 開發迭代（即時跑、不出安裝包）：
# npm run tauri:dev
# 建好後，用新產物覆蓋預建檔（讓每次 clone 都拿到最新殼）：
# Copy-Item src-tauri\target\release\cim-light.exe prebuilt\cim-light.exe -Force
```

> ⏱️ **時間/空間預期**：第一次 `cargo`/`tauri build` 會編譯大量 crate，**可能數分鐘到十幾分鐘**；過程看似停住屬正常，**不要當成失敗中斷**。`src-tauri\target` 可長到數 GB。
>
> ⚠️ **簽章憑證注意（一定要看）**：要編輯的檔是 **`C:\code\claude\nativeApp\apps\host-tauri\src-tauri\tauri.conf.json`**，鍵路徑 `bundle.windows.certificateThumbprint`，目前值 `9A91F8C5D5E93B2828773F57DDF6D0EBDE18A82E` + DigiCert 時間戳（`http://timestamp.digicert.com`）。`tauri build` **會用該指紋的憑證簽章**——這張憑證必須在 **Windows 憑證存放區（cert store）**裡。機器上**沒有這張憑證**時，兩條路擇一：
> 1. **匯入該憑證**到目前使用者的 cert store（`certmgr.msc` / `Import-PfxCertificate`），再 `tauri build`；或
> 2. **建非簽章版**：把上述 `tauri.conf.json` 的 `bundle.windows.certificateThumbprint` 改成空字串 `""`（或移除該鍵），讓 build 不簽章。
>    （只想本機跑、不發佈時最省事；非簽章 exe 在 no-WDAC 機器可直接跑。改檔會弄髒 `nativeApp` 的 git 樹，build 後可 `git stash`/`git checkout -- apps/host-tauri/src-tauri/tauri.conf.json` 還原。）

---

## 9. 啟動 (Run)

```powershell
# 方式 A（主線）：跑隨 repo 帶的預建 cim-light.exe（免編譯）
Set-Location C:\code\claude\nativeApp
start-dev.bat            # → 轉導 start-dev-tauri.bat → 跑 apps\host-tauri\prebuilt\cim-light.exe
                         #   （fallback 順序：prebuilt → 本機 target build → 舊 sibling）
                         #   並 spawn 原始碼 engine（sidecar\python-engine\engine.py，以 py -3.11）

# 方式 B（開發迭代殼本身）：no-WDAC 機器可直接 dev
Set-Location C:\code\claude\nativeApp\apps\host-tauri
npm install              # 首次 dev 殼才需要
npm run tauri:dev
```

> ⚠️ **方式 A 的前置檢查**：`start-dev-tauri.bat` 會自檢 (1) submodule、(2) `apps\host-tauri\src-tauri\tauri.conf.json`、(3) **可執行的 `cim-light.exe`**（優先預建 `apps\host-tauri\prebuilt\cim-light.exe`）、(4) portal dist 的 `index.html`、(5) 能 import `fastapi`+`uvicorn` 的 Python 3.11。
> 預建 exe 已隨 repo 版控，所以一般**直接就有** `cim-light.exe`。萬一連預建檔都找不到（被刪/被防毒移除），它會「自動退回 Electron 備援」（`start-dev-nowdac-electron.bat`）而不是報錯——這時你看到的是 Electron 視窗，**別誤以為 Tauri 跑起來了**；還原預建檔或依步驟 8 重建即可。其餘前置缺漏（portal dist / engine 相依）會中止並印出修補指令。
> 殼以外一切共用：engine、portal dist、cim-modules、Labeling 都是 runtime 載入。日常只改 portal dist / Python engine / 模組時**不需重編 Rust 殼**；只有改 Rust 殼本身才需回到步驟 8。

---

## 驗證 (Verify)

```powershell
Set-Location C:\code\claude\nativeApp
# 1) doctor：檢查平台側相依/拓樸（期望結尾印出 [OK] 全部通過）
powershell -ExecutionPolicy Bypass -File scripts\win\verify-setup.ps1

# 2) JS 測試（依序跑 shared-protocol 與 host-electron；兩組皆綠才算過）
npm test

# 3) Python 測試（務必用 py -3.11；涵蓋與 repo test:python 相同的兩個目錄）
py -3.11 -m pytest sidecar\python-engine\tests sidecar\python-engine\plugins\labeling\tests
```

> ⚠️ **doctor「通過」≠ Tauri 已建好**：`verify-setup.ps1` **只驗平台側**（git/node/npm、Python 3.11、AI4BI submodule + pip 層、`node_modules`、labeling junction）。它**不檢查** Rust/rustup、MSVC `link.exe`、WebView2、portal dist、簽章憑證，也**不檢查** `cim-light.exe`。所以 doctor 過了是「**必要但不充分**」。一般情況下 Tauri 殼的 **`apps\host-tauri\prebuilt\cim-light.exe` 已隨 repo 帶**，clone 後即存在；若你自行重建過殼，請確認該預建檔（或 `apps\host-tauri\src-tauri\target\release\cim-light.exe`）存在。doctor 對 torch/ultralytics 印 **WARN 屬正常、不是失敗**。
> ⚠️ **不要用 `npm run test:python`**：它走裸 `python`（可能是 `.venv-xanylabeling`，無 pytest），會以混淆的錯誤失敗。Python 測試一律用上面的 `py -3.11 -m pytest ...`。

啟動 app 後，portal 的 catalog 應正確列出 `app-lv` + `sheet-annotation` + `labeling` 等模組，代表 submodule、junction、engine 三者都到位。

---

## 疑難排解 (Troubleshooting)

| 現象 | 原因 | 解法 |
|------|------|------|
| `cargo build` / `tauri build` 報 **`link.exe not found`** / `error: linker 'link.exe' not found` | 缺 MSVC C++ Build Tools（沒裝「Desktop development with C++」workload），或裝 Rust 在前、Build Tools 在後 | 先裝 Visual Studio **Build Tools 2022** 並勾該 workload（步驟 0），開新終端再重試。`where.exe link.exe` 在一般 shell 找不到屬正常，不代表沒裝 |
| `winget is not recognized` | 機器無 winget（精簡/舊映像） | Microsoft Store 安裝「App Installer」，或用步驟 0 表格的直接下載連結逐一安裝 |
| `cim-light.exe` 啟動白屏 / WebView2 相關錯誤 | 缺 WebView2 Runtime（多見於舊 Win10） | 安裝 Microsoft **WebView2 Evergreen Bootstrapper**（Win11 通常已內建） |
| `tauri build` 因**簽章憑證**失敗（找不到 thumbprint `9A91F8C5...`） | cert store 沒有該憑證 | **匯入該憑證**後重建；或**建非簽章版**：把 `apps\host-tauri\src-tauri\tauri.conf.json` 的 `bundle.windows.certificateThumbprint` 設為 `""` |
| `verify-setup.ps1` 報 **FAIL：缺 ai4bi/duckdb/plotly** | 跳過了步驟 6(b) `pip install -e vendor\AI4BI[llm]` | 補跑步驟 6(b)；AI4BI 是 doctor 通過的硬性前置，非選用 |
| 模組目錄空 / `vendor/LV`、`AI4BI`、`cim-modules` 沒內容 | clone 時沒帶 `--recurse-submodules` | `git submodule update --init --recursive` |
| `link-labeling.bat` 報「Labeling source not found」/ portal 看不到影像標註 | `..\ANnoTation` 缺 `plugin.manifest.yaml`（clone 不完整），或重 clone 後沒重掛 junction | 完整重新 `git clone ANnoTation` 到同層，再跑 `scripts\win\link-labeling.bat` |
| `tauri dev`/`build` 抱怨找不到 `frontendDist` / portal 內容 | portal dist 還沒建 | 先跑步驟 7 `npm --prefix apps\portal-react run build`（殼已在本體 `apps\host-tauri`，`frontendDist` 指回同 repo 的 portal dist） |
| 第一次 `cargo build` 很久像當掉 | 正常——大量 crate 首編 | 耐心等（數分鐘～十幾分鐘）；把 `src-tauri\target` 加入防毒排除可加速 |
| `cargo` 偶發 I/O 失敗 / 路徑過長 | 防毒掃 `target`，或 MAX_PATH | `target` 加防毒排除；啟用 Windows long path（`git config --system core.longpaths true` + LongPathsEnabled）；工作目錄勿放太深 |
| `pytest`/`fastapi` 找不到、或測試用到錯的 Python | repo 內 `python` 指向 `.venv-xanylabeling` | 一律用 **`py -3.11`**；**勿用 `npm run test:python`**（走裸 python） |
| 跑了 `start-dev.bat` 卻開出 Electron 視窗 | 找不到可執行的 `cim-light.exe`（預建檔被刪/被防毒移除），腳本自動退回 Electron 備援 | 還原 `apps\host-tauri\prebuilt\cim-light.exe`（`git checkout -- apps/host-tauri/prebuilt/cim-light.exe`），或依步驟 8 重建後覆蓋預建檔，再跑 `start-dev.bat` |
| 步驟 6 `pip install -r` 報 **`UnicodeDecodeError: 'cp950' codec can't decode byte 0xe2`** | `requirements*.txt` 的「註解」含 UTF-8 字元（em-dash `—`、ellipsis `…`），pip（≤24）在檔案無 BOM 時用系統 ANSI 編碼 **cp950**（繁中 Windows）解碼 → 崩。ASCII-only 的英文機器碰巧不會炸 | 裝之前先 **`$env:PYTHONUTF8 = "1"`**（步驟 6 已內建此行）；或升級 pip：`py -3.11 -m pip install -U pip`；或把兩個 requirements 檔的非 ASCII 註解改 ASCII（`-`/`...`）或存成 UTF-8 **含 BOM** |
| `import ai4bi` 報 **`ModuleNotFoundError`**，但 `pip show ai4bi` 顯示「已裝」 | 步驟 6(b) 的 **editable 來源路徑被刪/搬**（常見：指到舊備份資料夾）。editable 只是把該路徑掛進 import 搜尋，路徑沒了 import 就失敗，`verify-setup.ps1` 連帶 FAIL | 重跑步驟 6(b) 指向**存在且穩定**的路徑：`py -3.11 -m pip install -e "C:\code\claude\nativeApp\sidecar\python-engine\vendor\AI4BI[llm]"`（多 clone 共用全域 `py -3.11` 時尤其要指穩定主 clone，勿指臨時/備份夾） |
| `pytest` 兩個 `test_mcp_config` 失敗 / `FileNotFoundError: ...\.mcp.json` | `.mcp.json` 與整個 `.claude/` 都被 **gitignore**，fresh clone 沒有（且 `.claude/mcp.json` **連 `.example` 都沒有**）。**不影響 app 運作**，純 MCP 工具設定的 meta-test | 依「當前 repo 絕對路徑」生成兩檔：`.mcp.json`（以 `.mcp.json.example` 為底、替換 `<YOUR_PROJECT_ROOT>`）與 `.claude/mcp.json`（從可用機器複製）。根本解：repo 補 `.claude/mcp.json.example`，或讓該測試在缺檔時 skip |
| `npm ci` 失敗 / 跑完 `npm install` 後 `package-lock.json` 大幅變動（未改動程式卻變髒） | 加入 `apps/host-tauri` 這個 workspace 後，root `package-lock.json` 未一起重生提交（lockfile 落後於目前 workspace 集合） | 在主 clone 跑一次 `npm install`，把更新後的 `package-lock.json` **commit 進 repo**；之後 fresh clone 的 `npm install` 就不再動 lockfile |

---

## 和 WDAC 的關係

本文件刻意在 **no-WDAC（無強制）機器**上做 `cargo`/`tauri build`/`vite build`——這些「新編譯出來的未簽章 exe」在 WDAC 強制機器上會被擋（`os error 4551`）。
日常開發機 `COLA\hctsa` 是 WDAC 強制，所以它**不在本機 build 殼**，而是跑「在這台 no-WDAC 機器建好（最好簽章）的產物」。
WDAC 的成因與對策**已定論、不需重新調查或提新解**——完整背景見 [`CLAUDE.md`「## WDAC」](CLAUDE.md) 與 [`docs/platform/startup-tauri.md`](docs/platform/startup-tauri.md)。
