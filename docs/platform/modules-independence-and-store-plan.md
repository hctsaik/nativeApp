# Modules 獨立 repo + 模組商店 + 無環境更新 — 設計提案 v2

> 狀態：**設計討論 v2（已過第一層 5 視角 multi-agent 評審 + 共識修正）→ P0 待實作**。
> 對應 /goal「把 `scripts/module_*` 拆成獨立 repo `nativeApp_modules`（比照 LV/AI4BI），並設計：(1) User 易選模組、(2) 沒 Python/沒環境的 User 如何安裝/更新大型套件（LV/Labeling/AI4BI）」。
> 關聯：[`repo-topology.md`](repo-topology.md)、[`fleet-distribution.md`](fleet-distribution.md)、[`per-tool-dependencies.md`](per-tool-dependencies.md)、[`catalog-source-of-truth-discussion.md`](catalog-source-of-truth-discussion.md)、[`labeling-independence-plan.md`](labeling-independence-plan.md)。
> v1→v2 變更摘要見文末「附錄 A：評審與修訂紀錄」。

## 0. 決議（2026-06-17，含 multi-agent 評審後修正）

### 0.1 掛載與分發（已拍板）
| 決策點 | 結論 |
|---|---|
| **掛載方式** | **git submodule**，掛 `sidecar/python-engine/plugins/cim-modules/`，repo 內部 `modules/module_xxx/`。命中現有 glob `plugins/*/modules/*/plugin.yaml`（[engine.py:667-668](../../sidecar/python-engine/engine.py)）與 dual-root loader（[plugin_loader.py](../../sidecar/python-engine/plugin_loader.py)）→ **engine.py / plugin_loader.py 真零改**（見 §4.3 深度方案）。 |
| **重相依交付** | **隨選下載相依包（dep-pack）**，但**走獨立 binary blob 管線**，不沿用 code-artifact 那套（見 §6，評審揭露結構性不相容）。 |
| **單 repo vs 多 repo** | **單 repo**（5 視角全票）。per-module 選擇靠 registry artifact 粒度（§5），不靠切 repo。 |
| **registry 部署** | code artifact 用**內網一台**即可；雲端待後續，且**在 Ed25519 + publish 認證 + TLS 補完前否決雲端**（資安）。 |
| **商店權限** | **fleet 管理機指派為預設 + 單機自選為退路**，用 channel + RBAC 分層；「單機放寬」**不得**變成關驗章/指向任意 registry（資安硬底線）。 |
| **deprecated 模組** | **不搬入** nativeApp_modules。關鍵事實：010/019/022-025 實體在 **labeling junction（`ANnoTation/modules/`）**內，不在 `scripts/`——v1 盤點誤算。cim-modules 只收 `scripts/` 活躍 CV 模組。 |

### 0.2 第一層評審分數（修訂前）
架構 72 / 分發維運 52 / 資安 52 / 終端 User 58 / DevEx 62。**共識：兩層方向正確；code-artifact 路線（P0-P2）可行度高；dep-pack（P3）與資安需獨立重設計並設為多機部署的前置閘。**

---

## 1. 問題

`scripts/module_*`（第一方 CV 模組）目前**實體住在平台 repo 內**，無法獨立開發/發版/分發。同時 LV(torch~2GB)、Labeling(ultralytics)、AI4BI 體積大，而目標機器**可能沒有 Python、沒有任何環境**。要解：(1) 拆 repo、(2) 易選模組、(3) 無環境安裝/更新且大相依不痛。

## 2. 現況積木（八成已具備）

