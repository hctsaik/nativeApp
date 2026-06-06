# Catalog 事實來源（tools.sqlite vs 宣告式檔）— 討論與決議

> 狀態：**已拍板（2026-06-07）＝走路 1（宣告式檔為權威）**，並已實作完成。
> 本文上半記錄 2026-06-03 的多方討論；§8 為決議與 as-built。
> 觸發點：portal 工具反覆出現 `Missing CIM_SHEET_ID or CIM_PLUGIN_ID`，
> 延伸到「為什麼有兩顆 tools.sqlite、catalog 的事實來源該是什麼」的架構問題。
> 相關：[architecture-restructure-discussion.md](architecture-restructure-discussion.md)（§已點名「3 份 tools.sqlite 漂移」）。

> **決議摘要**：YAML（plugin.yaml + sheet YAML + 新增 `config/seed.yaml`）= 唯一定義權威；
> `tools.sqlite` = per-device 衍生快取，每次 boot 自動重建、不進版控。死的 committed
> `config/tools.sqlite` 已刪除並 gitignore。新增 `engine --rebuild-catalog` 旗標供「砍掉重練」。
> 細節見文末 §8。

## 1. 為什麼會有「兩顆」tools.sqlite

不是「兩個權威打架」，而是**一顆活的 + 一顆死的**：

| | runtime `<log_dir>/data/tools.sqlite` | committed `config/tools.sqlite` |
|---|---|---|
| 角色 | **刻意的「每台裝置狀態隔離」** | `resolve_tools_db_path` 第三順位 fallback（engine.py ~44-50）|
| 誰讀 | dev / frozen / fleet / CLI **全讀這顆** | **任何正常路徑都讀不到**（都帶 `--log-dir` 或注入 `CIM_TOOLS_DB`）|
| 進版控 | 否（`.gitignore` 的 `logs/`）| 是（唯一進版控的 DB）|
| fleet | 每台裝置各一顆 → 狀態互不污染（`start-fleet.bat` 各帶 `--log-dir`）| 無關 |

**考古鐵證**：
- Electron 三條啟動候選全帶 `--log-dir`（`apps/host-electron/src/main.js` ~27-32, ~205-220），dev 解析為 `apps/host-electron/logs` → 實際活 DB 是 `apps/host-electron/logs/data/tools.sqlite`。
- committed `config/tools.sqlite` 內含 **2 筆真實 audit_events**（`hctsa` 2026-05-22 對 module_013 做 prod_disable/enable）→ 證明它的 schema **把「目錄定義表」與「執行期日誌表」混在同一檔**，所以一跑就髒、一髒就被 commit（churn 根因）。
- git 歷史：`config/tools.sqlite` 於 `1b3efd8` 夾帶進版控（非刻意種子），後被 `8d8aa62` 半當種子手改。
- 打包：`/package-source` 模式 A 打的是 **runtime DB**（非 config 那顆）；模式 B 不含 DB；frozen 把 `config/` 打進 exe 卻**仍不被讀**（執行時讀 `<exe>/logs/data/tools.sqlite`）。

> 一句話：**唯一進版控的那顆，正好是唯一沒人讀的那顆。** runtime 隔離是對的設計；committed 那顆是歷史遺留 + churn 來源。

## 2. DB schema 的兩種性質（churn 與決策的關鍵）

- **目錄定義**（變動才有意義、可考慮版控）：`tools` / `tool_versions` / `sheets` / `sheet_tabs` / `plugin_permissions` / `roles`
- **執行期狀態/日誌**（一跑就寫、不該進版控）：`audit_events` / `tool_runs` / `users`（含 token）/ `sqlite_sequence`

兩類混在同一檔 → 任何一次以它為 active DB 的操作都會弄髒版控。這是「DB 進版控 = git churn」的結構性原因。

## 3. 三個 agent 的立場

