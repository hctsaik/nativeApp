# 設計：CV 框架 v2

## 整體架構

```
┌─────────────────────────────────────────────────────────┐
│                    Portal (Electron/React)               │
│                    GET /tools → 工具列表                  │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP
┌─────────────────────▼───────────────────────────────────┐
│                    engine.py (FastAPI)                   │
│   /tools → PluginRegistry.list_plugins()                 │
│   /tools/{id}/start → ToolProcessManager.start()         │
└──────────┬──────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────┐
│                  PluginRegistry                          │
│   dev mode  → PluginLoader.from_filesystem()            │
│   prod mode → PluginLoader.from_db()                    │
└──────────┬──────────────────────────────────────────────┘
           │
    ┌──────┴──────────────────────────────────┐
    │                                         │
┌───▼──────────────┐              ┌──────────▼──────────────┐
│  Module Plugin   │              │  Workflow Plugin         │
│  cv_framework_   │              │  workflow_runner.py      │
│  runner.py       │              │  (Tab UI, state bridge)  │
└──────────────────┘              └─────────────────────────┘
           │                               │
┌──────────▼───────────────────────────────▼──────────────┐
│              scripts/module_NNN/                         │
│              NNN_input.py / NNN_process.py / NNN_output  │
└─────────────────────────────────────────────────────────┘
```

---

## 目錄結構（目標狀態）

```
sidecar/python-engine/
├── engine.py                        ← 改用 PluginRegistry，移除 hardcode seed
├── plugin_registry.py               ← NEW：發現 + 載入外掛的核心邏輯
├── plugin_loader.py                 ← NEW：dev/prod 雙模式載入
├── auth_provider.py                 ← NEW：permission check（placeholder）
├── tools/
│   ├── cv_framework_runner.py       ← 改用 plugin_loader
│   ├── workflow_runner.py           ← NEW：Workflow/Suite UI
│   └── management_runner.py         ← NEW：管理中心 UI
├── scripts/
│   ├── module_001/
│   │   ├── plugin.yaml              ← NEW
│   │   └── ...
│   ├── module_002/ ... module_005/  ← 各自加 plugin.yaml
│   ├── shared/
│   └── workflows/
│       └── edge_analysis/
│           └── workflow.yaml        ← NEW
└── tests/
    ├── test_plugin_registry.py      ← NEW
    ├── test_plugin_loader.py        ← NEW
    └── test_auth_provider.py        ← NEW
```

---

## Plugin Manifest（`plugin.yaml`）

每個模組目錄都必須有一個 `plugin.yaml`：

```yaml
id: module_003
name: 不規則邊框產生器
version: "1.0.0"
category: module          # module | tool | workflow
description: 以純數學方式生成帶有可控凹凸紋理的矩形影像
author: system
tags:
  - edge
  - generator
runner: cv_framework      # 使用哪個 runner（cv_framework | workflow | standalone）
```

**欄位定義：**

| 欄位 | 必填 | 說明 |
|------|------|------|
| `id` | ✓ | 唯一識別碼，對應 engine.py 的 `plugin_id` |
| `name` | ✓ | 顯示名稱（中文可） |
| `version` | ✓ | SemVer 字串 |
| `category` | ✓ | `module`、`tool`、`workflow` |
| `description` | | 簡短說明 |
| `author` | | 作者 |
| `tags` | | 自由標籤，供 Management Center 過濾 |
| `runner` | ✓ | 指定啟動此外掛的 runner script |

---

## Workflow Manifest（`workflow.yaml`）

```yaml
id: edge_analysis
name: 邊緣品質分析
description: 整合邊框生成、邊緣偵測與歷史查詢的完整工作流程
version: "1.0.0"
author: system
steps:
  - plugin_id: module_003
    tab_label: "影像來源"
    description: "生成測試邊框，或直接上傳影像"
    optional: true              # 可跳過此步驟（直接上傳）
  - plugin_id: module_004
    tab_label: "偵測分析"
    description: "邊緣偵測、量測指標，並儲存至資料庫"
    optional: false
  - plugin_id: module_005
    tab_label: "歷史查詢"
    description: "查詢歷史量測記錄"
    optional: true
```

**Workflow 的狀態傳遞：**

Tab 之間透過 `st.session_state["workflow_{id}_step_{n}"]` 傳遞。
若 Step 1（003）執行後產生 `image_b64`，在 Step 2（004）的 Input 頁面會顯示「使用前一步驟的影像」選項。