| 積木 | 現狀 | 用途 |
|---|---|---|
| submodule + dual-root loader | AI4BI/LV 掛 vendor/；`plugin_loader.module_roots()` = `[scripts/] + plugins/*/modules/` | 拆 module 範本、免改 loader |
| engine 自動掃描 | `engine.py:667-668` 掃 `plugins/*/modules/*/plugin.yaml` | 拆出去免改 engine |
| per-tool venv | `core/tool_deps.py`；**frozen 自帶 standalone Python 3.11**（per-tool-dependencies.md §8 已實機驗證） | ✅「沒 Python」已解決 |
| Fleet 分發 | `core/distribution/`（HMAC 簽章）+ `registry_server.py` + `fleet_publish.py`，env-gated | code artifact 分發骨幹 |
| 管理中心 | `management_runner.py` prod 啟用/停用 toggle（**全英文、面向發版者**） | 商店前台要重新包裝 |
| 全家桶 bundle | `make-source-bundle.ps1` → `nativeApp_BundleZip` | 無 git ZIP 安裝路徑 |

> **核心認知**：「沒 Python/沒環境」靠 frozen + 自帶 Python + per-tool venv **已能跑**。真正缺：(a) 拆 repo、(b) 給終端 User 的商店前台、(c) 重相依的**二進位**按需交付（現有 artifact 是 text-only，扛不動 2GB wheel）。

## 3. 架構：兩層分發 + 模組商店

```
第一層（開發者/原始碼）
  nativeApp_modules (github.com/hctsaik/nativeApp_modules)
    modules/module_001..021/  +  modules/_shared/（frame_fit_score 等領域共用碼）
        └─ git submodule ─► plugins/cim-modules/
                          │ fleet_publish.py（每模組 → 簽章 code artifact）
                          ▼
第二層（終端 User/無 git 無 Python）
  registry（catalog + code artifact）          dep-pack blob store（獨立二進位管線，§6）
    ├─ module_002@1.2.0 (code)                  └─ deppack:app-lv (wheelhouse, Range 串流, 逐檔 hash)
    └─ app-lv@1.0.0 (code)
                          │ frozen app 依「使用者勾選」拉取（驗章）
                          ▼
  frozen Electron app（自帶 Python 3.11）
    管理中心「模組商店」頁：未安裝/已啟用/已停用（三態，終端語彙）
```

---

## 4. 第一層：拆 `nativeApp_modules`（submodule）

### 4.1 掛載點與 repo 結構
- 掛載點：`sidecar/python-engine/plugins/cim-modules/`（submodule）。
- repo 結構：
```
nativeApp_modules/
├─ modules/
│  ├─ module_001..005/ module_007/ module_021/   活躍 CV 模組（7 個）
│  └─ _shared/frame_fit_score.py                 跨模組 CV 領域共用碼（從 host scripts/ 移入）
├─ tests/                  純邏輯單元測試（不 import core 的部分）
├─ requirements-dev.txt    開發 lint/test（執行期相依走各 plugin.yaml requires:）
└─ README.md
```
- `.gitmodules` 新增 `[submodule "sidecar/python-engine/plugins/cim-modules"] path=… url=https://github.com/hctsaik/nativeApp_modules.git`。

### 4.2 為何 engine / loader 零改（已驗證）
glob `plugins/*/modules/*/plugin.yaml` → `plugins/cim-modules/modules/module_001/plugin.yaml` 命中；`plugin_loader._find_folder`/`iter_module_folders` 走 `[scripts/]+plugins/*/modules/` 同涵蓋。**掃描與載入零改屬實。**

### 4.3 ⚠️ 反向尋徑：採 labeling 已驗證的深度方案（engine 真零改）
`plugins/cim-modules/modules/module_NNN/` 與 `plugins/labeling/modules/module_NNN/` **物理深度完全相同**，比舊 `scripts/module_NNN/` **深 2 層**。所有「模組反向找 host」的 `parent`/`parents[N]` 一律 **+2**（與 host 端共用碼自身的 `parents[4]` 無關——那些檔留在 host 原地、不受影響）。

**實測要改的 6 處**（grep 驗證，僅這些；engine.py/_make_env **不動**，不引入 `CIM_ENGINE_ROOT`）：

