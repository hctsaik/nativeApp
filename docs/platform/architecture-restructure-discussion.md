# 平台架構重構 — Multi-Agent 討論記錄

> 目的：把共用功能（DB、Log、library、common code）統一抽出到單一位置，讓 Labeling 以外的功能也能共用並容易被發現參照；同時把「跟 Labeling 直接相關的」（code/config/docs）集中在一處，將 Labeling 視為平台上的一個（重要）plugin。
>
> 方法：多角色 agent 逐輪討論「現有架構與資料夾結構的問題、如何讓平台更易維護」。**每一輪都記錄；未達共識則列出待澄清點，進入下一輪；直到共識為止。**
>
> 開始日期：2026-05-30

---

## 0. 現況快照（討論的事實基礎）

由 repo 實際盤點（2026-05-30）：

### 0.1 後端核心 `sidecar/python-engine/`
- **三套疑似責任重疊的套件**：
  - `annotation/`（40 個 .py）— core / storage / formats / integrations / domains / tools / adapters
  - `cim_annotation/`（15 個 .py）— connectors / tests
  - `cim_platform/`（3 個 .py）— connector / tenant
- 頂層散落 `management_*.py` ×6（insights / oracle_store / package_importer / schema / store / use_cases）、`plugin_loader.py`、`plugin_registry.py`、`auth_provider.py`、`engine.py`
- `scripts/`：module_001~026 各模組；另有 `scripts/shared/`、`scripts/sheets/`、`scripts/workflows/`、`scripts/docs/`
- **`sheets/`（engine 頂層）與 `scripts/sheets/` 並存**，職責不清
- **巢狀垃圾目錄**：`sidecar/python-engine/sidecar/python-engine/scripts/module_017`（疑似誤建殘留）

### 0.2 共用碼現況
- `scripts/shared/` 已有 `_manifest_db.py`、`_data_connector.py`、`_help.py`、`ui_components.py`、`image_widget.py`
  → 但定位在「Streamlit 工具層」，非平台級 library
- **20 個 module 各自有 `_config.py` 重複實作 `CIM_LOG_DIR` / DB 路徑邏輯**（DB、Log 設定碼重複 20×）

### 0.3 DB / Log 散落
- Log 目錄至少 4 處：`apps/host-electron/logs`、`sidecar/python-engine/logs`、`logs/`、`tmp/cim_log`
- sqlite DB 多處：`tools.sqlite`、`manifest.sqlite`、`annotation.sqlite`、`catalog.sqlite`、`edge_records.sqlite`…（散在 logs/、config/、workspace/）

### 0.4 文件
- 重複：`docs/ARCHITECTURE.md` vs `docs/platform/ARCHITECTURE.md`、`docs/AI_CONTEXT.md` vs `docs/platform/AI_CONTEXT.md`、`docs/system-flow.md` vs `docs/platform/system-flow.md`
- Labeling 相關文件散落 `docs/`（ANNOTATION_XANYLABELING、Annotation_Platform_Interface、sync-back-viewer-spec…）與 `docs/modules/`

### 0.5 其它
- `mcp/`：annotation_mcp / cim_gui_mcp / platform_mcp（三個 MCP server）
- `packages/`：shared-protocol / source-code-packager（JS 共用）

### 0.6 Round 1 後修正的事實
- 巢狀 `sidecar/python-engine/sidecar/python-engine/scripts/module_017` **確實存在，但全為空目錄、無任何檔案**（故以 Glob 比對檔案會找不到）→ 純殘跡 cruft，可安全刪。
- `cim_platform/` 被 **`annotation/` 反向 import 8 處**（`annotation/services.py:35` 等），是「外部系統契約」**唯一活躍**實作（並非 0 引用——module 層 0 引用，但 annotation 套件內大量依賴）。
- `cim_annotation/` 為半死套件：全 repo 僅 `scripts/module_017/017_process.py:26` 用到其 `label_ops`。
- 模組間用 `spec_from_file_location` 跨資料夾載入彼此 `_config.py`（如 `012_input.py:24-28` 載入 `module_016/_config.py`）→ **字串路徑的隱性橫向耦合，靜態分析抓不到**。
- import 契約靠 runner（`sheet_runner.py:12-13` 等）`sys.path.insert(0, ENGINE_DIR)`：頂層套件位置 = import 契約。
- `engine.spec`（PyInstaller）`datas` + `hiddenimports` 是**手寫白名單**（列了 40+ 個 `annotation.*`）→ 搬套件必同步改，且**只有 `/package-build` 才驗得出來，dev 模式測不到**。

