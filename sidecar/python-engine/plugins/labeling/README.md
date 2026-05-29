# Labeling plugin

Labeling 是 CIM 平台上的**一個（重要）plugin**，不是平台本身。這個目錄是 Labeling
的**單一宣告入口**：要找 Labeling 擁有哪些東西，看 [`plugin.manifest.yaml`](plugin.manifest.yaml)。

## 邊界

- Labeling 依賴平台 `core/`（`core.integrations` 的 `ExternalSystemConnector` /
  `SystemTenant`，以及逐步上移的共用基礎設施）。
- 依賴方向單向：`plugins/labeling/* → core/*`，**禁止** `core/* → plugins/labeling/*`。
  由 `tests/test_architecture_boundaries.py` 強制。

## 資產（目前 vs 目標）

`plugin.manifest.yaml` 列出 domain 套件、modules、sheet、MCP、docs、tests 的
**現址（current_path）** 與 **目標路徑（target_path）**。

平台重構採漸進路線（見 [`../../../docs/platform/architecture-restructure-discussion.md`](../../../docs/platform/architecture-restructure-discussion.md)）：

- **已完成（P0–P5）**：共用功能索引、文件去重、`_config_base` 共用化、架構邊界守門、
  收斂 `cim_annotation`、建立 `core/` 並把 `cim_platform` 移入 `core.integrations`。
- **本目錄（P6 宣告式家）**：`plugin.manifest.yaml` 已宣告 Labeling 全部資產歸屬。
- **待執行（P6 物理搬移，package-build + golden-path 驗證 gated）**：把 `annotation/`、
  `scripts/module_*`、`sheets/annotation.yaml`、`mcp/annotation_mcp`、相關 docs/tests
  實際搬入本目錄，並同步 `engine.py` 掃描根、runner `sys.path`、`engine.spec`、
  `package.json` filter，最後移除 `cim_platform` shim。此步驟必須在實際 app 上跑過
  package-build 與 golden-path MCP 才算完成（owner 決議 D4）。

## 模組命名（D3）

資料夾與 tool ID 凍結為 `module_NNN`；語意名（slug / name）放在 manifest 當 metadata，
不靠改資料夾名取得可讀性。
