# AI4BI 整合說明

把 **AI4BI**(自助式 AI 商業分析,Streamlit + Plotly + DuckDB)掛進 CIM Hybrid Edge
Platform,以「**app 類型工具**」的形式,在 portal 裡以一個獨立頂層應用、單一畫面
(iframe)呈現。

## 設計原則:連結,不複製(低摩擦更新)

AI4BI 在**自己的 repo** 持續開發,**不把原始碼複製進平台**:

- 以 **git submodule** 置於 `sidecar/python-engine/vendor/AI4BI`(鎖定 commit,供 release 重現)。
- 以 **editable 方式**安裝進 engine 的 Python(`pip install -e vendor/AI4BI[llm]`)。
- 平台端只新增一個很薄、幾乎不會變的啟動器 `tools/bi_runner.py`。

> **更新 AI4BI**:在 submodule 內 `git pull`(或 `git submodule update --remote`)即生效
> (editable 安裝即時反映);只有 AI4BI **新增相依套件**時才需要再 `pip install`。
> 平台端通常不需改動。

## 為什麼需要「app 類型工具」

平台原本的工具模型只有:cv_framework 模組(input/process/output 雙畫面)、多分頁 sheet、
external GUI(桌面 exe)。這些都不適合「**一個完整的外部 Streamlit app、單一畫面內嵌**」:

- 頂層可見需要 `category` 為 `sheet`/`management`(由 `tool_id` 開頭推導)。
- 但 `sheet` 會走 `_start_sheet` → `sheet_runner` 用 cv_framework 渲染每個分頁,
  而 cv_framework 會自己呼叫 `st.set_page_config`,**和 AI4BI 自己的版面設定衝突**。

因此新增第四種輕量工具類型 **`app`**(只開一個 runner、一個 iframe,app 自己掌管整個畫面)。

## 變更清單

| 檔案 | 變更 |
|------|------|
| `engine.py` `_derive_category` | `tool_id` 以 `app-` 開頭 → category **`app`**(頂層可見) |
| `engine.py` `start()` | category `app` → 新的 `_start_app` |
| `engine.py` `_start_app()` | **只 spawn 一個** Streamlit 程序、回傳單一 URL(不走 input/output 雙畫面、不走分頁) |
| `engine.py` `diagnostics()` | active tool 的 category 改用 `_derive_category`(正確回報 `app`) |
| `engine.py` `/tools/active/status` | 新增 **app 分支**:app 只有單一程序(無 output pane),`output_alive` 改讀那唯一程序——否則落入「regular tool」分支會從未 spawn 的 `_output_process` 讀出「死亡」,portal poller 誤報「Output 程序已停止」 |
| `apps/portal-react/src/main.jsx` | 新增 `AppPanel`(單一 iframe);`app` 加入可見類別/排序/標籤;render 分支 |
| `tools/bi_runner.py`(新) | `runpy.run_module("ai4bi.ui.app", run_name="__main__")` 啟動 AI4BI |
| `plugins/bi/`(新) | plugin manifest + `modules/ai4bi/plugin.yaml`(`id: app-ai4bi`、`runner: bi`) |
| `tests/test_app_tool_type.py`(新) | 驗證 category 推導與 app-ai4bi 接線 |
| `tests/test_api.py` | 回歸測試:app 工具的 status endpoint 回報單一程序存活(`output_alive=true`),防止假「Output 程序已停止」橫幅 |

`runner: bi` 由 engine 的 runner map fallback(`f"{runner}_runner.py"`)對應到 `tools/bi_runner.py`,
不需改 engine 的對照表。

## 啟動鏈

```
start-dev.bat → Electron → FastAPI engine
  → 選擇「📊 AI Report (AI4BI)」(category=app)
    → _start_app spawn 一次:streamlit run tools/bi_runner.py
      → runpy 執行 ai4bi/ui/app.py(其 __main__ 守衛觸發 main())
    → portal 以單一 iframe 內嵌
```

## 首次設定(全新 clone 後)

```powershell
git submodule update --init --recursive
# 用平台的 3.11 直譯器安裝(與 engine 同一個環境)
& "C:\Users\hctsa\AppData\Local\Python\pythoncore-3.11-64\python.exe" -m pip install -e "sidecar/python-engine/vendor/AI4BI[llm]"
```

## 版本對齊

- AI4BI 已對齊 **Python 3.11**(`requires-python>=3.11`),與平台 host 直譯器一致。
- 共用 engine 的 3.11 環境:streamlit 1.57、pandas 3.0 兩邊一致;`streamlit-image-annotation`
  未鎖 streamlit 上限,**不衝突**。安裝 AI4BI 只新增 duckdb/plotly/scipy/xlsxwriter/anthropic
  等附加套件,不影響 labeling 模組。
- AI4BI 的 `matplotlib`、`scipy` 已正式宣告為相依(先前在乾淨環境會缺)。

## Release 打包(瘦平台模型)

平台(本 repo)的 frozen `engine.exe` **刻意不把 AI4BI(plotly/duckdb)打進核心**——
AI4BI 是獨立 git submodule,屬於 plugin,平台保持瘦、plugin 自帶相依。
靜態守門:`tests/test_packaging_guards.py::test_engine_spec_does_not_bundle_plugin_heavy_deps`
(禁止有人把 `collect_all('ai4bi'/'plotly'/…)` 加回核心 spec)。

frozen 下要讓 AI Report 能 `import ai4bi`,走平台的「每工具自帶相依」機制(per-tool venv,
`core/tool_deps.py`,#7):在目標機用外部 Python 3.11 為該工具建隔離 venv 安裝 ai4bi 及其相依。
需設 `CIM_PYTHON` 指向真實 python.exe(frozen 的 engine.exe 無法自己 `-m venv`),離線用 `CIM_WHEELHOUSE`。

> 完整 frozen 端到端驗證(build engine.exe + 啟動 AI Report)請跑 `/package-build`,
> 並確認目標機具備 per-tool venv 所需的外部 Python 3.11。