| 檔案:行 | 現況 | 改為 | 取的東西 |
|---|---|---|---|
| `module_001/001_input.py:12` | `.resolve().parent.parent.parent / "tools"` | `.resolve().parents[4] / "tools"` | host `tools/` |
| `module_002/002_input.py:7` | 同上 | `.resolve().parents[4] / "tools"` | host `tools/` |
| `module_002/002_process_test.py:14` | `…/ "tools" / "road.png"` | `.resolve().parents[4] / "tools" / "road.png"` | host demo 圖 |
| `module_003/003_process_test.py:19` | `parents[1] / "frame_fit_score.py"` | `parents[1] / "_shared" / "frame_fit_score.py"` | **改指 repo 內 _shared** |
| `module_004/004_process.py:12-15` | `parent.parent`（=scripts）入 sys.path 後 `from frame_fit_score import` | sys.path 指 `parents[1] / "_shared"` | **改指 repo 內 _shared** |
| `module_021/_config.py:7`、`021_input.py:14`、`021_output.py:15` | `_HERE.parent / "shared" / …`（`_HERE=…resolve().parent`，=module 目錄） | `_HERE.parents[3] / "scripts" / "shared" / …` | host `scripts/shared/` |

- `module_003/004` 引用的 `scripts/frame_fit_score.py` 是 **CV 領域共用碼**（非平台），**隨模組移入 `modules/_shared/`**，讓 cim-modules 自足、且契約面不被它撐大。（grep 證實 module_007 **不**引用它，v1 評審「007 也用」有誤。）
- `road.png` 是 host demo 資源：P0 維持指向 host `tools/road.png`（純資料、非 import，契約測試不擋）；後續可評估隨模組移入以徹底脫鉤。
- submodule 是實體同樹，`.resolve()` **安全**（不像 junction 會跳出）；但仍立規矩：以 `__file__` 當自身錨點者優先 `Path(__file__)`，防未來改 junction。

### 4.4 平台契約（cim-modules 專屬 allowlist）
新建 `tests/test_modules_platform_contract.py`（**不沿用** labeling 的清單，否則「allowlist 必須被用到」測試會雙向變紅）。

**實測（第二層仲裁 grep 全 7 模組）：cim-modules 對 host `scripts/shared` 的真實依賴面只有 2 個檔**——`_config_base`（module_021/_config.py）與 `_help`（module_021/021_input、021_output）。其餘 `_manifest_db`/`ui_components`/`image_widget`/`db_utils`/`log_utils`/`tool_result`/`tool_comms`/`core.*` 目前 **零引用**。故 allowlist 收斂為 **`{_config_base, _help}`**（外加保留 `core` 命名空間供未來，但不納入「必被用到」檢查，以免空 namespace 讓測試紅）。`frame_fit_score` 移入 `modules/_shared/` 後**不算 host 依賴**；`road.png` 是純資料非 import，契約測試不擋。
> v1 曾把 allowlist 列成 10 項（含 ui_components/db_utils… ），第二層仲裁實測證實過大、會讓 `test_contract_allowlist_is_actually_exercised` 立即紅 → 已收斂。

