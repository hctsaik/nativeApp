# 讓 Labeling 達到 AI4BI 等級的獨立性 — 計畫與契約

> 目標：讓 **影像標註（labeling）** 能像 **AI4BI** 一樣，在自己的 repo 獨立開發、
> 以 git submodule 掛回平台、低摩擦更新。過程嚴守「文件 + 測試 + 不破壞功能」。
>
> 本文是該工作的**權威藍圖與契約定義**。每個階段都以「測試全綠 + MCP golden path」為閘門。

## 1. 兩種獨立性模式（為什麼 labeling ≠ AI4BI）

| | AI4BI | 影像標註 (labeling) |
|---|---|---|
| 隔離方式 | **行程邊界** — 獨立 Streamlit app 塞 iframe，跟平台零共享 | **程式碼邊界** — 同一 engine 行程，會 `import core.*` 與少數共用工具 |
| 對平台依賴 | 黑盒、零依賴 | 白盒、單向 `labeling → core`（manifest 宣告 + 測試鎖死方向）|
| 規模 | 1 app、1 個薄 runner | 156 py、12 活躍模組、1 sheet、1 MCP server、完整 domain 層 |
| 安裝 | `pip install -e`（自帶相依的獨立 pip 套件）| 拉 submodule 原始碼即可（非 pip 套件；靠 host 的 `core/` 在 path 上）+ 自己的 annotation 相依 |
| 版本自由度 | 可任意超前/落後 | **必須對齊相容的 platform 契約版本** |

結論：labeling 永遠不會是「裝了就忘」的黑盒（它是平台的旗艦白盒功能），但**可以**做到
「在自己 repo 開發、submodule 掛回、契約清楚、更新低摩擦」。AI4BI 靠「獨立套件」保證隔離；
**labeling 靠「受測試鎖住的 import 契約」保證隔離** —— 這是本計畫的核心。

## 2. 現況盤點（2026-05-31 量測）

平台重構（P0–P6）已把 labeling 收斂成 `plugins/labeling/` 物理 plugin，並以
[`plugin.manifest.yaml`](../../sidecar/python-engine/plugins/labeling/plugin.manifest.yaml)
宣告 `depends_on: core`，由
[`tests/test_architecture_boundaries.py`](../../sidecar/python-engine/tests/test_architecture_boundaries.py)
鎖死「core 不准依賴 plugin」。**解耦已完成約 90%。**

實測 labeling 對平台的**完整依賴面**（這就是要凍結的契約）：

- **命名空間**：`core.*`（靜態 import，17 處；目前皆 `core.integrations.connector / tenant`）
- **共用工具（5 檔）**，經 sys.path 靜態或 `importlib.spec_from_file_location` 動態載入：
  - `scripts/shared/_config_base.py` — 設定/路徑/atomic write（每個模組 `_config.py` 委派）
  - `scripts/shared/_help.py` — 共用說明 UI
  - `scripts/shared/_manifest_db.py` — manifest DB DAL
  - `scripts/shared/ui_components.py` — 共用 Streamlit UI（含中文錯誤覆蓋）
  - `tools/db_utils.py` — 通用 SQLite DAO
- 其餘動態載入（`_012_config`、`_008_process`…）皆 **labeling 內部**，不算契約。

> 關鍵相容性：模組以 `_HERE.parents[3] / "scripts" / "shared"` 取用共用碼，`parents[3]` 解析到
> **host 的 python-engine 根**。即使 labeling 變成位於 `plugins/labeling/` 的 submodule（同物理深度），
> 這些路徑仍指向 host 的 `scripts/shared` —— **與 submodule 化相容，不需改路徑算法**。

## 3. 階段計畫（每階段測試全綠才前進）

### P0 — 契約凍結（本次）✅ 進行中
- 本藍圖文件（你正在讀）。
- 新增 **contract 測試** [`tests/test_labeling_platform_contract.py`](../../sidecar/python-engine/tests/test_labeling_platform_contract.py)：
  以 allowlist 鎖住「labeling 只能依賴 `core.*` + 上述 5 個共用檔」，任何新增的平台內部依賴
  （如 `import engine` / `management_store`）即測試失敗。**這是獨立性的守門員**，也防止後續重構把耦合擴大。
- 不動任何執行碼 → 零破壞風險。