- **考古**：兩顆 DB 的真相如上；committed 那顆是死檔兼 churn 來源。
- **「SQLite 為單一權威」實作派**：要做到「committed SQLite 當 dev 也讀的權威」，**必須先拆「定義表 / 日誌表」兩顆庫**（否則日誌寫入會持續弄髒版控），並停掉「每次開機 scan+seed+reconcile 覆寫」，改成顯式 `sync` 指令把 YAML/plugin.yaml 寫進權威 DB。誠實指出代價：二進位 DB 無法 review diff、會弱化 no-code 上架流程。
- **裁決派（反對「SQLite 當權威」）**：
  - 可變二進位檔當權威 + 進版控是反模式：PR diff 只有「Binary files differ」（見 commit `857e682`/`8d8aa62`）、無法 merge、churn、定義與狀態混淆。
  - 會**倒退** no-code 上架賣點：scaffold 丟 YAML、`/reload` 熱載、**fleet 簽章簽的是 `*.py + plugin.yaml` 文字**（`fleet_publish.py` ~35-42），不是 DB。
  - 使用者的痛被**錯誤歸因**成「YAML 不該是權威」；真正根因是「一顆沒人讀的死 DB 進版控且混了執行期日誌」。

## 4. 使用者的真需求 vs 手段（裁決派的拆解）

| 訴求 | 真需求？ | 更好的滿足方式 |
|---|---|---|
| 不要 engine.py 寫死 seed | ✅ | 把 seed 抽成**文字檔**（YAML/JSON），engine 讀它 |
| 改了要生效 | ✅ | `/reload` 已能；DB 本來就每次冪等重建 |
| 定義可追溯/可信 | ✅ | **文字檔 git diff 才可 review**；二進位 DB 反而不可 |
| 「以二進位 SQLite 為權威」 | ❌（手段）| 用文字檔當權威即可，DB 當衍生快取 |
| 「不在意 YAML」 | 中性（=不反對）| 與文字檔方案相容，日常不必碰 DB |

## 5. 三條路

1. **宣告式檔為權威 + 刪死 DB + seed 抽文字檔（裁決派推薦）** — 解 churn + hardcode + 改了生效，保住 no-code 上架。
2. **以 committed SQLite 為單一權威（使用者原方向）** — 拆定義/日誌兩庫、dev 改讀 committed catalog、停每次重建、改 sync 指令。較大改動，no-code 流程需調整。
3. **最小** — committed DB 維持進版控但標註「僅參考」，只把 seed 抽成文字檔。動最少，churn/誤解仍在。

**目前傾向**：路 1（精準命中三個真需求、不犧牲 no-code 上架）。但與使用者「DB 進版控、以 SQLite 為主」偏好相反 → **待使用者拍板**。

---

## 6. 路 1 完整實施計畫（使用者詢問：「如果是路 1，之後怎麼進行」）

原則：**宣告式文字檔（plugin.yaml + sheet YAML + 新的 config/seed.yaml）= 唯一定義權威；tools.sqlite = per-device、gitignored 的衍生快取，每次 boot / `/reload` 冪等重建。** 分階段、每階段獨立可驗、可隨時停。

### Phase A — 刪掉沒人讀的 committed DB（零風險、最大止血）
- `git rm sidecar/python-engine/config/tools.sqlite`（任何正常路徑都不讀它；fallback 命中時 engine 會自動新建，`CREATE TABLE IF NOT EXISTS` 已支援）。
- `.gitignore` 加 `sidecar/python-engine/config/*.sqlite` 防再被夾帶。
- 更新 CLAUDE.md / `docs/platform/shared-components.md`：明訂「tools.sqlite 是衍生快取、不進版控」。
- 驗收：fresh clone → `start-dev.bat` → catalog 正常（由 plugin.yaml/sheet YAML 重建）。
- ⚠️ 與既有偏好「*.sqlite 都進版控」衝突 → 需使用者確認（見 §7）。

### Phase B — engine.py 寫死的 seed 抽成文字檔（消滅 hard code）
- 現況：`_seed_static_tools`（engine.py ~395-452）用 inline Python tuple `INSERT` 那些「沒有 plugin.yaml 的工具」（management-center、labelme-dino，及 annotation 系列 sheet 的殘留 seed）。
- 改法：新增 `config/seed.yaml`（或各自 manifest），engine 啟動讀它取代寫死 tuple。新增「無 plugin.yaml 的工具」= 改文字檔，不必動 engine.py，且 diff 可 review。
- 一次性的 legacy UPDATE/rename（~405-414）評估是否還需要；需要的留在 migrations、其餘移除。
- 注意：edge-analysis 已改由 `sheets/edge-analysis.yaml` 提供，不再需要 seed tab。
- 驗收：刪掉 seed tuple 後 fresh DB 內容不變（用 §P0 的 catalog 不變量測試把關）。

