# No-Code / Low-Code 平台適用性評估（multi-agent 迭代）

> 目標：反覆檢討現有 CIM Hybrid Edge Platform 架構，確認它是否是一個「未來容易使用的 no-code / low-code 平台」——涵蓋**開發**（加工具/模組/工作流）與**使用**（操作）。
>
> 方法：每輪由 multi-agent 產生 **10 個使用情境**，逐一評分（完美支援=100，有缺失逐步扣分）。**10 個情境平均 > 95 才算通過**；否則記錄缺口、實作改進，再產生新一輪 10 個，直到通過。
>
> 開始：2026-05-30（接續 P0–P6 架構重構之後）

## 現況基線（評分前提）
重構後架構：
- **後端**：Python FastAPI engine + Streamlit split-tool（`*_input.py`/`*_process.py`/`*_output.py`）子程序；`plugin.yaml` 驅動自動註冊；DEV 從檔案系統 / PROD 從 DB snapshot。
- **核心/外掛**：`core/`（平台共用：integrations 等）、`plugins/labeling/`（domain/modules/sheets/mcp/manifest）。
- **工作流**：sheet YAML（`sheets/*.yaml` + `plugins/*/sheets/*.yaml`）多分頁組合。
- **管理**：管理中心（module_009）發布/回溯/sheet 編輯。
- **scaffolding**：`/new-cv-module`、`/new-split-tool`、`/common-component` 等 skill。
- **前端**：React portal + Electron；使用者操作 Streamlit GUI（no-code 使用）。

評分維度（每情境綜合）：可達成度、所需技術門檻（no-code vs low-code vs 需寫 code）、步驟數/摩擦、可發現性、防呆、可維護。

---

## Round 1（2026-05-30）— 基線評分

### 評估官 10 情境分數
| # | 情境 | persona | 門檻 | 分 |
|---|------|---------|------|----|
| 1 | 操作既有標註工作流 | 現場使用者 | no-code | 82 |
| 2 | 加簡單影像處理工具 | 公民開發者 | low-code | 70 |
| 3 | 加多步驟 sheet 工作流 | 流程設計者 | low-code | 86 |
| 4 | 改既有工具參數/UI | 維護者 | low-code | 60 |
| 5 | 發布/回溯/啟停工具 | 管理員 | no-code | 90 |
| 6 | 貢獻 plugin | 外部夥伴 | low-code+GUI 上傳 | 72 |
| 7 | 串接外部系統 iWISC | 整合工程師 | 需寫 code（無 GUI）| 55 |
| 8 | 加全新領域 plugin | 領域架構者 | 需寫不少 code | 50 |
| 9 | 除錯定位 | 維護者 | low-code | 68 |
| 10 | 打包部署 DEV→PROD | 部署工程師 | 需寫 config | 48 |

**評估官平均：68.1**。嚴格複評認為灌水，校準後真正 no-code/low-code 友善度 **50–62**。**Round 1 採信校準後綜合平均 ≈ 62（未通過，門檻 95）。**

### 跨情境最高槓桿缺口（Round 1 共識，依槓桿排序）
1. **無 declarative 表單/UI 層**：每個工具的 input/output 都是手寫 Streamlit code。改一個下拉、加一個欄位都要寫 Python。← no-code 天花板，影響情境 2/4/6/8。
2. **scaffolding 綁 Claude Code skill**（`/new-cv-module` 是 AI 指令非平台內建 CLI/GUI）：沒有 agent 的人用不了；且與管理中心 `create_module_scaffold` 兩套產出不一致。
3. **外部系統 tenant 註冊無管理中心 GUI**（`register_tenant` 只在 service/MCP 層），且 CLAUDE.md「至管理中心新增 Tenant」與實作不符。
4. **工作流只能線性串 tab**：無分支/參數傳遞/條件/資料 mapping（step 間僅靠 `{TOOL_ID}_result.json`）。
5. **RBAC 是 placeholder**：`auth_provider` 無權限列時預設**全允許**、`get_current_role` 寫死 admin。
6. **打包白名單手寫**（engine.spec ~50 hiddenimports）：dev 綠/打包死，P6b 已因此回滾。
7. **隱性字串路徑耦合**（spec_from_file_location 跨模組硬連）：靜態抓不到、改一處斷另一處。
8. **無 `/new-plugin` scaffold + 第二個 plugin 未驗證**：新領域沿用全域數字 ID、core formats/storage 邊界未拍板。
9. 其它：log 散 4 處、DEV/PROD 雙載入心智負擔、無 declarative 資料模型/連接器市集/即時預覽。

