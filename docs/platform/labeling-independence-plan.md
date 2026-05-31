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

### P1 — 契約顯性化（把隱性耦合收進 `core`）
把 P0 凍結的 5 個共用檔提升為**正式的 `core/` 契約**，讓 labeling 改用 `import core.X`，
不再靠 `parents[3]` 路徑算法與 bare import：
- `core.config_base`（← `scripts/shared/_config_base`）
- `core.ui`（← `scripts/shared/ui_components` / `_help` / `image_widget`）
- `core.manifest_db`（← `scripts/shared/_manifest_db`）
- `core.db`（← `tools/db_utils`）
做法：在 `core/` 建薄轉接層（re-export 既有實作，**不搬實作、不改行為**），逐模組切換 import，
每切一個就跑 `test:python` + 該模組 MCP golden path。隱性 → 可版本化的顯性契約。

### P2 — 相依與安裝收斂
- 建 labeling 自己的相依清單（annotation stack：streamlit-image-annotation、PIL、torch/ultralytics/transformers（AI 預標）、cv2…），
  併進 `verify-setup.ps1` doctor 與安裝文件。
- 在 doctor 增加「labeling 契約檢查」：確認 host 提供的 `core` 契約版本相容。

### P3 — 物理搬遷成 submodule（需 owner 的 GitHub 操作，最後一步）
1. 建 `labeling` repo，把 `plugins/labeling/` 內容移入。
2. 在原位 `plugins/labeling/` 掛 git submodule（照搬 AI4BI 的 `.gitmodules` 模式）。
3. `git submodule update --init` 即到位；`requirements-labeling.txt` 補裝 annotation 相依。
4. 釘 labeling submodule 對應的 `core` 契約版本；保留契約測試當守門員。

## 4. 風險與防護（如何「不改壞功能」）

| 風險 | 防護 |
|------|------|
| 重構切 import 時改壞行為 | P1 用**薄 re-export 轉接層**，不搬實作；逐模組切換 + 每步 `test:python` 全綠 + MCP golden path |
| 後續開發偷偷擴大耦合 | P0 contract 測試以 allowlist 失敗擋下 |
| submodule 與 core 版本漂移 | P2 doctor 檢查契約版本；P3 釘版本 |
| 路徑算法在 submodule 下失效 | 已驗證 `parents[3]` 仍解析到 host 根（§2 註） |

## 5. 進度

- **P0**：進行中（本文件 + contract 測試）。
- P1–P3：未開始。
