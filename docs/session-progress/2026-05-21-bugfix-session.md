# 2026-05-21 Bug Fix Session — 進度紀錄

> 此文件記錄本次 session 修復的三個 bug，以及尚未完成的一個問題（WDAC）。
> 接手時從「⏳ 待用戶操作」章節開始閱讀。

---

## ✅ Bug 1：分頁按鈕（◀/▶）點擊無反應

### 症狀
annotation_workflow sheet 的 module_012 Output 頁，點擊分頁按鈕後頁碼不變。

### 根本原因
`sidecar/python-engine/scripts/module_012/012_output.py`（修前 line ~587）的**自動跟隨邏輯**在每次 rerun 都無條件執行：

```python
# 原本（有 bug）— 每次 rerun 都會把 m012_page 覆寫回選取項目所在頁
for _vi, _it in enumerate(visible):
    if item_id_to_global.get(_it.get("item_id", "")) == sel_idx:
        desired = _vi // PAGE_SIZE
        if desired != page:
            page = desired
            st.session_state["m012_page"] = page  # ← 覆蓋分頁按鈕的寫入
        break
```

當 ▶ 設定 `m012_page=1` 觸發 rerun，下一次 rerun 自動跟隨看到選取項目在第 0 頁，就把 `m012_page` 改回 0，永遠無法翻頁。

### 修法（已套用）
**檔案：** `sidecar/python-engine/scripts/module_012/012_output.py`

1. 自動跟隨改為 **只在鍵盤導覽時觸發**（以 `m012_kbd_nav` flag 控制）
2. 分頁按鈕移除多餘的 `st.rerun()`（Streamlit 按鈕點擊本身已觸發 rerun）
3. 幽靈導覽按鈕（↑/↓）設定 `m012_kbd_nav = True`

```python
# 修後
if st.session_state.pop("m012_kbd_nav", False):   # 只有鍵盤導覽才跟隨
    for _vi, _it in enumerate(visible):
        if item_id_to_global.get(_it.get("item_id", "")) == sel_idx:
            desired = _vi // PAGE_SIZE
            if desired != page:
                page = desired
                st.session_state["m012_page"] = page
            break
```

---

## ✅ Bug 2：強化圖（🔆 對比 toggle）無反應

### 症狀
右欄的「🔆 對比」toggle 切換後圖片沒有任何變化。

### 根本原因
`enhance` 只在 `if shapes:` 分支內被消費（有標注框才套用增強），若當前圖片無標注或 shapes 為空，`st.image(fp)` 完全忽略 `enhance` 狀態。

### 修法（已套用）
**檔案：** `sidecar/python-engine/scripts/module_012/012_output.py`

新增 `_show_img(fp, enhance)` helper，`enhance=True` 時對純圖片也套用 PIL 增強：

```python
def _show_img(fp: str, enhance: bool) -> None:
    if enhance:
        try:
            st.image(_draw_annotations(fp, {}, enhance=True), use_container_width=True)
            return
        except Exception:
            pass
    st.image(fp, use_container_width=True)
```

原本 `st.image(fp)` 的兩個位置（無標注、shapes 為空）改用 `_show_img(fp, enhance)`。

---

## ✅ Bug 3：sheet_runner / cv_framework_runner 吞掉 RerunException

### 症狀
Output 頁各種按鈕互動有時無反應（背景原因，會影響 Bug 1 以外的互動）。

### 根本原因
`sheet_runner.py` 和 `cv_framework_runner.py` 的 `except Exception:` 捕捉到 Streamlit 的 `RerunException`，導致 `st.rerun()` 失效，並且兩個檔案都有 `time.sleep(2/3) + st.rerun()` polling loop。

### 修法（已套用）

**`sidecar/python-engine/tools/sheet_runner.py`**：
- 加入 Streamlit 例外重新拋出檢查
- 移除 `time.sleep(2) + st.rerun()` polling loop