### Phase C — 確立「DB = 衍生快取」（多為現況扶正）
- 確認 runtime DB 維持 gitignored（已是）。
- `_scan_and_register_plugins` / `_reconcile_sheets_from_yaml` 維持「每次啟動冪等重建」即可（這正是讓「改了 YAML 就生效」的機制）；P0 的孤兒自動收斂續留。
- 把原則寫進 CLAUDE.md，杜絕未來再有人把 DB 進版控。
- 新增/擴充測試：`tools.sqlite` 刪掉後仍能從宣告式來源完整重建（CI 把關）。

### Phase D — 打包一致化
- `/package-source` 模式 A 不再打 runtime DB（DB 既是快取，讓目標機首啟重建；對齊模式 B）。
- `/package-build`（frozen）的 `engine.spec` 移除 `config/*.sqlite`，catalog 由打包進去的 plugin.yaml/sheet YAML 首啟重建。

### Phase E — 驗證與上線
- clean-room clone 跑一次（確認刪 DB + seed 文字化後 catalog 完整、無孤兒、edge-analysis 可啟動）。
- `npm run test:python` + `npm test` 全過。
- commit + push（沿用快轉 main 流程）。

### 路 1 的代價（誠實）
- 新增「無 plugin.yaml 的工具」從「改 DB」變「改 `config/seed.yaml`」——但這正是消滅 hard code 的目的，且對既有「丟 plugin.yaml/sheet YAML 即註冊」零影響。
- 與「DB 進版控」偏好相反（見 §7 待決）。

## 7. 待使用者決定的點（已於 2026-06-07 拍板，見 §8）
1. **走哪條路**（§5 的 1 / 2 / 3）。→ **路 1**
2. **死的 committed `config/tools.sqlite` 怎麼處理**。→ **刪除並 gitignore**
3. （若路 1）seed 文字檔格式。→ **`config/seed.yaml` 單檔**

---

## 8. 決議與 as-built（2026-06-07，路 1 已實作）

使用者拍板：**YAML 當權威**，但要求 (a) pull 後有方式讓 local SQLite 被更新、(b) 直接刪死 DB、
(c) 確保程式 initial 時 tools.sqlite 會被建起來。對應實作（皆已過 `npm run test:python` 678 passed + `npm test` 16 passed）：

| 訴求 | 落地方式 |
|---|---|
| (c) initial 自動建 DB | **本來就會**：`SQLiteToolAdapter.__init__ → _initialize()` 每次啟動 `CREATE TABLE IF NOT EXISTS` + 掃 plugin.yaml/sheet YAML/seed.yaml。檔案不存在就新建並填好。新增 CI 測試 `test_catalog_rebuilds_identically_after_db_deleted` 把關「刪掉仍能完整重建」。 |
| (a) pull 後更新 local DB | 三層：① 重啟 app（開機自動重掃，最常用）② `POST /reload` 熱套用 ③ 新增 **`engine --rebuild-catalog`** 旗標：boot 前先刪 DB 再重建（砍掉重練，pull 完一鍵保證乾淨）。 |
| (b) 刪死 DB | `git rm sidecar/python-engine/config/tools.sqlite`；`.gitignore` 加 `sidecar/python-engine/config/*.sqlite` 防再被夾帶。 |
| 消滅 engine.py 寫死 seed | 新增 `config/seed.yaml`（static_tools / disable_tools / prod_enable_tools / renames / sheet_tab_deletions），`_seed_static_tools` 改讀它（`_load_static_seed()`）；行為等價、diff 可 review。 |
| 打包一致化 | `engine.spec` 過濾掉所有 `*.sqlite`（不把 dev 機殘留快取打進 frozen exe）；`/package-source` 模式 A 預設不再夾帶 runtime DB（首啟重建；要帶執行期狀態才用 `--include-file`）。 |

**改動檔案**：`engine.py`（`_load_static_seed`/`_seed_static_tools`/`--rebuild-catalog`）、
`config/seed.yaml`（新）、`.gitignore`、`engine.spec`、`core/guidance.py`、
`tests/test_catalog_invariant.py`、`.claude/commands/package-source.md`、CLAUDE.md。