### 4.5 遷移步驟（P0 checklist）
1. **盤點**：活躍模組 = 001-005、007、021（有 plugin.yaml）。`frame_fit_score.py` 隨遷。deprecated 010/019/022-025 **不動**（在 labeling）。
2. **先複製後驗證（難回復步驟前的安全閘，架構視角建議）**：先把模組**複製**到 `plugins/cim-modules/modules/`、套 §4.3 尋徑修正、移入 `_shared/frame_fit_score.py`，跑 `npm run test:python` + MCP golden path **綠**——確認無誤，再做 filter-repo + `git rm` + submodule add 等難回復動作。
3. **建 repo**：`git filter-repo`/`subtree split` 保留 module_* 提交歷史搬入 `nativeApp_modules/modules/`，push GitHub。
4. **掛 submodule**：平台 `git rm` 舊 `scripts/module_*`、`git submodule add` 到 `plugins/cim-modules/`，釘 commit。
5. **scaffold 導向 submodule**（DevEx 阻斷）：`scaffold.py module` 的 `--dest` 預設改為「偵測 `plugins/cim-modules/modules/` 存在就用它，否則 fallback scripts/」；輸出提示加「請到 cim-modules 內 commit/push，再回平台釘 submodule 指標」。README/CLAUDE.md 範例同步。
6. **detached-HEAD 防呆**（DevEx 阻斷）：`preflight-submodules.bat`/`verify-setup.ps1` 增 cim-modules「dirty/detached/落後 origin」檢查；CLAUDE.md「協作規則」加固定流程：改 cim-modules → submodule 內 commit+push → 平台 `git add plugins/cim-modules` 釘指標 → 平台 commit。
7. **bundle/doctor/docs 同步**：`make-source-bundle.ps1` `$mounts` 增 cim-modules（submodule 在全家桶須**實體拷入**，走 submodule 分支非 junction 分支）；`check_submodules()` 納入；CLAUDE.md 首次設定、repo-topology.md 更新。
8. **測試矩陣**：cim-modules repo CI = 純邏輯單元測試；平台 super-repo CI = `npm run test:python` 全套（含 contract）。模組 repo 單獨 clone 不含 `core/`，故整合/contract 只在平台側跑。
9. **熱載照舊**：本機改 submodule 內檔 → `POST /reload` 即生效（不需 commit）；commit/push 是「給別人看到」的另一步——文件要把「跑得動」與「進得了版控」分清楚。

---

## 5. 第二層：模組選擇（模組商店）

### 5.1 per-module 簽章 artifact（fleet 既有）
`fleet_publish.py` 已能把一個工具資料夾打成 HMAC 簽章 artifact。對每個 module/app 套用 → catalog 變「可選清單」。裝置設 `CIM_DISTRIBUTION_SOURCE` 後 `pull_distribution_into_catalog` 驗章寫入。**這條已實作、已實機冒煙。**

### 5.2 商店 UX（終端語彙，藏發版術語）— 終端 User 視角阻斷修正
- 終端 User 只看**三態開關**：`未安裝 / 已啟用 / 已停用（可重新啟用）`。`snapshot`/`publish`/`checks`/`Danger zone` 全收進「進階/開發者」分頁。
- **全繁中、語氣一致**（安裝/更新/啟用/停用）；現有 `Prod: ON / Hidden from Prod` 在商店語境重寫。
- 勾選 = 安裝 + 啟用一氣呵成；取消 = 停用（資料留著）。兩層解耦（裝不裝 vs 顯不顯示）是後端細節，前台一個勾。
- **profile（模組組合）**：主管在管理機定義「產線 A = LV+module_002」一次，批次推給一組機器（解「管 5 台」痛點，§10-Q4）。
- **單一更新入口**：portal 一個「更新」鈴鐺，彙整殼層/模組/重相依三種更新 + 數量紅點 + 「全部更新」。User 不需分辨是哪種更新。

### 5.3 與 catalog 權威關係
不破壞 YAML 權威：商店裝下來的 `plugin.yaml` 就是本機宣告式來源，`tools.sqlite` 照舊 reconcile。商店只是「把 plugin.yaml 從 registry 搬到本機」的傳輸層。

---

## 6. 重相依交付：dep-pack（獨立 binary blob 管線）— 分發/資安視角重設計

> ⚠️ **評審揭露**：現有 artifact 是 **text-only**（`ToolArtifact.content: dict` → `json.dumps`）、**從不落地**（寫 DB → in-memory `exec`）、registry **無串流/Range**、`CIM_WHEELHOUSE` **引擎側從未接線**。所以 dep-pack **不能**沿用 code-artifact 那套，需新管線。