---

## Round 1（2026-05-30）— 四視角獨立分析

### A. 核心架構師（基礎設施抽離）
- **問題**：三套 connector 套件（cim_platform 活/cim_annotation 死/annotation.integrations 實作）範式衝突；平台基礎設施散在 engine 頂層扁平 module；DB/Log/env 路徑邏輯複製 21 份（根因＝無權威 `paths/env` 模組）；3 份 `tools.sqlite` 漂移；`scripts/shared/_manifest_db.py` 是乾淨 DAL 卻被鎖在 Streamlit 工具層。
- **提案**：新建單一 `cim_core/` package（paths/env/logging/config/db/auth/plugins/integrations），core 不依賴 plugin、plugin 只依賴 core 契約；Labeling 收進 `plugins/labeling/`。可發現性靠單一 entry + README index + `__init__` 匯出 + import-linter 強制邊界。
- **遷移**：三波——①先建 paths/env/config helper 與舊 `_config.py` 並存，逐一委派；②`cim_platform`→core、auth/loader/registry→core，用 shim 轉發；③最後才整批搬 annotation+scripts 進 plugins/labeling（牽動 loader 掃描、sys.path、spec）。

### B. Plugin 邊界 / Labeling-as-plugin
- **問題**：Labeling 領域邏輯散在 annotation/cim_annotation/cim_platform；Labeling 與非-Labeling module 混在 `module_001~026` 平坦數字命名空間；真正耦合是「隱性的」（共用 sqlite + scripts/shared，非 import）；Sheet 一式三份（sheets/、scripts/sheets/、engine.py seed）；Labeling 文件撒在 4 個 docs 目錄；MCP 邊界與 code 邊界沒對齊；命名與真實歸屬相反（cim_annotation 其實全是 Labeling、cim_platform 其實是平台共用）。
- **提案**：`plugins/labeling/` 單一樹收斂 domain/integrations/modules/sheets/mcp/tests/docs；用 `plugin.toml` manifest 宣告對 core 依賴與提供項；module 改語意命名 + `_legacy_ids.toml` 對映；engine 改掃 `plugins/*/plugin.toml`，刪 seed hardcode；廢棄模組移 `_deprecated/`。

### C. 開發者體驗 / 可發現性
- **問題**：三套套件無入口說明必踩雷；共用 DB/Log/config 散在 20 份 `_config.py`(1226 行)；共用 DB 路徑與 DAL 被切兩半；共用 UI 靠動態 `importlib` 載入→IDE/grep 全失效；**CLAUDE.md 對 Python 共用功能完全沉默**；文件三處重複且已漂移（ARCHITECTURE 889 vs 791 行）；sheets 兩處並存自相矛盾；`cim_` 前綴用得不一致放大「該用哪個」焦慮。
- **提案**：單一 `cim_core/`（正常 import，含 storage/config/ui，`__all__` 明確匯出）；建 `docs/platform/shared-components.md` 權威 index 表（能力→路徑→import 範例）；每個共用模組頂部 docstring+snippet；**CLAUDE.md 新增「共用功能在哪」一節（最高槓桿、零成本）**；docs 去重保留 `docs/platform/` 為權威、先 diff 合併 98 行差異再刪重複。

### D. 務實遷移派 / 風險守門人
- **真該修**：巢狀空目錄（純 cruft）、`cim_annotation` 半死套件收斂、文件去重。
- **先別碰（地雷）**：20 份 `_config.py` + 跨資料夾 `spec_from_file_location`（字串路徑、無靜態分析、搬移即斷鏈）；annotation→cim_platform 8 處依賴是設計問題不該靠搬資料夾解。
- **警示**：搬套件會碎 `sys.path` 契約（多個 runner 各自 hack）；`engine.spec` 手寫白名單必爆且**只有 package-build 驗得出**（dev 綠、打包死）；勿動 `_make_env()` env 名稱（30+ 檔的隱形 ABI）；勿藉重構刪廢棄模組（022-025 是近期 iWISC 成果）；勿改 x-anylabeling 啟動方式（WDAC）。
- **最小路徑**：Step0 純文件索引（先達成「知道共用碼在哪」零風險）→ Step1 收斂 cim_annotation → Step2 建 `cim_core` namespace **alias 不搬檔**（re-export/sys.modules alias，可隨時回滾）→ Step3 真要搬才逐套件搬且當場跑 package-build。
- **核心質疑**：擁有者目標「共用碼單一位置」是否「物理搬移」才算？還是「邏輯索引 + namespace alias」就達成、且風險低 10 倍？