---

## DB Schema（新增表格）

### 新增 6 個表格，舊 `tools` 表保留不動

```sql
-- 角色定義（未來 web service 整合使用）
CREATE TABLE IF NOT EXISTS roles (
    role_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT
);

-- 使用者（placeholder，未來從 web service 同步）
CREATE TABLE IF NOT EXISTS users (
    user_id    TEXT PRIMARY KEY,
    username   TEXT NOT NULL UNIQUE,
    role_id    TEXT REFERENCES roles(role_id),
    api_token  TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 外掛目錄（每個外掛一列）
CREATE TABLE IF NOT EXISTS plugins (
    plugin_id  TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT 'module',  -- module|tool|workflow
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 版本快照（不可變，每次 publish 新增一列）
CREATE TABLE IF NOT EXISTS plugin_versions (
    version_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id    TEXT NOT NULL REFERENCES plugins(plugin_id),
    version      TEXT NOT NULL,
    content_json TEXT NOT NULL,  -- {filename: content_str} JSON
    changelog    TEXT,
    author       TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    is_active    INTEGER NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'filesystem'  -- filesystem|published
);

-- 工作流程定義
CREATE TABLE IF NOT EXISTS workflows (
    workflow_id    TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT,
    runner_script  TEXT NOT NULL,  -- tools/ 目錄下的腳本名稱
    enabled        INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT DEFAULT (datetime('now'))
);

-- 工作流程步驟（有序）
CREATE TABLE IF NOT EXISTS workflow_steps (
    step_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
    step_order  INTEGER NOT NULL,
    plugin_id   TEXT NOT NULL REFERENCES plugins(plugin_id),
    tab_label   TEXT NOT NULL,
    description TEXT,
    optional    INTEGER NOT NULL DEFAULT 0,
    UNIQUE(workflow_id, step_order)
);

-- 外掛權限（角色 × 外掛）
CREATE TABLE IF NOT EXISTS plugin_permissions (
    perm_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id   TEXT NOT NULL REFERENCES plugins(plugin_id),
    role_id     TEXT NOT NULL REFERENCES roles(role_id),
    can_view    INTEGER NOT NULL DEFAULT 1,
    can_execute INTEGER NOT NULL DEFAULT 1,
    UNIQUE(plugin_id, role_id)
);
```

### 初始 seed 資料

```sql
-- 預設角色
INSERT OR IGNORE INTO roles VALUES ('admin', '管理員', '完整存取所有外掛');
INSERT OR IGNORE INTO roles VALUES ('operator', '操作員', '可執行，不可管理');
INSERT OR IGNORE INTO roles VALUES ('viewer', '觀察員', '唯讀，不可執行');

-- edge_analysis workflow
INSERT OR IGNORE INTO workflows VALUES
    ('edge_analysis', '邊緣品質分析', '整合邊框生成、偵測與查詢', 'workflow_runner.py', 1, datetime('now'));
```

---

## `plugin_registry.py` 介面

```python
class PluginRegistry:
    def list_plugins(self, role_id: str = "admin") -> list[PluginInfo]
    def get_plugin(self, plugin_id: str, role_id: str = "admin") -> PluginInfo
    def list_workflows(self, role_id: str = "admin") -> list[WorkflowInfo]
    def get_workflow(self, workflow_id: str) -> WorkflowInfo
    def publish(self, plugin_id: str, changelog: str, author: str) -> int
    def rollback(self, plugin_id: str, version_id: int) -> None
    def set_enabled(self, plugin_id: str, enabled: bool) -> None
    def list_versions(self, plugin_id: str) -> list[VersionInfo]
```

---

## `plugin_loader.py` 介面

```python
class PluginLoader:
    # Dev mode: load from filesystem (CIM_DEV_MODE=1)
    @staticmethod
    def load_module_dev(plugin_id: str, layer: str) -> ModuleType

    # Prod mode: load from DB active version snapshot
    @staticmethod
    def load_module_prod(plugin_id: str, layer: str, content_json: dict) -> ModuleType

    @staticmethod
    def is_dev_mode() -> bool:
        return os.environ.get("CIM_DEV_MODE", "1") == "1"
```

---

## `auth_provider.py` 介面