### 6.1 dep-pack 模型
```
deppack:<tool_id>@<dep-fingerprint>
  meta.json（已簽章，小）: { platform_tag, python_tag, size, payload_sha256,
                            requires_fingerprint, wheel_hashes:[{name, sha256}...] }
  payload: wheelhouse 壓縮包（一組 .whl）
```
- **逐檔 hash + --require-hashes**（資安阻斷 B3）：meta 對每個 `.whl` 記 sha256；安裝前逐檔比對；產一份帶 `--hash=sha256:` 的 requirements 餵 pip，杜絕「`--find-links` 無條件裝任何 wheel」。
- **wheel 權威來源**：只接受內部受控鏡像 `pip download` 產出，**禁止裝置自由連 PyPI**；記錄誰產/何時產。
- **ABI 防呆交給 pip**：`platform_tag/python_tag` 僅作商店 UI 預檢（省 2GB 誤下載）；最終靠 pip 對目標 venv interpreter tags 的天然拒絕（手寫字串比對更脆）。
- **prebuilt-venv 模式暫緩**：整個 venv 難逐檔驗、RCE 面大；P0-P4 釘死 wheelhouse-only。

### 6.2 傳輸與落地（解 2GB）
- registry 新端點 `GET /deppack/{id}/{fp}` 支援 **Range/續傳**；裝置端**串流落地 + 邊下邊算 sha256**。簽章只簽 meta（小），payload 靠 sha256 鎖。
- blob **存檔案系統/物件儲存**，DB 只存 meta + 路徑（不要 2GB 塞 SQLite TEXT 欄）。
- **斷點續傳**（終端 User 阻斷）：中斷從上次塊續傳，不從 0；商店顯示「下載中 45% / 已暫停 / 失敗 重試」半裝狀態。

### 6.3 接進 per-tool venv（解 CIM_WHEELHOUSE 未接線）
- `_make_env` 解析「該工具的 wheelhouse 快取目錄」→ 改呼叫 `ensure_tool_deps(deps_module, requires, wheelhouse=<path>)`（目前**沒傳** wheelhouse=，只 fallback 全域 env）。
- wheelhouse 快取與 `.tool-venvs` 都放**裝置級固定位置**（`CIM_DEPPACK_CACHE` / `CIM_TOOL_VENVS_DIR`），**不綁 log-dir**——否則換 log-dir 同時失去 venv 和 wheel，「離線可重用」破功。
- `.cim-deps.json` 指紋加記 `wheelhouse_sha256`：換了 wheelhouse 就重裝，避免「錯 ABI 的 wheel 建出的 venv 被指紋誤判齊備」。
- **離線可重用承諾**寫進 UI 文案：「一次性下載約 2GB（約 15 分鐘），**下載後可離線重複使用**，可暫停續傳。」
- **內網鏡像欄位**：商店設定讓 IT 填 `dep-pack 來源 URL`，全廠從區網拉一次，免每台連外網。

### 6.4 為何不選另兩案
純線上首用 pip（慢網/離線痛、不可控）；全內建多 GB（沒選 LV 的人也被迫扛，違背易選初衷）。隨選 dep-pack 兼顧三方。

---

## 7. 更新策略
| 對象 | 機制 | 現狀 |
|---|---|---|
| module/app 碼 | registry channel(dev/prod) + 新 artifact；`POST /reload` 熱套用 | ✅ |
| 重相依 | dep-pack 換 fingerprint → 商店提示重拉一次 | 本案新增 |
| base 殼層 | **electron-updater**（generic provider：URL+latest.yml+安裝檔） | ⬜ 待辦，**前置=code signing** |
| 無 git ZIP 機 | 取新全家桶重裝 | ✅ 保留為保底 |

- **electron-updater 前置是 code signing**（資安阻斷 B5）：`package.json` 目前只有 `portable` target、無簽章設定，未簽 exe + updater 在 Windows 被 SmartScreen/SmartAppControl 攔；portable 與 electron-updater 搭配尷尬（updater 為 nsis/squirrel 設計）。**P4 拆成 P4a（簽章 pipeline）+ P4b（updater feed）**；簽章未解前 §7 此格不算 ready。
- **ZIP 全家桶的誠實漏洞**（終端 User 阻斷 B4）：全家桶把 LV/AI4BI/Labeling 原始碼**全實體塞入**，走 ZIP 的機器 100% 扛全部模組——對最弱勢 User「不該扛 2GB」跳票。對策：`make-source-bundle.ps1` 加 `--modules` 產**精簡版全家桶**（只含殼層 + 指定模組）。