---

## Round 1 綜合 — 共識 vs 待澄清

### ✅ 已達共識（4 方一致）
1. **`cim_annotation/` 是半死套件**，應收斂（唯一外部使用者 module_017 的 `label_ops`）。低風險、優先。
2. **文件重複必須去重**，收斂單一 source of truth（先 diff 合併 ARCHITECTURE 差異再刪）；保留 `docs/platform/` 為平台權威目錄。
3. **20+ 份 `_config.py` 重複 DB/Log/path 邏輯**是真問題，根因＝缺權威 paths/env/config 模組。
4. **概念上**應有「單一平台 core 共用層」+「Labeling 視為 plugin 集中」。
5. **可發現性**需要：單一入口 + 權威 index 文件 + **CLAUDE.md 明確指路**（一致認為這是最高槓桿、最低成本，應最先做）。
6. **遷移必須漸進、shim/alias 過渡、每步 test-gated**，嚴禁一次大爆改。
7. **第一步**（零/低風險、高即時收益）：文件去重 + CLAUDE.md「共用功能在哪」一節 + 收斂 cim_annotation + 刪巢狀空目錄。
8. **`/package-build` 是套件搬移的唯一驗證關卡**（dev 模式測不到 spec 破壞）。

### ❓ 待澄清（Round 2 焦點）
- **Q1（核心分歧）**：「共用碼單一位置」要**物理搬移**到 `cim_core/`+`plugins/labeling/`，還是**邏輯索引 + namespace alias**（不搬檔）就足夠？務實派主張後者風險低 10 倍且同樣「知道在哪」；其餘三方傾向物理收斂。
- **Q2 整合範式**：平台 core 契約要採 `cim_platform` 的 Platform-Dictated（get_ant_list）還是 `cim_annotation` 的 Pull/Push？未來非-Labeling 功能（BI/QC）走哪種？決定 `cim_core/integrations` 收哪套、刪哪套。
- **Q3 core 邊界畫在哪**：annotation 的 formats/storage 要上提到 core（供其他影像 plugin 重用）還是留 plugin？過早抽象 vs 假歸屬。
- **Q4 命名拍板**：`cim_core`(新) vs 沿用 `cim_platform`(殼) vs 無前綴？需一次定調寫進 CLAUDE.md 命名規範。
- **Q5 module 數字 ID**：資料夾語意改名 + 對映層 vs ID 字串永久凍結為 `module_NNN`（資料夾改名、DB/log/env 的 ID 不動）？
- **Q6 scripts/ 要不要搬**：要不要做第三波（搬 scripts 進 plugin，最高風險），還是只抽 cim_core、scripts 留原址先拿 80% 收益？
- **Q7 scripts/sheets/ 去留**：`annotation_workflow/`、`edge_analysis/`、`pipeline_sheet.py` 是死碼還是在用的 pipeline？影響「唯一 sheet 來源」說法。
- **Q8 owner 政策**：是否接受「每次套件搬移強制跑 `/package-build`」與「過渡 shim 保留期限」？

---

## Round 2（2026-05-30）— 兩陣營交叉辯論（結構派 vs 務實派）

### 補充查證（Round 2 期間）
- `from annotation` / `from cim_platform` 散佈 **41 檔 87 處**（物理搬移的 import 爆炸面比 Round 1 估的大一個量級）。
- `load_module_dev` 用 `glob("module_*")` 比對 `plugin.yaml` 的 `id` 定位資料夾 → **資料夾名與 plugin_id 已解耦**（間接層存在）；但 PROD（`CIM_DEV_MODE=0`）從 DB snapshot exec，不碰檔案系統。
- `CIM_DEV_MODE` **不繞過打包驗證**：它只切換「檔案系統 vs DB snapshot」載入源；PyInstaller bundle 仍受 `engine.spec` 白名單約束 → 結論不變：**spec 破壞只有 `/package-build` 驗得出**。
- 數字 ID 深埋：`annotation_runner.py` 用 `CIM_MODULE_ID` 組 `f"module_{ID}/{ID}_runner.py"`；各 `0XX_input/process/output.py` 檔名含數字；`_config.py` 用 `module_012.json`；**module_014 直接複用 `module_012_classifications_*` 路徑（跨模組硬連）**。改 ID 格式＝動檔名+runner 字串+設定檔+打包四處，且**零測試覆蓋**。
- `engine.py` 掃描根寫死 `ROOT_DIR / "scripts"`、`ROOT_DIR / "sheets"`；`_config.py` 用 `parents[4]` 算 PROJECT_ROOT → 搬 scripts 目錄層級一變就全錯。