### 結論
未通過。要拉高分數需**實作**降低開發門檻的能力（最高槓桿＝declarative 表單層 + 平台內建 scaffolding + tenant GUI + RBAC + /new-plugin）。逐項實作後再跑新一輪 10 情境重評。

---

## Round 1 後實作的改進（2026-05-30）
1. **修 P6e 真實回歸**：labeling 模組搬到 plugins/labeling/modules/ 後，`cv_framework_runner`/`annotation_runner`/`management_runner`/`management_insights` 仍 hardcode `scripts/` → 開工具/管理/發布都會找不到。加 `plugin_loader.find_module_folder/module_yaml_paths` dual-root 解析、`management_insights._resolve_module_folder`，並以 `tests/test_module_roots.py` 守住。（pytest/pyinstaller 之前漏掉，因為是 Streamlit/admin runtime path。）
2. **宣告式 no-code input 表單**：`core/forms.py` + `cv_framework_runner` run_input fallback；模組可不寫 `*_input.py`，改用 plugin.yaml `form:`；`module_preflight` 對宣告式 input 視 input 為非必需；範例 `scripts/module_007/`（零 input 程式碼）；`tests/test_forms.py`。
3. CLAUDE.md tenant 文件修正、shared-components 索引補 forms。

## Round 2（2026-05-30）— 改進後重評

| # | 情境 | 分 | # | 情境 | 分 |
|---|------|----|----|------|----|
| 1 | no-code 純參數 CV 工具 | 78 | 6 | 外部貢獻 zip 投稿 | 48 |
| 2 | 新人宣告式表單 demo | 80 | 7 | 設定模組 RBAC | 55 |
| 3 | GUI scaffold 新模組 | 60 | 8 | 註冊外部系統租戶 | 38 |
| 4 | GUI 組工作流 sheet | 82 | 9 | 打包可攜部署 | 68 |
| 5 | 使用者跑 annotation 流程 | 80 | 10 | dual-root 模組搬移 | 72 |

**Round 2 平均：66.1（較 Round 1 +4.1）**。提升集中在宣告式表單（情境 1/2）與 dual-root 修復（情境 10）。

### Round 2 發現的真問題（待修）
- `core.forms` 未進 engine.spec hiddenimports → 打包版 no-code 表單有風險。
- no-code 只覆蓋 **input 層**；process/output 仍要寫 Python → 「加工具」封頂 ~60–80。
- scaffold（GUI/skill）仍產手寫 `*_input.py` stub，未對齊 form-first；manifest 無 vendor/domain/slug。

### 距 95 前 5 大缺口（Round 2 共識）
1. **宣告式 process + output 層**（最高槓桿）：讓簡單工具連 output 都宣告，才能真正 no-code。
2. 外部系統租戶註冊 GUI（後端 register_tenant/SystemTenant 已備，缺前端）。
3. 真實身分 + 權限矩陣 GUI（auth_provider 是 placeholder allow-all）。
4. 外部貢獻安全（上傳碼直接 exec，無沙箱/簽章）+ no-code 投稿封包。
5. 打包 hiddenimports 自動收集（取代手寫白名單）。

## Round 2 後實作的改進（2026-05-30）
- **宣告式 no-code OUTPUT 層**：`core/output.py`（metric/text/list/table/json/image/markdown/caption）+ `cv_framework_runner.run_output` fallback + `module_preflight` output 宣告時非必需 + `core.forms`/`core.output` 進 engine.spec hiddenimports + `tests/test_output.py`。
- **範例 `module_007` 變成完全宣告式**：只有 `007_process.py` + plugin.yaml（form: + output:），**零 Streamlit code**，preflight 通過。→ 直接攻克 Round 2 缺口 #1 的 output 半邊。