---

## 8. 路線圖（含資安閘）
| 階段 | 內容 | 前置/閘 |
|---|---|---|
| **P0 拆 repo** | §4.5 全部：複製驗證閘→filter-repo 保歷史→submodule→§4.3 尋徑(+2)→`_shared/frame_fit_score`→cim-modules 契約測試→scaffold 導向→detached-HEAD 防呆→bundle/doctor/docs→測試全綠 | 本期實作目標 |
| **P1 per-module 發布** | `fleet_publish.py` 批次對每 module/app 產 artifact；catalog 顯示完整清單 | 有骨幹 |
| **P0-SEC 資安前置**（多機部署的閘） | dev 密鑰 fail-closed；`/publish` + `/reload` 認證 + channel 寫入分權 + audit；RBAC 新增 `install/uninstall` 且 fail-closed；驗章失敗升級為安全事件（非吞 log） | **任何超出單機 loopback 的部署都必須先過此閘；亦涵蓋 P1 啟用 HTTP registry（`CIM_DISTRIBUTION_SOURCE` 指向非 `local:` 單機來源）之前** |
| **P2 模組商店前台** | 三態 UX、繁中、profile 批次、單一更新入口；走 RBAC install 動作 | P0-SEC |
| **P3 dep-pack** | binary blob 管線（Range 串流 + 逐檔 hash + --require-hashes）；接 `wheelhouse=`；裝置級快取；內網鏡像 | P0-SEC |
| **P4a/P4b auto-update** | code signing pipeline → electron-updater feed | 簽章先行 |
| **P5 強化** | Ed25519（信任模型翻新，見下）、prebuilt-venv、裝置註冊/分批 rollout、Postgres/物件儲存後端、雲端 registry | 全數在 P0-SEC 後 |

> **Ed25519 升級的正確認知**（資安）：`sign/verify` 函式介面相近，但**信任模型必須翻新**——`secret`（對稱、人人可簽）→ `private_key`（只在簽章服務）/`public_key`（裝置只嵌公鑰、絕不嵌私鑰）。「介面不變」在密碼學上是誤導；建議參數正名 `signing_key`/`verifying_key`。HMAC 對稱模型對「分發可執行碼給終端」本質不成立。

## 9. 風險與緩解
| 風險 | 緩解 |
|---|---|
| 搬目錄後尋徑斷裂 | §4.3 +2 深度（labeling 已驗證）+ 複製驗證閘 + cim-modules 契約測試 |
| HMAC 對稱密鑰偽造可執行碼 | P5 Ed25519（裝置只持公鑰）；多機部署前不開放 |
| dev 預設密鑰成 prod 後門 | `get_secret()` 在 frozen/prod 未設密鑰時 **raise**（fail-closed），不回預設值 |
| dep-pack wheel 供應鏈 RCE | 逐檔 sha256 + `--require-hashes` + 受控鏡像、禁連 PyPI；prebuilt-venv 暫緩 |
| 2GB OOM/逾時/斷線 | 獨立 blob 端點 Range 串流落地、斷點續傳、`HttpRegistrySource` 10s timeout 不適用大檔 |
| `/publish`、`/reload` 無認證 | P0-SEC 加 authN/authZ + audit + channel 分權 |
| 安裝可執行碼無 RBAC 詞彙 | P0-SEC 新增 `install/uninstall` action 且 default deny |
| 驗章失敗被吞成 warning | 升級為安全事件：error log + 商店紅色硬擋 + 計數，與「網路錯」分流 |
| frozen 前端 static 未驗算繪 | P0/P2 用 Electron+MCP 截圖驗 iframe（per-tool-dependencies.md §8 已記 start 200 只證 server 起） |