### 結構派（綜合架構師+Plugin+DX）的讓步與主張
- **讓步**：①撤回「第一步就搬套件樹」，承認物理搬 annotation 當下 ROI 為負（spec 白名單＋dev 綠打包死）；②承認 `spec_from_file_location` 跨資料夾互載是地雷，凡涉及 module 資料夾改名/搬移一律降級為「最終才做且需專屬 test 護欄」。
- **Q1**：擁有者四目標「沒有一個字要求物理單一資料夾」，邏輯收斂達成 90%。物理搬移僅在三條件全過時做：(a)單一消費者 (b)不觸 spec/sys.path 或可被單一 test 覆蓋 (c)可發現性收益>風險。「現在物理做」＝刪空殼/刪 legacy scripts/sheets/收斂 cim_annotation；「絕不物理搬」＝annotation 與 scripts/module_* 整支。
- **Q2/Q3**：plugin 邊界用 **manifest 宣告**而非目錄牆；core＝被≥2 plugin 消費者（今天具體＝cim_platform + tools/ 的 db/log utils），annotation 只 labeling 用→屬 plugin。
- **Q4/Q5/Q6**：命名統一與數字 ID 改名都「最終才做、存量不動」；scripts 不搬，靠 plugin.yaml `domain` 標籤 + index 宣告歸屬。
- **關鍵新貢獻（兩派都接受）**：
  - **打包護欄 test**：解析 `engine.spec` 的 hiddenimports，逐項 `importlib.import_module` → 把「只有 package-build 驗得出」前移成 dev 可跑單測。
  - **路徑契約 test**：掃全 repo 的 `spec_from_file_location(字串路徑)`，assert 目標檔存在 → 字串依賴變 test 可見，搬移即紅燈。
  - **namespace alias 過渡**：最終做 core 聚合時用 `sys.modules` alias 讓新舊 import 與 spec 白名單同時有效，逐步拆 alias。

### 務實派的讓步與主張
- **讓步**：①承認 end-state 應只剩**一個** annotation 套件、`cim_annotation` 要物理消失（不爭）；②承認 20 份 `_config.py` 重複骨架是真債、alias 救不了，必抽共用 helper；③接受 import-linter/manifest 邊界契約（但先用於「凍結現狀防腐」，非立刻搬家發令槍）。
- **Q1 階段門檻**：L0 索引→L1 凍結(契約+alias)→L2 抽共用 helper→P1 物理(低風險:刪 cim_annotation/空殼)→P2 物理(高風險:annotation→core，**僅當 alias 已是唯一 import 路徑且 package-build 連過 3 次**)。原則：「物理搬移是**兌現**邏輯收斂，不是**探索**收斂」。
- **紅線（擋下結構派想現在做的）**：擋「現在物理搬 annotation→core」、擋「現在改數字 ID→語意名」（零測試覆蓋＋014 跨模組硬連會斷）、擋「現在搬 scripts 重組 plugin 樹」、擋「先發明統一 connector framework」。

### Round 2 結論：已收斂的共識（兩派一致）
1. **現在物理只動**：刪巢狀空目錄、刪/封存 legacy `scripts/sheets/`、收斂 `cim_annotation/`（確認零活躍引用後併入 `annotation/integrations` 或刪）。
2. **「Labeling 集中」先用邏輯達成**：plugin.yaml `domain:labeling` 標籤 + `plugins/labeling/plugin.manifest.yaml`（純宣告、零 import 風險）+ 權威 index，**實體檔案留原位不搬**。
3. **`annotation/` 與 `scripts/module_*/` 物理不動**（41 檔 87 處 import + spec 白名單 + parents[4] + spec_from_file_location）。
4. **20 份 `_config.py`**：抽 `scripts/shared/_config_base.py`（或 cim_core 等價），各檔改為委派、只留自己的 `_DEFAULTS`；分批 commit、每批 test。
5. **數字 module ID 凍結**：發現性靠 index + plugin.yaml metadata，不靠資料夾/ID 改名。
6. **整合範式**：凍結 `annotation/integrations/contracts.py` 為唯一對外契約，舊 connector 標 deprecated，不發明第三套。
7. **可發現性最高槓桿先做**：文件去重（保留 docs/platform 權威）+ CLAUDE.md「共用功能在哪」一節 + 權威 index 表。
8. **兩個護欄 test**（spec hiddenimports 可載入、spec_from_file_location 目標存在）作為任何後續搬移的安全網，盡早加入。
9. **core 物理聚合 + 套件/ID 改名（S5/P2）一律延後**，且須 alias 已唯一化 + `/package-build` 連過數次才可進行。