### P1 — 契約顯性化（可選打磨，**高風險，預設不做**）
構想是把 5 個共用檔提升為 `core.config_base` / `core.ui` / `core.manifest_db` / `core.db`，
讓 labeling 改用 `from core.X import`，不再靠 `parents[3]` 路徑算法 + `spec_from_file_location`。

> **2026-05-31 調查結論：暫不執行。** GUI 模組對 `core` 的 import **全是延遲匯入**（在函式內、附
> `# noqa: PLC0415`，如 `module_026`），因為 Streamlit 子程序在**模組頂層執行時 `core` 尚未在
> sys.path 上**，要等 bootstrap 後才可用。共用碼改用 `spec_from_file_location`（絕對路徑、永遠可用）
> 正是為了繞過這個時序問題 —— **這是刻意且健壯的設計，不是技術債**。
>
> 因此把頂層動態載入改成頂層 `from core.X import` **會有破壞風險**（頂層匯入時機 core 未必可用），
> 與本計畫「避免改壞功能」相牴觸；而且 **P0 契約測試無論靜態或動態都已鎖住邊界、§2 已證動態載入在
> submodule 化後照常運作**，P1 對「獨立性」本身是零增益、純清晰度。故預設不做。
>
> 若未來仍要做：須逐模組改成**延遲匯入** `from core.X import`（比照現有 core import 的 pattern），
> 每切一個跑 `test:python` + 該模組 MCP golden path，且先確保子程序 sys.path 已含 python-engine。

### P2 — 相依與安裝收斂 ✅ 已完成
- 建 labeling 專屬相依清單
  [`plugins/labeling/requirements-labeling.txt`](../../sidecar/python-engine/plugins/labeling/requirements-labeling.txt)：
  只列「在 labeling 外 0 個 import 站點」的專屬套件（streamlit-image-annotation、streamlit-autorefresh、
  ultralytics/torch/torchvision/transformers）；與其他 CV 工具共享的 cv2/numpy/PIL/pandas 仍留在核心
  `requirements.txt`（**未改動主清單 → 零安裝破壞風險**）。對應 AI4BI 的 `[llm]` extra 概念。
- `verify-setup.ps1` doctor 新增「Labeling 影像標註」區段：檢查 plugin 存在、**平台契約檔齊全**
  （`core/` + 5 個共用工具檔）、annotation UI 相依可匯入（缺則 FAIL）、AI 預標相依（缺則 WARN，基本標注不受影響）。
  → 這同時就是「host 提供的 `core` 契約是否相容」的安裝期檢查。

### P3 — 物理搬遷成 submodule ✅ 已完成（2026-05-31）

labeling 已是 git submodule：**`https://github.com/hctsaik/ANnoTation`**，掛在
`sidecar/python-engine/plugins/labeling`（與 AI4BI 並列於 `.gitmodules`）。歷史以
`git subtree split` 保留後推到新 repo 的 `main`（commit f189e82）。驗證：`test:python` 717 passed、
doctor Labeling 區段全 PASS、MCP golden path（影像標註 sheet「資料來源」分頁）渲染正常。
備份分支 `backup/pre-labeling-submodule` 保留作安全網。

**日後維護**：在 submodule 內 `git pull` 即更新 labeling，平台端不需改動（與 AI4BI 完全相同的工作流）。
全新 clone：`git submodule update --init --recursive` 取得 labeling + AI4BI；
`pip install -r plugins/labeling/requirements-labeling.txt` 補裝 annotation 相依。

以下為當時實際執行的步驟（保留完整 git 歷史，供日後類似抽離參考）：

```powershell
# 0) 安全網：先開備份分支
git switch -c backup/pre-labeling-extract

# 1) 把 plugins/labeling 的歷史抽成獨立分支（保留 commit 歷史）
git subtree split --prefix=sidecar/python-engine/plugins/labeling -b labeling-export

# 2) 推到新 repo（先在 GitHub 建好空的 <labeling repo url>）
git push <labeling repo url> labeling-export:main

# 3) 回主分支，移除原目錄並改掛 submodule
git switch feat/platform-restructure
git rm -r sidecar/python-engine/plugins/labeling
git commit -m "chore(labeling): replace in-tree plugin with submodule"
git submodule add <labeling repo url> sidecar/python-engine/plugins/labeling
git commit -m "chore(labeling): vendor labeling as git submodule"

# 4) 驗證（與 AI4BI 同樣的關卡）
git submodule update --init --recursive
powershell -ExecutionPolicy Bypass -File scripts\win\verify-setup.ps1   # Labeling 區段須全 PASS
npm run test:python                                                     # 契約測試 + 全套件須綠
```

