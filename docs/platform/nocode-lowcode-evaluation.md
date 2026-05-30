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