### 收斂後的最小路線圖（兩派共同認可）
| 階段 | 交付（對應擁有者目標） | 風險 | 驗收 |
|------|------|------|------|
| **S0** 文件去重 + CLAUDE.md 指路 + 權威 index 表 | 目標2 可發現性 | 極低 | 文件 review；無程式碼變動 |
| **S1** 刪巢狀空目錄 + 刪/封存 legacy `scripts/sheets/` + 加兩個護欄 test | 目標4 可維護 | 低 | test:python 綠 + package-build 能啟動 |
| **S2** 抽共用 `_config_base`/paths/env helper，20 份 `_config.py` 委派（保留各自 `_DEFAULTS`） | 目標1 共用單一處 | 中 | 每批 5 檔跑 test:python，分批可回滾 commit |
| **S3** import-linter 邊界契約 + namespace alias（`cim.core`/`cim.annotation`） | 目標2+4 | 低（只加不刪） | 契約測試新增即綠 |
| **S4** 收斂 `cim_annotation`（證明零活躍引用後刪/併入） | 目標3+4 | 中 | grep 引用面 + test:python + package-build |
| **S5（延後/待 owner）** 物理 annotation→core + 套件命名統一 (+ 視 owner 決定是否改 ID 格式) | 目標1+3 | 高 | alias 已唯一化 + spec 同步 + package-build 連過 3 次 |

→ 兩派一致：**S0–S4 已達成擁有者 4 目標的「實質」；S5 是「美學/長期兌現」，非必要前置。**

### 仍未達共識（本質為 owner 價值/時程判斷，需擁有者拍板）
- **D1「集中」的定義**：「Labeling 都在同一個地方」是指**物理同一目錄**，還是**邏輯可發現+索引指路**就夠？（路線分水嶺）
- **D2 S5 是否必做**：物理把 annotation→core + 套件改名，是「遲早要做的維護投資」還是「alias 穩定後非必要的美學」？取決於 owner 對「未來會不會有第 2、第 3 個 plugin」與維護人手的預期。
- **D3 module ID 格式**：數字 ID 凍結是否長期可接受？（與既有「Module ID 重設計計畫」想改 vendor_domain_slug 的想法衝突——Round 2 證明改名高風險+零測試覆蓋，需 owner 重新權衡「可讀性 vs 穩定性」）
- **D4 速度 vs 風險**：要「一次到位乾淨 end-state（高風險快）」還是「漸進、每步可回滾（低風險慢）」？

---

## Round 3（2026-05-30）— Owner 拍板 + 最終共識

### Owner 對 D1–D4 的決定
- **D1 = 物理集中到 `plugins/labeling/`**（不是只做邏輯索引）。→ 最終結構確定要物理收斂。
- **D2 = 明確要做 S5**（物理把 annotation 搬進 core + 套件改名），當成長期目標。
- **D3 = 凍結數字 ID + 補 metadata**（資料夾/檔名/ID 字串維持 `module_NNN`，可讀性靠 plugin.yaml 的 vendor/domain/slug + index）。→ 既有「Module ID 重設計（vendor_domain_slug）」想法**擱置**：rename 高風險且零測試覆蓋。
- **D4 = 漸進、每步可回滾**。

### 為何這組決定是自洽的（分歧收斂點）
務實派 Round 2 對「物理搬 annotation」的紅線，本來就**不是「永不」，而是「需 alias 已唯一化 + `/package-build` 連過數次才可做」**（其 P2 條件）。Owner 選的 **D2（要做）+ D4（漸進可回滾）** 正好落在這個條件內 → 兩派紅線與 owner 目標**不再衝突**：end-state 是物理（結構派要的），但用務實派的階段門檻與護欄到達。**至此達成方向性共識。**