## 10. 開放問題 → 已解（共識）
1. **deprecated 模組**：不搬（在 labeling，非 scripts/）。
2. **單/多 repo**：單 repo。
3. **registry 形態**：內網一台供 code artifact；dep-pack 需鏡像/續傳；雲端在 Ed25519+publish 認證+TLS 後才談。
4. **商店權限**：fleet 指派為預設 + 單機自選為退路，channel+RBAC 分層；單機放寬不得關驗章/換任意 registry。

## 11. 實作現況（as-built）

### P0 拆 repo — ✅ 已完成（2026-06-17，multi-agent 雙層共識後實作）
- [x] 7 個活躍 CV 模組（001-005/007/021）+ `frame_fit_score.py` 移入 `nativeApp_modules`，建獨立 git repo（SHA `93397e2`，origin = github.com/hctsaik/nativeApp_modules）。
- [x] 平台以 **git submodule** 掛 `sidecar/python-engine/plugins/cim-modules/`，`.gitmodules` URL = GitHub、pin SHA `93397e2`；命中既有 glob → engine.py/plugin_loader.py **零改**（除新增缺漏偵測 sentinel）。
- [x] §4.3 反向尋徑 6 處 +2 深度修正（`frame_fit_score`→`modules/_shared/`）。
- [x] `tests/test_modules_platform_contract.py`（allowlist=`{_config_base,_help}`，3 測試）。
- [x] `scaffold.py` `--dest` 預設導向 cim-modules（`_default_module_dest()`）+ submodule commit 提醒。
- [x] detached-HEAD/缺漏偵測：`engine.check_submodules()` + `preflight-submodules.bat` 納入 cim-modules。
- [x] `make-source-bundle.ps1 $mounts`、`repo-topology.md`、`CLAUDE.md` 同步。
- [x] `test_module_roots.py` / `test_orphan_sheet.py` 改用 dual-root 解析（去除硬寫 scripts/ 路徑）。
- [x] **測試全綠**：`npm run test:python` 691 passed / 1 skipped / 1 xpassed；`npm test` 20 passed。
- ⚠️ **唯一待 User 手動的一步**（需 GitHub 認證，我無法代勞）：把本地 `C:\code\claude\nativeApp_modules` push 到 GitHub。指令：
  ```powershell
  gh auth login                          # 或設定 git 認證
  gh repo create hctsaik/nativeApp_modules --private --source C:\code\claude\nativeApp_modules --remote origin --push
  # 若 repo 已存在，改： git -C C:\code\claude\nativeApp_modules push -u origin main
  ```
  push 後平台 submodule（pin 同一 SHA）即可對接 GitHub；fresh clone 用 `git clone --recurse-submodules` 一次到位。
- 平台變更在分支 `feat/extract-cim-modules`（未動 main，待 review 合併）。

