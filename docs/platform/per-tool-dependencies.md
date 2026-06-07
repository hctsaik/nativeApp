# 工具自帶相依宣告（Per-Tool Dependencies）— 設計提案

> 狀態：提案 → 實作中。對應功能 **#7**（工具在 `plugin.yaml` 宣告自己的 Python 相依，框架在隔離的 per-tool venv 安裝並注入子程序）。
> 本文件同時是實作規格與 as-built 文件；實作完成後請把「實作現況」一節更新為實際行為。

## 1. 問題

目前 pip 相依分兩種：全域 `requirements.txt` 與各 plugin 手動安裝（如 `plugins/labeling/requirements-labeling.txt`）。

→ **工程師上架一個需要新套件的工具時會卡住**：工具無法宣告自己需要什麼，也沒有自動安裝的機制。這正好打斷平台的核心迴圈（scaffold → 開發 → 熱載 → 上架）。

而且正式版是 PyInstaller frozen `engine.exe`，**內建 Python 是唯讀的**，無法 `pip install` 進自己。所以 per-tool 相依**必須**裝在另一個可寫位置（per-tool venv），這跟既有的 `.venv-xanylabeling`、`LabelMe_Dino/.venv` 是同一個模式。

## 2. 目標 / 非目標

**目標**
- 工具在 `plugin.yaml` 用 `requires:` 宣告 Python 相依。
- 框架在啟動該工具前，於**隔離的 per-tool venv** 確保相依齊備（冪等：已齊備就秒過）。
- 把該 venv 的 `site-packages` 注入 Streamlit 子程序的 `PYTHONPATH`（沿用既有 `_make_env` 注入點）。
- **frozen-exe 安全**：偵測 `sys.frozen`，改用外部 real Python 建立 venv。
- **離線/氣隙安全**：可從本機 wheelhouse 以 `--no-index --find-links` 安裝，模擬工廠內網鏡像。
- 全程不阻塞 engine 啟動；單一工具相依失敗只影響該工具，回報清楚錯誤。

**非目標（本期不做）**
- 跨機器分發相依（屬 #1 Fleet）。
- 非 Python 相依（系統套件、CUDA 等）。
- 自動解相依衝突 / lockfile 求解（交給 pip）。

## 3. 宣告語法（plugin.yaml）

```yaml
id: module_042
name: 缺陷量測
runner: cv_framework
# ── 本工具自帶的 Python 相依（框架自動建 per-tool venv 安裝）──
requires:
  - shapely>=2.0
  - scikit-image==0.24.*
```

- 省略 `requires:` 或空清單 → **完全不建 venv**（行為與今天一致，零額外成本）。
- 套件字串就是 pip requirement specifier，原樣交給 pip。

## 4. 元件設計：`core/tool_deps.py`

新模組，**純函式、可單元測試、不 import streamlit、不 import engine**。對外 API：

```python
def venvs_root() -> Path:
    """per-tool venv 的家。預設 <engine_root>/.tool-venvs/，
    可由 CIM_TOOL_VENVS_DIR 覆寫（packaged 模式指向可寫資料夾）。"""

def tool_venv_dir(tool_id: str) -> Path:
    """單一工具的 venv 路徑：venvs_root() / tool_id。"""

def site_packages_dirs(venv_dir: Path) -> list[str]:
    """該 venv 的 site-packages 路徑（Windows: Lib/site-packages；
    POSIX: lib/pythonX.Y/site-packages）。供注入 PYTHONPATH。"""

def base_python() -> list[str]:
    """建立 venv 用的『真 Python』指令前綴。解析順序：
      1. CIM_PYTHON 環境變數（絕對路徑）
      2. 若非 frozen：sys.executable
      3. frozen：嘗試 py -3.11 / python3.11 / python（PATH）
    回傳如 ['C:/.../python.exe'] 或 ['py','-3.11']。"""

def ensure_tool_deps(
    tool_id: str,
    requires: list[str],
    *,
    wheelhouse: Path | None = None,
    base_python_cmd: list[str] | None = None,
    venv_dir: Path | None = None,
) -> DepResult:
    """確保 tool_id 的 venv 內 requires 齊備（冪等）。
       - requires 空 → 回 DepResult(ok=True, venv_dir=None, installed=[])
       - venv 不存在 → 用 base_python 建立
       - 用『已安裝指紋』判斷是否需要 pip（見 §5），需要才安裝
       - wheelhouse 給定 → pip install --no-index --find-links=<wheelhouse>
       - 回傳結果（成功/失敗、訊息、site-packages 路徑、本次安裝清單）"""

def pythonpath_for_tool(tool_id: str, requires: list[str]) -> str | None:
    """便利函式：ensure 後回傳要併進 PYTHONPATH 的字串（os.pathsep 串接），
       無相依時回 None。供 engine._make_env 直接使用。"""
```