### 最終共識：目標 end-state
```
sidecar/python-engine/
├── engine.py / engine.spec            # 平台入口（spec 白名單隨搬移同步）
├── core/                              # 平台共用層（被 ≥1 plugin 共用的基礎設施）
│   ├── paths.py / env.py / config.py / logging.py   # 取代 20 份 _config.py 骨架
│   ├── db/        (connection, manifest DAL, management)
│   ├── integrations/ (connector, tenant ← cim_platform)
│   ├── auth/      (← auth_provider)
│   └── plugins/   (loader, registry, contracts ← plugin_loader/registry)
└── plugins/
    └── labeling/                      # Labeling 物理集中於此（D1）
        ├── plugin.manifest.yaml       # 宣告對 core 依賴 + 提供 modules/sheets/mcp
        ├── domain/                    # ← annotation/（core/formats/storage/adapters/services）
        ├── integrations/              # ← annotation/integrations（唯一 connector 契約）
        ├── modules/module_NNN/        # ← scripts/module_*（資料夾名維持數字 ID，D3）
        ├── sheets/                    # ← sheets/annotation.yaml（唯一權威）
        ├── mcp/                       # ← mcp/annotation_mcp
        ├── tests/                     # ← tests/annotation + 各 module *_test
        └── docs/                      # ← 所有 Labeling 文件集中
```
原則：`plugins/* → core/*` 單向依賴，由 import-linter 強制；資料夾/ID 字串凍結為 `module_NNN`，可讀性靠 metadata + index。

### 最終共識：漸進路線圖（兩派 + owner 共同認可）
每階段＝獨立 commit、`npm run test:python` 綠、**凡涉及套件/目錄物理搬移必跑 `/package-build` 確認可啟動**、可回滾。

| Phase | 內容 | 風險 | 關卡 |
|------|------|------|------|
| **P0** 文件去重（保留 docs/platform 權威，先 diff 合併 ARCHITECTURE 98 行差異）+ CLAUDE.md「共用功能在哪」一節 + 權威 index 表 | 極低 | 文件 review |
| **P1** 刪巢狀空目錄 + 刪/封存 legacy `scripts/sheets/` + 加**兩個護欄 test**（① 解析 engine.spec hiddenimports 逐項 importlib 可載入 ② 掃全 repo `spec_from_file_location` 字串路徑 assert 目標存在）| 低 | test:python + package-build |
| **P2** 抽 `core/`（或先 `scripts/shared/`）的 `_config_base`/paths/env/log helper；20 份 `_config.py` 改委派、只留 `_DEFAULTS` | 中 | 每批 5 檔跑 test，分批可回滾 |
| **P3** import-linter 邊界契約 + namespace alias（`core.*` / `labeling.*` 指向現位置，新碼用新名、舊名保留相容） | 低（只加不刪）| 契約測試即綠 |
| **P4** 收斂 `cim_annotation`（證明零活躍引用後刪/併入 `annotation/integrations`）| 中 | grep 引用面 + test + package-build |
| **P5** 物理建立 `core/`，搬共用基礎設施（cim_platform connector/tenant + tools db/log utils）進去，alias 維持舊名；同步 engine.spec；package-build×N | 高 | alias 唯一化 + package-build 連過數次 |
| **P6（end-state）** 物理建立 `plugins/labeling/`，搬 annotation + scripts/module_*（資料夾名維持數字）+ sheets + mcp + tests + docs 進去；同步 engine.py 掃描根、runner sys.path、engine.spec、修正 `parents[N]` 深度；最後拆 alias | 最高 | alias 唯一化 + package-build 連過數次 + golden path MCP |

→ **D3 全程適用**：資料夾/ID 維持 `module_NNN`，metadata（vendor/domain/slug）寫進 plugin.yaml + index。
→ **P0–P4 先交付擁有者 4 目標的實質**；**P5–P6 兌現物理 end-state（D1+D2）**，最後做、護欄最重。

### 共識狀態
✅ **方向性共識達成**（end-state 形狀 + 漸進路線 + 護欄 + ID 凍結 + 依賴方向）。
後續若要更細，可在各 Phase 開工前再開一輪 agent 針對「該 Phase 的具體 diff 與回滾腳本」做設計。但**重構方向已無歧見**。

---

## 執行記錄（2026-05-30, /goal 實作至 P6）

每個 Phase 獨立 commit、`npm run test:python` 綠燈才進下一步（分支 `feat/platform-restructure`）。