### P3 dep-pack 核心鏈 — ✅ 已完成（2026-06-18，「產 wheelhouse 包 + 離線裝進 per-tool venv」）
> 這是 §6 的最關鍵一段：讓「沒 Python/沒環境」的機器,agent/商店把 wheelhouse copy 來後能**離線**裝起重相依。registry blob 端點/續傳/商店 UI 仍屬後續。
- [x] `core/deppack.py`：`build_wheelhouse()`（`pip download`→wheelhouse）、`compute_manifest`/`verify_wheelhouse`（**逐檔 sha256**）、`DepPackManifest`（含 `requires_fingerprint`/`python_tag`/`platform_tag`）、裝置端快取路徑（`CIM_DEPPACK_CACHE`，預設 `.deppack-cache/`，不綁 log-dir）、`prepare_tool_wheelhouse()`（驗章通過才回 wheelhouse；壞掉拋 `DepPackError`）。
- [x] `core/tool_deps.py`：`_resolve_wheelhouse(tool_id, requires)` 優先用「per-tool dep-pack 快取（驗章後 `pip --no-index --find-links`）」→ 退 `CIM_WHEELHOUSE` → 退線上 PyPI；**驗章失敗 fail-closed（不退回連 PyPI）**。`requires_fingerprint` 提為公開,與 dep-pack 共用。**引擎零改**（`_make_env`/`_prewarm` 兩呼叫點自動受惠）。
- [x] `tools/build_deppack.py`：CLI（讀 plugin.yaml `requires:` / `--requires`；跨平台 `--platform/--python-version/--abi`；`--dry-run` 預覽）。
- [x] `tests/test_deppack.py`（20 測試：產包/manifest round-trip/逐檔驗證/竄改·缺·多檔偵測/跨平台指令組裝/`prepare` 三態/與 tool_deps 離線裝 + fail-closed + 無包退線上）。
- [x] `.gitignore` 加 `.deppack-cache/`。**測試全綠**：`npm run test:python` 711 passed。
- 端到端用法：管理機 `py -3.11 tools/build_deppack.py plugins/lv/modules/app-lv --platform win_amd64 --python-version 3.11 --abi cp311` → 把 `release/deppacks/app-lv/` copy 到裝置 `CIM_DEPPACK_CACHE` → 首次啟動 LV 自動驗章 + 離線裝進 per-tool venv。
- ⚠️ 尚未做（P3 其餘）：registry 的 dep-pack **binary blob 端點 + Range 續傳 + 串流落地**（目前靠 agent/商店把 `release/deppacks/<id>/` copy 過去）、dep-pack 簽章（目前靠逐檔 sha256 manifest；簽章升級隨 P0-SEC/Ed25519）、商店「下載中/暫停/重試」UI。

### 其餘階段
- [ ] P0-SEC　- [ ] P1　- [ ] P2 商店　- [x] **P3 dep-pack 核心鏈（產包+離線裝,已完成）** / 其餘 P3（blob 端點·續傳·簽章·UI 未做）　- [ ] P4 auto-update　- [ ] P5

---

## 附錄 A：評審與修訂紀錄（v1 → v2）

第一層 5 視角 multi-agent 評審（各自讀 code 驗證）找出的主要修正：
- **架構（72）**：「engine 零改」對掃描成立，但 v1 §4.3 的 `CIM_ENGINE_ROOT` 對策與之矛盾（`_make_env` 未注入該變數）→ 改採 labeling 已驗證的 +2 深度（engine 真零改）。揪出 v1 漏盤 `frame_fit_score.py` 共用檔、把 deprecated 模組誤算進盤點（其實在 labeling）。
- **分發/維運（52）**：dep-pack 與現有 text-only/DB-snapshot/in-memory-exec 模型結構性不相容；`CIM_WHEELHOUSE` 引擎側未接線；registry 無串流扛不動 2GB → §6 重設計為獨立 binary blob 管線。
- **資安（52）**：HMAC 對稱密鑰分發可執行碼本質不成立；dev 預設密鑰非 fail-closed；dep-pack 無逐檔驗；`/publish`/`/reload` 無認證；RBAC 無 install 詞彙；驗章失敗被吞 → 新增 P0-SEC 閘，設為多機部署前置。
- **終端 User（58）**：2GB 無續傳/無進度/無離線承諾；商店勾選 vs prod toggle 心智打架且英文；管 5 台無 profile；更新入口分裂；ZIP 全家桶仍扛全包 → §5.2/§6.2/§6.3/§7 補續傳+三態 UX+profile+單一更新入口+精簡全家桶。
- **DevEx（62）**：scaffold 產出寫死 scripts/；cim-modules 契約面比 labeling 大、直接沿用會誤殺；模組 repo 無法獨立自測；submodule detached-HEAD 無防呆 → §4.4/§4.5 補 scaffold 導向、專屬 allowlist、測試矩陣、detached-HEAD 防呆。