```python
class AuthProvider:
    def get_current_role(self) -> str:
        """
        現在（placeholder）：永遠回傳 'admin'。
        未來（production）：呼叫 web service，用 API token 換取 role。
        """

    def check_permission(self, plugin_id: str, action: str) -> bool:
        """action: 'view' | 'execute'"""
```

---

## Workflow Runner 設計（`tools/workflow_runner.py`）

```python
# 透過 CIM_WORKFLOW_ID env var 知道要執行哪個 workflow
workflow_id = os.environ.get("CIM_WORKFLOW_ID")

def main():
    workflow = registry.get_workflow(workflow_id)
    tab_labels = [step.tab_label for step in workflow.steps]
    tabs = st.tabs(tab_labels)

    for tab, step in zip(tabs, workflow.steps):
        with tab:
            render_step(step)

def render_step(step):
    # input 層
    input_mod = loader.load_module(step.plugin_id, "input")
    # 若上一步有傳入結果，注入 session_state 讓 input 可感知
    params = input_mod.render_input()

    if st.button("▶ 執行", key=f"run_{step.plugin_id}"):
        process_mod = loader.load_module(step.plugin_id, "process")
        result = process_mod.execute_logic(params)
        # 儲存到 session_state 供下一步使用
        st.session_state[f"wf_result_{step.plugin_id}"] = result

    result = st.session_state.get(f"wf_result_{step.plugin_id}")
    if result:
        output_mod = loader.load_module(step.plugin_id, "output")
        output_mod.render_output(result)
```

---

## engine.py 改動

**最小化改動**：只需要讓 `PluginRegistry.list_plugins()` 的回傳格式和現有的 `ToolDefinition` 相容即可。

1. 新建 `PluginRegistry`，用新的 DB tables
2. `list_tools()` 改為合併 plugins + workflows 的結果
3. 移除 hardcode `executemany` seed（改由 `plugin_registry.py` 的 `initialize()` 處理）
4. `_make_env()` 改為根據 plugin category 注入不同的 env var：
   - module：`CIM_MODULE_ID`（現有邏輯）
   - workflow：`CIM_WORKFLOW_ID`（新）

---

## 管理中心功能（`tools/management_runner.py`）

| 功能 | 說明 |
|------|------|
| 外掛列表 | 顯示所有 plugins，含狀態（啟用/停用）、版本、類別 |
| 啟用/停用 | 一鍵切換，立即生效 |
| 版本歷史 | 展開查看所有歷史版本，比對 changelog |
| 版本回溯 | 點選任一歷史版本 → 設為 active → 下次啟動框架即生效 |
| Dev→Prod 發布 | 掃描 `scripts/module_NNN/`，打包成 content_json，存入 plugin_versions |
| 工作流程管理 | 顯示 workflow 列表，啟用/停用 |
| 權限設定 | 設定哪些 role 可 view/execute 哪個 plugin（placeholder UI） |

---

## 開發流程（Dev → Prod）

```
開發階段（CIM_DEV_MODE=1）
  ↓ 直接修改 scripts/module_NNN/*.py
  ↓ 立即在框架中看到效果（無需 DB 操作）
  ↓ 完成開發，寫 changelog

發布（透過管理中心 或 CLI）
  ↓ 讀取 scripts/module_NNN/ 所有 .py 檔
  ↓ 序列化成 content_json
  ↓ INSERT INTO plugin_versions(..., is_active=1)
  ↓ 舊 active 版本設為 is_active=0

生產環境（CIM_DEV_MODE=0）
  ↓ 從 DB 讀取 active version 的 content_json
  ↓ 動態載入模組（exec 方式，不寫入檔案系統）
  ↓ 版本固定，不受檔案系統影響
```

---

## 設計決策說明

| 決策 | 選擇 | 理由 |
|------|------|------|
| 版本快照格式 | `content_json` TEXT | 不依賴 git，可在任何環境回溯；未來可換成 S3 等 |
| 舊 `tools` 表 | 保留不動 | Portal API (`/tools`) 仍讀取它；未來再統一 |
| auth placeholder | 永遠回傳 admin | 不阻礙開發；interface 已定義好，未來只換實作 |
| workflow state | `st.session_state` | Streamlit 原生機制，無需額外 IPC |
| DB file | 同 `tools.sqlite` | 減少檔案管理複雜度；schema 透過 migration 擴展 |
| `CIM_DEV_MODE` 預設值 | `"1"`（dev） | 開發時預設安全，需要明確設為 `"0"` 才進 prod 模式 |