| Phase | 狀態 | 內容 | 驗證 |
|------|------|------|------|
| **P0** | ✅ done | docs 去重（platform 為權威，刪 root 重複三檔）、`docs/platform/shared-components.md` 權威索引、`docs/README.md` 文件地圖、CLAUDE.md「共用功能在哪」 | 文件；test:python 534 |
| **P1** | ✅ done | 刪巢狀空目錄、刪 legacy `scripts/sheets/`、加 2 護欄 test（spec hiddenimports 可載入、spec_from_file_location 目標存在）| 536 passed |
| **P2** | ✅ done | `scripts/shared/_config_base.py` 共用化，20 份 `_config.py` 委派（保留各自 `_DEFAULTS`/extras）、特性化測試鎖行為 | 556 passed |
| **P3** | ✅ done | `tests/test_architecture_boundaries.py` 邊界守門（core 不得依賴 plugin）| 558 passed |
| **P4** | ✅ done | 收斂 `cim_annotation`：`label_ops.py` → `annotation/`，改 module_017 import，補 spec hiddenimport，刪除其餘 | 558 passed |
| **P5** | ✅ done | 建 `core/`，`cim_platform/{connector,tenant}` → `core/integrations/`，`cim_platform` 保留為相容 shim，8 處內部 import 改 `core.integrations`，spec datas+hiddenimports、`package.json` extraResources filter（補 `core/**/*`）、boundary 納入 core | 558 passed + import 身分一致驗證 |
| **P6** | 🟡 宣告式家完成；物理搬移 gated | 建 `plugins/labeling/`（`plugin.manifest.yaml` 宣告 domain/modules/sheets/mcp/docs/tests 歸屬 + 對 core 依賴 + 語意名 metadata、`README.md`）；修補 P5 的 `package.json` filter 缺口 | test:python 綠 |

### P6b 嘗試 annotation 實體搬移 → pyinstaller gate 擋下 → 已回滾
經 owner 授權「pyinstaller-only 盡力做」，實際嘗試把 `annotation/` 搬到 `plugins/labeling/domain/`，用 `annotation/__init__.py` 的 `__path__` 重導當相容 shim（commit `0731826`）。**in-process 全綠**（558 passed + 所有 `annotation.*` import 身分一致），但跑 `pyinstaller engine.spec`（exit 0）後發現 **46 個 `annotation.*` hidden import 全部 `ERROR: not found`**：

> `__path__` 是 **runtime** 機制，PyInstaller 的 **build-time 靜態 modulegraph 不執行它**，因此無法把 `plugins/labeling/domain/*` 收進 bundle 的 `annotation.*` 名稱下 → **打包後會缺整個 annotation 套件**（典型「dev 綠、打包壞」）。

依 D4「失敗步驟回滾」**已 `git revert`（commit `ab58f5d`）**，annotation 回到正常頂層套件。同一次 build 確認 **P5 的 `core.integrations` / `cim_platform.*` 正常解析 → core/ 是 bundle-safe**（其餘 46 個 not-found 警告為既有 optional dep：pycparser/scipy/MySQLdb 等，與本次無關）。

### 結論：annotation/scripts 實體搬移的正確作法（未做，較大工程）
`__path__` shim 此路不通。要 bundle-safe 地把 Labeling 程式實體放到 `plugins/labeling/`，唯一正解是 **把 import 名稱全面改寫**（`annotation` → `plugins.labeling.domain`，121 處 + scripts/module_* + mcp + tests + `engine.spec` hiddenimports + `package.json` filter），讓 PyInstaller 看到正規 package。這是較大的機械式重構，且 `scripts/module_*` 還有 **`scripts/shared` 跨 labeling/非-labeling(module_021) 共用** 的結構難點（模組以 `spec_from_file_location` 相對載入 shared，正是為 PROD/bundle 而用，不能盲改成正規 import）。此工程建議獨立進行、每步 `npm run test:python` + 護欄 test + **`pyinstaller` build 驗證** + GUI golden-path。

### P6c annotation 領域實體搬移（import-rename 路線）→ pyinstaller gate 通過 ✅
依否決 P6b 後得到的正解，實際執行 bundle-safe 版本（commit 接在 revert 之後）：
- `git mv annotation/ → plugins/labeling/domain/`，新增 `plugins/__init__.py`、`plugins/labeling/__init__.py`，使 `plugins.labeling.domain` 成為**正規可 import 套件**（PyInstaller 靜態可解析，與 __path__ shim 不同）。
- **55 檔** `from annotation...` → `from plugins.labeling.domain...`（domain 內部、scripts/module_*、mcp/annotation_mcp、tests；無 bare `import annotation`）。
- `engine.spec` hiddenimports annotation.*→plugins.labeling.domain.*、datas annotation→plugins；`package.json` filter annotation→plugins；test_mcp_config / boundary guard（core 禁 import `plugins`）/ manifest / index 同步。
- **驗證**：`test:python 558 passed`、in-process import + module_017 載入 OK、**`pyinstaller engine.spec` build 成功且 `plugins.labeling.domain.*` 0 個 "not found"**（正是擊沉 P6b 的失敗模式）→ **bundle-safe**。