**`sidecar/python-engine/tools/cv_framework_runner.py`**：
- 同上

```python
except Exception as exc:
    if type(exc).__module__.startswith("streamlit"):
        raise   # 讓 st.rerun() / st.stop() 正常傳播
    st.error(f"載入 {PLUGIN_ID} output 失敗：{exc}")
```

---

## ⏳ Bug 4：X-AnyLabeling 啟動失敗（WDAC 封鎖）— 需用戶操作

### 症狀
點擊「🖊 標注工具」出現：`啟動失敗：[WinError 4551] 應用程式控制原則已封鎖此檔案`

### 根本原因分析

| 執行檔 | 來源 | WDAC 狀態 |
|--------|------|-----------|
| `.venv-xanylabeling\Scripts\xanylabeling.exe` | uv trampoline (46KB) | ❌ 封鎖 |
| `.venv-xanylabeling\Scripts\python.exe` | uv trampoline (46KB) | ❌ 封鎖 |
| `AppData\Roaming\uv\python\cpython-3.12-...\python.exe` | uv 下載，未簽章 (91KB) | ❌ 封鎖 |
| `C:\Users\...\AppData\Local\Python\pythoncore-3.14-64\python.exe` | PSF-signed | ✅ 信任，但 ABI 不符（cp312 venv）|
| `C:\Users\...\AppData\Local\Python\pythoncore-3.11-64\python.exe` | PSF-signed | ✅ 信任，但 ABI 不符（cp312 venv）|

`.venv-xanylabeling` 以 `uv venv --python 3.12` 建立，所有 `.pyd` 為 `cp312-win_amd64`，需要 Python 3.12 才能載入。系統上沒有 PSF-signed 的 Python 3.12。

### 程式碼已更新（等用戶操作後自動生效）

**`sidecar/python-engine/scripts/module_012/012_output.py`** 新增 `_find_venv_python_cmd()`：

1. 讀 `pyvenv.cfg` 的 `version_info` 欄位確認 venv Python 版本
2. 嘗試 `py.exe -3.X`（Windows Python Launcher，Microsoft-signed，WDAC 信任）
3. 嘗試 `%LOCALAPPDATA%\Programs\Python\PythonXYZ\python.exe` 等常見路徑
4. Fallback 到 pyvenv.cfg home → venv python.exe

### 需要用戶執行的操作

**方案 A：用 Python 3.11 重建 venv（推薦，不需安裝新 Python）**

```powershell
# 在專案根目錄執行
python -m uv venv --python 3.11 .venv-xanylabeling
python -m uv pip install --python .venv-xanylabeling\Scripts\python.exe --pre "x-anylabeling-cvhub[cpu]"
```

重建後 `pyvenv.cfg` 會記錄 `version_info = 3.11.x`，程式碼自動走 `py -3.11`（已安裝，WDAC 信任）。

**方案 B：安裝 Python 3.12 官方版（不需重建 venv）**

1. 下載 `python-3.12.x-amd64.exe` from [python.org](https://www.python.org/downloads/release/python-3128/)
2. 安裝時勾選「Install py launcher」
3. 重啟應用程式，程式碼自動走 `py -3.12`

### 預期結果

操作完成後不需任何程式碼修改，重啟 app 即可正常啟動 X-AnyLabeling。

---

## 修改的檔案清單

| 檔案 | 變更內容 |
|------|----------|
| `sidecar/python-engine/scripts/module_012/012_output.py` | 分頁自動跟隨 bug、強化圖 bug、WDAC 啟動邏輯 |
| `sidecar/python-engine/tools/sheet_runner.py` | RerunException 重拋、移除 polling loop |
| `sidecar/python-engine/tools/cv_framework_runner.py` | RerunException 重拋、移除 polling loop |

其餘 `docs/`、`engine.py`、`012_process.py`、`013_process.py`、`sheet.yaml` 為上一個 session 的變更（annotation path 改為影像同目錄），一併 commit。