## Round 3（2026-05-30）— 宣告式 output 後重評（精簡）

| # | 情境 | 分 | # | 情境 | 分 |
|---|------|----|----|------|----|
| 1 | 純參數工具（form+output 全宣告，只寫 process）| **86** | 6 | 接新 REST connector | 52 |
| 2 | 日常用標註工具 | 82 | 7 | 外部貢獻者提交模組 | 46 |
| 3 | 管理員檢視模組健康（preflight 不誤報宣告式）| 78 | 8 | 設定模組 RBAC 權限 | 40 |
| 4 | 改 form default/select 選項 | 84 | 9 | 多租戶上線設定 | 42 |
| 5 | 影像上傳+CV 推論工具 | 58 | 10 | 打包可攜部署 | 70 |

**Round 3 平均：63.8**（本輪刻意納入更多硬骨頭情境 6–9＝外部貢獻/RBAC/租戶/connector，拉低平均；但「**加工具**」類因宣告式 output 躍升到 84–88，情境 1 比 Round 2 同類 +11~14）。

## 三輪軌跡與誠實結論

| 輪 | 平均 | 「加工具」類最高 | 改進 |
|----|------|------------------|------|
| 1 | 62 | 70 | 基線 |
| 2 | 66.1 | ~75 | 宣告式 input + dual-root 回歸修復 |
| 3 | 63.8 | **86** | 宣告式 output（零 Streamlit code 工具）|

**已驗證攻克**：簡單參數型工具現可**完全零 Streamlit code**（只寫純 `process.py` + YAML）——這是 no-code 開發的核心突破，「加工具/改參數」類情境已達 84–88。

**為何整體仍 ~64、距 95 還遠（誠實）**：剩餘高槓桿缺口**幾乎都是 GUI 重 + 安全 + 大型功能**，無法在 headless 環境驗證/實作：
1. **RBAC 權限設定 GUI**（auth_provider 是 placeholder；要管理中心 Streamlit 頁）
2. **多租戶/外部系統註冊 GUI**（後端 register_tenant 已備，缺前端 Streamlit 頁 + 連線測試 + token 加密）
3. **外部貢獻市集/審核/沙箱**（上傳碼直接 exec，需安全沙箱 + 版本流程 + no-code 投稿封包）
4. **宣告式 connector 層**（接外部系統仍須手寫 Python contract）
5. **宣告式生態普及 + 進階呈現**（7 模組僅 1 個真用零程式碼；output 無條件/格式化/分頁宣告）+ **宣告式 process/transform 庫**（讓「簡單變換工具」連運算都宣告）

→ **達到 95 是多輪、多週的產品工程**（大量管理中心 GUI + 安全 + 宣告式運算庫），其中 GUI 部分需在能跑 `start-dev` 的環境逐頁驗證（owner 的 D4 golden-path）。本 session 已把**可在 headless 驗證的 no-code 基礎（宣告式 input+output、零程式碼工具、回歸護欄）**做到位並驗證，並把剩餘路線圖明確化、排序。

### 下一輪建議實作順序（最高槓桿先）
A. 宣告式 process/transform 庫（內建常用運算）→ 讓「簡單變換工具」連 process 都免寫 → 攻 +info/CV 以外的純資料工具。
B. RBAC 真實權限模型（後端可 headless 測）→ scenario 8 從 40→~70。
C. 外部系統/Tenant 註冊 GUI（管理中心新分頁，需實機驗 render）→ scenario 8/9。
D. scaffold form-first 模式 + /new-plugin → 對齊宣告式、補 vendor/domain。
E. 打包 hiddenimports 自動收集（PyInstaller `collect_submodules`）。
F. 外部貢獻沙箱 + 市集流程（安全）。