### P6d sheet 搬移 + 移除 cim_platform shim → pyinstaller gate 通過 ✅
- `sheets/annotation.yaml` → `plugins/labeling/sheets/`；engine `_reconcile_sheets_from_yaml` 改掃 `sheets/*.yaml` **+** `plugins/*/sheets/*.yaml`（既有 `test_sqlite_adapter` 的 annotation-tabs 測試驗證 sheet 仍從新位置正確註冊）。
- 完全移除 `cim_platform` shim（P5 已把所有 import 改 `core.integrations`，確認零殘留 importer）；自 engine.spec / package.json filter / test / boundary 一併移除。CLAUDE.md sheet 位置更新。
- pyinstaller build：0 not-found、`cim_platform` 完全消失。

### P6e/P6f 完成 — 整個 Labeling plugin 已物理收斂
- **P6e `scripts/module_*` → `plugins/labeling/modules/`**（19 個 labeling 模組）：採用比「轉正規 import」更簡單且 PROD-safe 的解法——`scripts/shared` **留原位**（平台共用，module_021 仍用），搬移後模組的 `_HERE.parent/"shared"` 路徑改為 `_HERE.parents[3]/"scripts"/"shared"`（65 檔、機制不變仍是 spec_from_file_location）；跨模組 `_HERE.parent/"module_NNN"` 因模組一起搬而續存；深度相關 `parents[4]`(PROJECT_ROOT)/`parents[2]`(tools/ENGINE_ROOT) 統一 +2（25 處，保留原語意），相對 `parents[1]` 跨模組不動；engine `_scan_and_register_plugins` + plugin_loader `_find_folder` 改搜 scripts/ + plugins/*/modules/。**驗證**：test:python 558、test_sqlite_adapter 確認 engine 從新位置掃到模組 + sheet tabs、6 個跨模組/用 shared 的 process 模組 in-process 載入、護欄 test 解析全部 spec 路徑、**pyinstaller build 0 not-found**。
- **P6f `mcp/annotation_mcp` → `plugins/labeling/mcp`**：相對內部 import 續存；`.mcp.json` + `.claude/mcp.json` 改 `python -m plugins.labeling.mcp.server`（PYTHONPATH=python-engine）。**驗證**：launch-smoke（`-m` 啟動處理 stdin-EOF 乾淨退出）、handlers create_dataset/ingest 正常。註：`test_annotation_mcp` 有 1 個**既有**失敗（create_schema NOT_FOUND，AnnotationService API drift，早於本重構、與搬移無關，搬移前後皆 1-fail/2-pass）。

### 最終交付狀態（分支 `feat/platform-restructure`）
- **P0–P5 完成、全綠**；P5(core/) 經 pyinstaller 驗證。
- **P6 物理搬移全數完成**：`plugins/labeling/` 現含 **domain/（領域）+ modules/（19 GUI 模組）+ sheets/（annotation.yaml）+ mcp/（MCP server）+ plugin.manifest.yaml + README**。平台共用層 `core/`（+`core.integrations`）抽出、**cim_platform alias 已刪**、依賴單向 `plugins→core`（boundary test 強制）、數字 module ID 凍結（D3）。
- **每步 pyinstaller build 為 gate**；`test:python 558 passed`、`npm test 16 passed`；全程 commit 可回滾。
- **刻意未搬（低價值/高 churn，manifest 已宣告歸屬）**：`tests/annotation/`（仍由 test:python 的 `tests/` 收集，搬移需改測試發現且無實益）；Labeling docs（仍在 `docs/`，搬移會斷大量 README/openspec 連結）。模組自帶的 `*_test.py` 已隨模組搬入 `plugins/labeling/modules/`。
- **唯一需實機補驗**：Labeling sheet 4 個 tab 的 Streamlit 實際 render、annotation MCP 在 Claude Code 重啟後的 tool handshake（結構/啟動已驗，render/handshake 屬 owner D4 的 GUI golden-path，headless 跑不了）。