完成後：日後維護 labeling 只需在 submodule 內 `git pull`；契約測試 + doctor 守住與 host `core` 的相容性。
`requirements-labeling.txt` 隨 submodule 一起移動，安裝時 `pip install -r plugins/labeling/requirements-labeling.txt`。

> 注意：`.gitmodules` 會多一筆 labeling 條目（與既有 AI4BI 並列）。釘 submodule commit = 釘 labeling
> 對應的 `core` 契約版本，達成「可重現的 release」。

### P4 — 改為外部資料夾掛載（2026-06-14）✅ 已完成（取代 P3 的 submodule 掛法）

labeling 不再以 git submodule 巢狀於 nativeApp，而是改為**外部外掛**：原始碼放在 nativeApp
旁的獨立 clone（`ANnoTation`，repo 同為 `github.com/hctsaik/ANnoTation`），透過 **目錄
junction** 掛回 `sidecar/python-engine/plugins/labeling`。平台契約完全不變（仍靠
`plugins/*/modules` glob 探索、`import plugins.labeling.*`、`parents[3]` 取 host `core`），
因此**零執行碼改動**即可運作；探索／契約／打包 hiddenimports 等測試在 junction 下全綠。

> 動機：讓「平台（nativeApp）」與「外掛（labeling）」連實體目錄都分離——nativeApp 樹內不再有
> labeling 原始碼。代價：junction 不進 git，每次 clone／換機需跑一次
> `scripts\win\link-labeling.bat` 重建（已納入 README 安裝步驟、preflight 與 doctor 的修法提示）。

落地細節：
- `.gitmodules` 移除 labeling 條目（僅留 AI4BI）；`.gitignore` 忽略 `plugins/labeling/`。
- `engine.py` 的 submodule preflight 把 labeling 標為 `kind=external`，缺失時提示跑
  `link-labeling.bat`（AI4BI 仍提示 `git submodule update`）；`preflight-submodules.bat`／
  `verify-setup.ps1` 同步。
- 新增 `scripts\win\link-labeling.bat` 建立 junction（預設指向 nativeApp 旁的 `..\ANnoTation`，
  可用環境變數 `LABELING_SRC` 覆蓋）。
- 日後更新 labeling：在外部 `ANnoTation` 資料夾 `git pull` 即可（junction 即時反映）。

## 4. 風險與防護（如何「不改壞功能」）

| 風險 | 防護 |
|------|------|
| 重構切 import 時改壞行為 | P1 用**薄 re-export 轉接層**，不搬實作；逐模組切換 + 每步 `test:python` 全綠 + MCP golden path |
| 後續開發偷偷擴大耦合 | P0 contract 測試以 allowlist 失敗擋下 |
| submodule 與 core 版本漂移 | P2 doctor 檢查契約版本；P3 釘版本 |
| 路徑算法在 submodule 下失效 | 已驗證 `parents[3]` 仍解析到 host 根（§2 註） |

## 5. 進度

- **P0 ✅**：契約凍結 — 本文件 + `tests/test_labeling_platform_contract.py`（3 測試綠）。
- **P2 ✅**：相依與安裝收斂 — `requirements-labeling.txt` + doctor「Labeling」區段（實機全 PASS）。
- **P1（可選打磨）：預設不做**。調查發現模組對 `core` 採延遲匯入（子程序頂層 sys.path 時序），
  動態 `spec_from_file_location` 是刻意健壯設計；改頂層 `core.X` 有破壞風險、對獨立性零增益
  （契約已由 P0 鎖住）。詳見 §3 P1 結論。
- **P3 ✅**：labeling 已是 git submodule（`github.com/hctsaik/ANnoTation`），歷史保留、測試全綠、
  MCP golden path 驗證 OK。**目標達成：labeling 現與 AI4BI 同樣可獨立維護（submodule `git pull`）。**
- **P4 ✅（2026-06-14，取代 P3 掛法）**：labeling 改為**外部資料夾 + 目錄 junction** 掛載，原始碼
  移出 nativeApp 樹（獨立 clone `ANnoTation`）。零執行碼改動、測試全綠；新增
  `scripts\win\link-labeling.bat`，preflight／doctor／README 同步。詳見 §3 P4。
