# 共用功能索引（Shared Components）

> **這是「共用功能在哪、怎麼用」的唯一權威索引。** 開發新模組／plugin 前先查這裡，不要各自重造（尤其 DB、Log、config/路徑、UI 元件）。
>
> 註：平台正進行架構重構（見 [`architecture-restructure-discussion.md`](architecture-restructure-discussion.md)）。下表「目前位置」是現況；「未來去向」是重構後的目標（`core/`＝平台共用層、`plugins/labeling/`＝Labeling plugin）。重構期間會以 namespace alias 過渡，舊 import 仍有效。

## 快速查表：我想做 X → 用 Y

| 我想做… | 用哪個 | import / 用法 | 目前位置 | 未來去向 |
|---------|--------|---------------|----------|----------|
| 寫 log | `get_logger` | `from log_utils import get_logger; log = get_logger("module_012")` | `tools/log_utils.py` | `core/logging` |
| 開/查 manifest DB | `_manifest_db` DAL | `init_db(db_path)` / `create_manifest(...)` / `add_manifest_items(db_path, mid, items)`（所有函式第一參數收 `db_path`）| `scripts/shared/_manifest_db.py` | `core/db/manifest` |
| 通用 SQLite 存取 | `SimpleDAO` | `from db_utils import SimpleDAO` | `tools/db_utils.py` | `core/db` |
| 寫/讀工具執行結果 | `write_result`/`read_result` | `from tool_result import write_result, read_result` | `tools/tool_result.py` | `core`（執行框架）|
| 通知 portal 開始/完成 | `notify_start`/`notify_complete` | `from tool_comms import notify_start, notify_complete` | `tools/tool_comms.py` | `core`（執行框架）|
| 模組設定讀寫 / log 路徑 / 專案根 | 各模組 `_config.py` | `load_config()` / `save_config()` / `get_manifest_db_path()` | `scripts/module_NNN/_config.py`（**目前 20+ 份重複骨架**）| `core/config`+`core/paths`（P2 抽共用 helper，模組只留 `_DEFAULTS`）|
| Streamlit 共用 UI（日期/Parts/toast/下載/中文覆蓋）| `ui_components` | `date_input_range(...)` / `save_success_toast()` / `inject_streamlit_zh_overrides()` | `scripts/shared/ui_components.py` | `plugins/labeling/shared_ui` 或 `core/ui` |
| 影像預覽元件 | `image_widget` | `render_image_preview(...)` | `scripts/shared/image_widget.py` | 同上 |
| 說明按鈕（? 徽章）| `_help` | `render_help_button(module_id, side, title)` | `scripts/shared/_help.py` | 同上 |
| 資料來源連接器（ZIP/遠端）| `_data_connector` | `DataConnector` ABC / `ZipPackageConnector` | `scripts/shared/_data_connector.py` | `plugins/labeling/integrations` |
| 接外部任務系統（iWISC 等）| `ExternalSystemConnector` | `from core.integrations import ExternalSystemConnector` | `core/integrations/connector.py`（`cim_platform.connector` 為相容 shim）| ✅ 已在 core |
| 外部系統租戶設定 | `SystemTenant` | `from core.integrations import SystemTenant, load_tenant_from_file` | `core/integrations/tenant.py`（`cim_platform.tenant` 為相容 shim）| ✅ 已在 core |
| 標注領域服務（資料集/標注集/匯出）| `AnnotationService` | `from annotation.services import AnnotationService` | `plugins/labeling/domain/services.py`（import 名仍是 `annotation`，經 shim）| ✅ 已在 plugins/labeling/domain |
| 標注資料模型 | `annotation.core.models` | `DatasetManifest` / `AnnotationSet` / `AnnotationItem` | `plugins/labeling/domain/core/models.py` | ✅ 已搬 |
| 格式轉換（COCO/YOLO/x-anylabeling…）| `annotation/adapters` | `from annotation.adapters.coco import …` | `plugins/labeling/domain/adapters/`、`…/formats/` | ✅ 已搬 |
| 發布/回溯/載入 plugin | `PluginRegistry`/`PluginLoader` | 由 engine 使用 | `plugin_registry.py`、`plugin_loader.py` | `core/plugins` |
| 權限/角色 | `AuthProvider` | `from auth_provider import AuthProvider` | `auth_provider.py` | `core/auth` |
| 管理中心資料/schema | `management_*` | — | `management_*.py`（頂層 6 檔）| `core/db/management` |

## engine 注入的環境變數（**不可手動設定**）

由 `engine.py` 的 `ToolProcessManager._make_env()` 在 spawn Streamlit 子程序時自動注入。模組透過 `os.environ` 讀取，**名稱是穩定 ABI，重構不得更名**：

| 變數 | 用途 |
|------|------|
| `CIM_SHEET_ID` | 目前 sheet |
| `CIM_PLUGIN_ID` | 目前 plugin/工具 |
| `CIM_TOOL_ID` | 工具 ID（結果檔名 `{TOOL_ID}_result.json`）|
| `CIM_TOOL_LAYER` | `input` / `output` |
| `CIM_MODULE_ID` | 模組數字 ID（如 `012`）|
| `CIM_LOG_DIR` | log/config/db 根目錄 |
| `CIM_DEV_MODE` | `1`＝檔案系統載入；`0`＝DB snapshot |

## 重要慣例與地雷

- **共用碼目前靠動態載入**：模組用 `importlib.util.spec_from_file_location` 以**字串路徑**載入 `scripts/shared/*` 與彼此的 `_config.py`（例：`module_012/012_input.py` 載 `module_016/_config.py`）。→ IDE「Go to Definition」、grep `import xxx`、靜態分析**抓不到**這些依賴；搬移檔案會 runtime 才報 `FileNotFoundError`。P3 會引入 namespace alias + 正規 import 改善。
- **import 契約靠 runner 的 `sys.path`**：`tools/*_runner.py` 用 `sys.path.insert(0, ENGINE_DIR)`，所以頂層套件（`annotation`/`cim_platform`/`tools`/`management_*`）能被 import。**頂層套件的物理位置＝import 契約**，搬移需同步所有 runner。
- **打包白名單**：`engine.spec`（PyInstaller）的 `datas` + `hiddenimports` 是手寫清單；**dev 模式測不到 spec 破壞，只有 `/package-build` 驗得出**。搬任何套件都要同步更新 spec 並跑 package-build。
- **`_config.py` 用 `parents[4]` 算專案根**：目錄層級一變就錯。
- **新增模組/sheet 不必改 `engine.py`**：engine 啟動時掃 `scripts/*/plugin.yaml`（模組）與 `sheets/*.yaml`（sheet）自動註冊。`scripts/sheets/` 已**不被掃描**（legacy）。

## 命名規範（重構目標）

- 平台共用 → `core/`（依賴方向：`plugins/* → core/*`，**禁止** `core/* → plugins/*`）
- Labeling 專屬 → `plugins/labeling/`
- 模組資料夾/ID 字串**凍結為 `module_NNN`**；可讀性靠 `plugin.yaml` 的 `vendor`/`domain`/`slug` metadata + 本索引，不靠改資料夾名。