`DepResult` 是 dataclass：`ok: bool`、`venv_dir: Path | None`、`site_packages: list[str]`、`installed: list[str]`、`message: str`。

### 設計要點
- **冪等指紋**：在 venv 內寫一個 `.cim-deps.json`，記錄上次安裝的 `sorted(requires)` 之 hash。`ensure` 時比對；相同則跳過 pip（這是「秒過」的關鍵，避免每次啟動工具都跑 pip）。
- **frozen-exe**：`base_python()` 在 frozen 下不可用 `sys.executable`（那是 engine.exe），必須找外部 3.11。找不到 → `DepResult(ok=False, message="…需要設定 CIM_PYTHON…")`，且 engine 端要把這個訊息回報給 portal/log，不可吞掉。
- **離線**：`wheelhouse` 來自 `CIM_WHEELHOUSE` 環境變數（資料夾）。給定時一律 `--no-index`，完全不連 PyPI。
- **安全併發**：建立/安裝期間在 venv 父目錄放一個 file lock（或寫入 tmp 再 atomic rename），避免兩個子程序同時建同一個 venv。
- **不阻塞啟動**：`ensure_tool_deps` 只在「啟動某工具」時呼叫，不在 engine 開機時對所有工具跑。

## 5. 安裝流程（ensure_tool_deps 內部）

```
requires 空? ──是──▶ 回 ok（不建 venv）
   │否
venv 存在? ──否──▶ base_python -m venv <tool_venv_dir>
   │是
讀 .cim-deps.json 指紋 == hash(sorted(requires))? ──是──▶ 回 ok（秒過）
   │否
<venv_python> -m pip install [--no-index --find-links=WHEELHOUSE] <requires...>
   │
成功? ──是──▶ 寫入新指紋 → 回 ok（installed=requires）
   │否
回 DepResult(ok=False, message=pip stderr 摘要)
```

## 6. 整合點（由 orchestrator 在 engine 側接線，非本模組職責）

1. **`engine.py` `_make_env`**：取得該 tool 的 `requires`（讀 `find_module_folder(tool_id)/plugin.yaml`），呼叫 `tool_deps.pythonpath_for_tool(...)`，把回傳併進 `env["PYTHONPATH"]`（保留既有值）。
2. **`scaffold.py`**：`module` 子指令加 `--requires a,b` 旗標；form/full 範本 plugin.yaml 加註解示範 `requires:`。
3. **`requirements.txt` / 打包**：不變（per-tool venv 與全域分離）。

## 7. 測試計畫（`tests/test_tool_deps.py`）

純單元測試，不真的連網路。重點用例：
- `requires` 空 → 不建 venv、回 `ok=True, venv_dir=None`。
- `tool_venv_dir` / `site_packages_dirs` 路徑形狀（Windows vs POSIX 分支）。
- `base_python()` 解析順序：設 `CIM_PYTHON` 時優先；frozen 模擬（monkeypatch `sys.frozen`）時不回 `sys.executable`。
- 指紋邏輯：同 `requires` 第二次呼叫應跳過安裝（用 monkeypatch 攔截 subprocess 確認沒呼叫 pip）。
- `wheelhouse` 給定時組出的 pip 指令含 `--no-index --find-links`。
- 安裝失敗（monkeypatch subprocess 回非零）→ `ok=False` 且 message 帶 stderr。
- 真實 venv 建立可用 `tmp_path` + 一個極小純 Python 套件（或用 `--no-index` 空 wheelhouse 驗證指令組裝，不實際裝），避免測試連網或變慢。

## 8. 實作現況（as-built）

