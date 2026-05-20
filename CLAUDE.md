# CIM Hybrid Edge Platform — AI 協作指引

## 啟動方式

### 開發模式
```powershell
# 根目錄執行（會開 Electron + React portal + Python engine）
start-dev.bat
# 或
cd apps/host-electron && npm run dev
```

### 首次設定（解壓 source zip 或全新 clone 後）
```powershell
python restore_gmail_safe_filenames.py   # 僅 Gmail-safe zip 需要
npm install
pip install -r sidecar/python-engine/requirements.txt
start-dev.bat
```

## 架構關鍵點

### 啟動鏈
```
start-dev.bat
  → Electron (apps/host-electron)
    → Python FastAPI engine (sidecar/python-engine/engine.py)
      → Streamlit 子程序（按需啟動，含注入環境變數）
```

### 環境變數由 engine 注入，不可手動設定
`CIM_SHEET_ID`、`CIM_PLUGIN_ID`、`CIM_TOOL_ID`、`CIM_LOG_DIR` 等變數由
`ToolProcessManager._make_env()`（engine.py ~line 484）在 spawn Streamlit 子程序時自動注入。

**不可直接執行任何 `sidecar/python-engine/tools/*.py`**（包括 `sheet_runner.py`），
必須透過 Electron 啟動整個 app，engine 才會正確注入這些變數。

## 常見錯誤與處理

| 錯誤 | 原因 | 解法 |
|------|------|------|
| `Missing CIM_SHEET_ID or CIM_PLUGIN_ID` | 直接執行 `sheet_runner.py`，或 source zip 未含 `tools.sqlite` | 改用 `start-dev.bat` 啟動整個 app；或確認打包時有帶 `--include-file` |
| Electron app 啟動後印出 Node.js 版本就退出 | `ELECTRON_RUN_AS_NODE=1` 殘留在環境 | 移除該環境變數，或用 `apps/host-electron/launch-electron.js` workaround |
| `xanylabeling.exe` 被 WDAC 封鎖 | Windows Application Control 政策 | `012_output.py` 已改用 `python.exe -c "from anylabeling.app import main; main()"` 繞過 |

## 工具開發規則

- 每個工具由兩個 Streamlit 程序組成（split-tool 架構）：`*_input.py` + `*_output.py`
- Output page **禁止** `time.sleep + st.rerun()` polling loop；portal 收到 `EXECUTE_COMPLETE` 後會自動 reload
- 新工具需在 `engine.py` 的 `seed_tools` 清單中新增 entry

詳見 `README.md` 的「開發新工具」章節。

## Streamlit Output 頁效能規則

**每次 rerun 都會重新執行整個 render 函式**，因此以下三條規則必須遵守：

### 規則 1：掃描結果必須快取在 session_state，以 mtime 驅動增量更新

禁止在 `render_output()` 裡對所有 item 直接跑 `json.loads()` / `Path.exists()` 迴圈。
正確做法：

```python
# 首次載入 → full scan（記錄 ann_path mtime）
# 後續 rerun → 只做 stat() 比對，mtime 改變才重讀 JSON
def _get_items(manifest_id, workspace_dir, db_items):
    if st.session_state.get("cache_mid") != manifest_id or "items" not in st.session_state:
        items, mtimes = _scan_items(db_items, workspace_dir)   # full scan
        st.session_state["items"] = items
        st.session_state["mtimes"] = mtimes
        st.session_state["cache_mid"] = manifest_id
        return items
    items, mtimes = _incremental_refresh(                       # mtime-only
        st.session_state["items"], st.session_state["mtimes"], workspace_dir
    )
    st.session_state["items"] = items
    st.session_state["mtimes"] = mtimes
    return items
```

參考實作：`scripts/module_012/012_output.py`（`_scan_items` / `_incremental_refresh` / `_get_items`）

### 規則 2：大型列表必須分頁（PAGE_SIZE = 50），禁止一次 render 所有項目

左欄列表超過 50 項時，每次 rerun 的 Streamlit widget 樹會線性爆炸（每項 3欄 + 2按鈕）。
正確做法：

```python
PAGE_SIZE = 50
n_pages   = max(1, (len(visible) + PAGE_SIZE - 1) // PAGE_SIZE)
page      = st.session_state.get("page", 0)
page_items = visible[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

for item in page_items:   # 只 render 當頁 50 項
    ...

# 鍵盤導覽自動跟隨：選取項目不在當頁時跳過去
for _vi, _it in enumerate(visible):
    if item_id_to_global[_it["item_id"]] == sel_idx:
        desired = _vi // PAGE_SIZE
        if desired != page:
            st.session_state["page"] = desired
        break
```

### 規則 3：`list.index(item)` 在 loop 內是 O(N²)，必須改為 O(1) 查表

```python
# ❌ 禁止
global_idx = items.index(item)   # loop 內每次都線性搜尋

# ✅ 正確：loop 前建一次 dict
item_id_to_global = {it["item_id"]: i for i, it in enumerate(items)}
# loop 內
global_idx = item_id_to_global.get(item["item_id"], fallback)
```

詳細說明見 `docs/patterns/streamlit_output_perf.md`

## 測試

```powershell
npm run test:python     # Python sidecar 單元測試
npm test                # JavaScript shared-protocol 單元測試
```

## 日誌位置

`apps/host-electron/logs/`（`CIM_LOG_DIR`）

## 打包

```powershell
# 原始碼 zip（換電腦用，含 sheet 工具資料庫設定）
python packages/source-code-packager/scripts/package_source_zip.py `
  --root . --include-all `
  --exclude-dir .venv-xanylabeling --exclude-dir .claude `
  --exclude-dir external_exe --exclude-dir release --exclude-dir _release --exclude-dir testData `
  --exclude-dir logs --exclude-dir tmp `
  --include-file "apps/host-electron/logs/data/tools.sqlite" `
  --name ../nativeApp_source

# 原始碼 zip（Gmail 安全模式，無資料庫）
python packages/source-code-packager/scripts/package_source_zip.py `
  --root . --include-all `
  --exclude-dir .venv-xanylabeling --exclude-dir .claude `
  --exclude-dir external_exe --exclude-dir release --exclude-dir _release --exclude-dir testData `
  --gmail-safe --name ../nativeApp_source_gmail_safe

# Electron 可攜式安裝包
npm run build
cd sidecar/python-engine && python -m PyInstaller engine.spec
npm run package:portable
```