- [x] `core/tool_deps.py`（純函式核心，含 file lock + 指紋快取 + frozen 候選 Python）
- [x] `tests/test_tool_deps.py`（26 passed）
- [x] engine `_make_env` 注入（[engine.py](../../sidecar/python-engine/engine.py) `_read_tool_requires` + `_make_env`；sheet tab 以實際 `plugin_id` 為鍵）
- [x] scaffold `--requires`（CLI 旗標 + 三種 plugin.yaml 範本的 `requires:` 區塊；`tests/test_scaffold.py` 兩個新測試）
- [x] **frozen 自帶 Python（base_python 來源）**：release 透過 `scripts/win/fetch-standalone-python.ps1`
  取得可重定位的 **python-build-standalone 3.11**（內含 venv+pip，非 embeddable），electron-builder 以
  `package.json` 的 `extraResources`（`python-runtime/python` → `resources/python`）打進安裝包；
  `apps/host-electron/src/main.js` 啟動 engine 時注入 `CIM_PYTHON=<resources>/python/python.exe`
  →`base_python()` 第一順位即用它建 per-tool venv。**這讓乾淨工廠機（沒裝 Python）也能用自帶相依的工具。**
  版本鎖 3.11 與 frozen engine.exe 對齊（注入回 PYTHONPATH 的 site-packages 須 ABI 相容）。
  接線守門：`apps/host-electron/src/electron-env.test.js`。
- [x] **frozen-exe 端到端實機驗證（2026-06-07 完成，start 200）**：臨時建一個 `requires: cowsay`
  的 cv_framework 工具，用**打包後的 `engine.exe` + 自帶 Python**（`CIM_PYTHON` 注入）經 HTTP 啟動，
  `POST /tools/<id>/start` 回 **200**（10s 內），engine.log `Per-tool deps ready ... ['cowsay']`→`(cached)`，
  venv 內確有 cowsay。確認乾淨機免裝 Python 也能用自帶相依工具，且 frozen streamlit 工具能真正啟動。

### frozen 端到端驗證揭露的兩個真正阻斷（已修；先前 frozen 從未真的跑起 streamlit）
原本誤判為「首次 pip 太久 → 就緒逾時 500」，實機驗證後發現**真因是 frozen 打包缺陷**，與 timeout 無關：
1. **streamlit metadata 未打包**：`streamlit/version.py` 在 import 時呼叫 `importlib.metadata.version("streamlit")`，
   frozen 找不到 `.dist-info` → `PackageNotFoundError` → **每個 streamlit 子程序 import 即崩**。
   修：`engine.spec` 加 `copy_metadata('streamlit', recursive=True)`（含 45 個相依 metadata）。
2. **developmentMode 衝突**：frozen 下 streamlit 預設 `global.developmentMode=true`，禁止設 `server.port`
   →`RuntimeError: server.port does not work when global.developmentMode is true`。
   修：`run_streamlit_script` 設 `STREAMLIT_GLOBAL_DEVELOPMENT_MODE=false`（dev 本就 false，無影響）。

> 附帶防禦改善（非 500 主因，但保留）：啟動前 `_prewarm_deps_and_timeout()` 先建 per-tool venv（把首次 pip
> 移出就緒等待預算），且 `requires:` 工具的就緒 timeout 由 30s→120s。見 engine.py `_start_regular/_start_app/sheet`。

> ⚠️ 尚未驗：frozen 下 streamlit **前端 static 是否完整算繪**（start 200 只證明 server 起、port 綁定）。
> 需啟動打包後 Electron app 以 GUI/MCP 截圖確認 iframe 內容；本輪未做。

## 9. 風險與緩解
| 風險 | 緩解 |
|------|------|
| frozen 下找不到 real Python | release 自帶 standalone Python 3.11 並注入 `CIM_PYTHON`（見 §8）；仍找不到時回明確錯誤訊息 + 可手動 `CIM_PYTHON` 覆寫 |
| 每次啟動都跑 pip 拖慢 | `.cim-deps.json` 指紋快取，相同 requires 秒過 |
| 兩子程序同時建 venv | venv 父目錄 file lock / atomic rename |
| 工廠離線裝不到套件 | `CIM_WHEELHOUSE` + `--no-index`，部署前 `pip download` 備好 wheel |
