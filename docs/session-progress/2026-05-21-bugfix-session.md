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

## ✅ Bug 4：X-AnyLabeling 啟動失敗（WDAC 封鎖）

### 症狀
點擊「🖊 標注工具」出現：`啟動失敗：[WinError 4551] 應用程式控制原則已封鎖此檔案`

### 根本原因分析

| 執行檔 | 來源 | WDAC 狀態 |
|--------|------|-----------|
| `.venv-xanylabeling\Scripts\xanylabeling.exe` | uv trampoline (46KB) | ❌ 封鎖 |
| `.venv-xanylabeling\Scripts\python.exe` | uv trampoline (46KB) | ❌ 封鎖 |
| `AppData\Roaming\uv\python\cpython-3.12-...\python.exe` | uv 下載，未簽章 (91KB) | ❌ 封鎖 |
| `C:\Users\...\AppData\Local\Python\pythoncore-3.14-64\python.exe` | PSF-signed | ✅ 信任，但 ABI 不符（cp312 venv）|
| `C:\Users\...\AppData\Local\Python\pythoncore-3.11-64\python.exe` | PSF-signed | ✅ 信任，已重建 venv 後可用 |

修復前 `.venv-xanylabeling` 以 `uv venv --python 3.12` 建立，所有 `.pyd` 為 `cp312-win_amd64`，需要 Python 3.12 才能載入。系統上沒有 PSF-signed 的 Python 3.12。

### 程式碼已更新

**`sidecar/python-engine/scripts/module_012/012_output.py`** 新增 `_find_venv_python_cmd()`：

1. 讀 `pyvenv.cfg` 的 `version_info` 欄位確認 venv Python 版本
2. 嘗試 `py.exe -3.X`（Windows Python Launcher，Microsoft-signed，WDAC 信任）
3. 嘗試 `%LOCALAPPDATA%\Programs\Python\PythonXYZ\python.exe` 等常見路徑
4. Fallback 到 pyvenv.cfg home → venv python.exe

### 本次已完成的操作

已用 Python 3.11 重建 venv（不需安裝新 Python）：

```powershell
# 在專案根目錄執行
python -m uv venv --python 3.11 --clear .venv-xanylabeling
python -m uv pip install --python .venv-xanylabeling\Scripts\python.exe --pre "x-anylabeling-cvhub[cpu]"
```

重建後 `pyvenv.cfg` 記錄 `version_info = 3.11.9`，程式碼自動走 `py -3.11`（已安裝，WDAC 信任）。

### 預期結果

重啟 app 後，點擊「🖊 標注工具」應可透過 `py -3.11` 正常啟動 X-AnyLabeling。

### 已驗證

```powershell
py -3.11 -c "import sys; sys.path.insert(0, r'.venv-xanylabeling\Lib\site-packages'); import anylabeling; print(anylabeling.__version__)"
py -3.11 -c "import sys; sys.path.insert(0, r'.venv-xanylabeling\Lib\site-packages'); from anylabeling.app import main; print('anylabeling.app main ok')"
py -3.11 -c "import sys; sys.path.insert(0, r'.venv-xanylabeling\Lib\site-packages'); from anylabeling.app import main; sys.argv=['xanylabeling','checks']; main()"
```

結果：
- `anylabeling` 版本 `4.0.0-beta.7`
- `from anylabeling.app import main` 成功
- `xanylabeling checks` 成功，Python Version 顯示 `3.11.9`

---

## 修改的檔案清單

| 檔案 | 變更內容 |
|------|----------|
| `sidecar/python-engine/scripts/module_012/012_output.py` | 分頁自動跟隨 bug、強化圖 bug、WDAC 啟動邏輯、X-AnyLabeling 標注讀回刷新 |
| `sidecar/python-engine/scripts/module_012/012_output_test.py` | Output 層標注 JSON 搜尋回歸測試 |
| `sidecar/python-engine/tools/sheet_runner.py` | RerunException 重拋、移除 polling loop |
| `sidecar/python-engine/tools/cv_framework_runner.py` | RerunException 重拋、移除 polling loop |

其餘 `docs/`、`engine.py`、`012_process.py`、`013_process.py`、`sheet.yaml` 為上一個 session 的變更（annotation path 改為影像同目錄），一併 commit。

---

## ✅ Bug 5：X-AnyLabeling 標注後平台沒有自動讀回

### 症狀

X-AnyLabeling 已 autosave 出 LabelMe JSON，例如：

```text
C:\code\claude\backup\LabelMe_Dino_old\video\car_1\frame_00000.json
```

但 `module_012` Output 頁仍顯示 `已標注 = 0`，看起來像沒有回寫到平台。

### 根本原因

`012_output.py` 有標注狀態快取，但 Output 頁沒有實際啟用原本文件寫的 30 秒 autorefresh；使用者從 X-AnyLabeling 回來後，如果 Streamlit 沒有 rerun，就不會重新掃描磁碟。

另外當時 `012_process.py` 與 `012_output.py` 的搜尋邏輯不一致，後續已統一為只查影像同目錄同名 `.json`。

### 修法（已套用）

**檔案：** `sidecar/python-engine/scripts/module_012/012_output.py`

1. 加回 `st_autorefresh(interval=30_000)`，每 30 秒自動重新檢查標注檔。
2. 新增「重新掃描標注」按鈕，清除 `m012_items` / `m012_mtimes` / `m012_cache_mid` 後立即 rerun。
3. `_find_annotation()` 對齊 process 層，只找影像同目錄同名 `.json`。
4. 新增 `012_output_test.py`，覆蓋同目錄 JSON 與非同目錄 JSON 不讀取。

### 已驗證

```powershell
python -m py_compile sidecar/python-engine/scripts/module_012/012_output.py
python -m pytest sidecar/python-engine/scripts/module_012/012_output_test.py sidecar/python-engine/scripts/module_012/012_process_test.py -q
```

結果：`3 passed`

---

## ✅ Bug 6：移除 annotation_workflow 的舊工作目錄依賴

### 需求

annotation_workflow 不再建立或讀取舊的 `annotation_*` 工作資料夾。標注 JSON 必須留在影像同目錄，分類與 X-AnyLabeling 輔助檔改存到 log/config/state。

### 修法（已套用）

**`module_012`**
- Input 不再回傳舊路徑參數
- Process 不再建立 annotation 工作資料夾
- 標注偵測只讀 `Path(image).with_suffix(".json")`
- labels 檔改存 `{CIM_LOG_DIR}/config/module_012_classes_{manifest_id[:12]}.txt`
- 分類檔改存 `{CIM_LOG_DIR}/config/module_012_classifications_{manifest_id[:12]}.json`
- X-AnyLabeling GUI state 改存 `{CIM_LOG_DIR}/xanylabeling_state/module_012_{manifest_id[:12]}/`

**`module_013`**
- 分類改讀 `{CIM_LOG_DIR}/config/module_012_classifications_{manifest_id[:12]}.json`
- 預設整理輸出改為 `{CIM_LOG_DIR}/exports/module_013_{manifest_id[:12]}/`
- 若 source folder 無法推算，update result fallback 到上述 exports 目錄

### 已盤點

以下程式碼已確認沒有舊工作目錄相關字串：

```powershell
rg -n "<old-work-dir-pattern>" sidecar/python-engine/scripts/module_010 sidecar/python-engine/scripts/module_012 sidecar/python-engine/scripts/module_013
```

### 已驗證

```powershell
python -m pytest sidecar/python-engine/scripts/module_012/012_output_test.py sidecar/python-engine/scripts/module_012/012_process_test.py sidecar/python-engine/scripts/module_013/013_process_test.py -q
python -m py_compile sidecar/python-engine/scripts/module_012/012_input.py sidecar/python-engine/scripts/module_012/012_process.py sidecar/python-engine/scripts/module_012/012_output.py sidecar/python-engine/scripts/module_012/_config.py sidecar/python-engine/scripts/module_013/013_input.py sidecar/python-engine/scripts/module_013/013_process.py sidecar/python-engine/scripts/module_013/013_output.py sidecar/python-engine/scripts/module_013/_config.py
```

結果：`6 passed`

---

## ✅ Bug 7：Output autorefresh 改由 Annotation Input 設定

### 需求

原本 `module_012` Output 頁固定每 30 秒 `st_autorefresh`。改成在 Annotation Input 頁可設定啟用/停用與刷新間隔。

### 修法（已套用）

**`module_012/_config.py`**
- 新增 `autorefresh_enabled`，預設 `true`
- 新增 `autorefresh_seconds`，預設 `10`

**`module_012/012_input.py`**
- 新增「自動刷新」區塊
- 提供 checkbox 控制是否啟用
- 提供 5–300 秒 number input 控制間隔

**`module_012/012_process.py`**
- 接收並 clamp `autorefresh_seconds`
- 保存設定到 `module_012.json`
- 回傳設定給 Output

**`module_012/012_output.py`**
- 不再硬編碼 30 秒
- 依 `autorefresh_enabled` / `autorefresh_seconds` 決定是否呼叫 `st_autorefresh`
- 頁頭顯示目前自動重新掃描狀態

### 後續調整

- 預設刷新間隔由 30 秒改為 10 秒。
- 點擊某筆「🖊 標注工具」時，會先把 `m012_selected_idx` 切到該筆，再開啟 X-AnyLabeling；回到頁面時左側高亮與右側 Detail Panel 會對應同一張影像。

---

## ✅ Bug 8：Annotation Input 支援選擇標注工具

### 需求

Annotation Input 頁讓使用者選擇標注工具，目前支援：

- X-AnyLabeling
- LabelMe

### 修法（已套用）

**`module_012/_config.py`**
- 新增 `annotation_tool`，預設 `x-anylabeling`

**`module_012/012_input.py`**
- 新增「標注工具」selectbox
- 將選擇值回傳給 process

**`module_012/012_process.py`**
- 接收並保存 `annotation_tool`
- 新增 `get_labelme_exe()`：
  1. `LABELME_EXE`
  2. sibling `LabelMe_Dino/.venv/Scripts/labelme.exe`
  3. repo-local `LabelMe_Dino/.venv/Scripts/labelme.exe`
  4. PATH `labelme`
- 回傳 `labelme_exe` 給 Output

**`module_012/012_output.py`**
- 新增 `_launch_annotation_tool()` 分派器
- `x-anylabeling` 走原本 WDAC-safe X-AnyLabeling 啟動
- `labelme` 走 `_launch_labelme()`，輸出到影像同目錄同名 JSON

---

## ✅ Bug 9：縮圖 hover preview 沒有展開

### 症狀

滑鼠移到左側縮圖上時，preview 視窗沒有出現。

### 根本原因

原本 hover preview 依賴 `components.html()` 注入 JavaScript 到 parent frame，再用 `MutationObserver` 綁定 `data-m012p` 圖片。這在 Streamlit iframe / DOM 隔離下不穩定，而且失敗時被 `catch` 靜默吞掉。

### 修法（已套用）

**`module_012/012_output.py`**
- 移除 parent-frame JS popup 綁定
- 改用純 HTML/CSS hover preview：
  - `_thumb_html()` 直接輸出 `.m012-thumb` + `.m012-preview`
  - `.m012-thumb:hover .m012-preview { display: block; }`
- 新增 `_make_preview()` / `_make_ann_preview()`，preview 使用較大的 640x480 快取圖，不再放大小縮圖

### 已驗證

```powershell
python -m pytest sidecar/python-engine/scripts/module_012/012_output_test.py sidecar/python-engine/scripts/module_012/012_process_test.py sidecar/python-engine/scripts/module_013/013_process_test.py -q
```

結果：`11 passed`

---

## ✅ Bug 10：Annotation Input layout 簡化與精進

### 需求

自動掃描速度預設維持 `10s`，並透過 multi-agent 討論 Annotation Input 頁面是否有更簡化、清楚的 layout。

### Multi-agent 結論

- Input 頁應定位為「開始標注前確認」，不是完整設定中心。
- 主路徑只保留「目前資料集」與「標注類別」。
- 「圖片快速分類」屬於可選功能，收進 expander。
- 「標注工具」與「自動重新掃描」屬於進階設定，收進 expander。
- 保留 `render_input()` 回傳契約，避免影響 `012_process.py`、`012_output.py`、`module_013`。

### 修法（已套用）

**`module_012/012_input.py`**
- 標題改為「開始標注前確認」。
- Manifest info bar 改成 `目前資料集：<name>｜<N> 張圖片`。
- 移除 1/2/3/4 的步驟式版面。
- 標注類別成為主區塊，顯示將建立的類別數。
- 標注類別預設改為空白，避免 `物件A / 物件B / 物件C` 被誤用。
- 新增空白行忽略與重複類別提示。
- 「分類類別」改名為「圖片快速分類，可選」，並收進 expander。
- 「標注工具」與自動重新掃描設定收進「進階設定」。
- 自動重新掃描預設仍為啟用、每 `10` 秒。

**`module_012/_config.py`**
- 預設 `annotation_labels` 改為空陣列。

**測試**
- 新增 `012_input_test.py`，驗證：
  - 無 manifest 時回傳安全預設值。
  - Input layout 調整後仍保留回傳契約。
  - `LabelMe` / `X-AnyLabeling` canonical value 映射仍正確。
  - labels 與 classification labels 會 trim、忽略空白行。
  - 新 config 預設 labels 為空白。

### 已驗證

```powershell
python -m pytest sidecar/python-engine/scripts/module_012/012_input_test.py sidecar/python-engine/scripts/module_012/012_output_test.py sidecar/python-engine/scripts/module_012/012_process_test.py sidecar/python-engine/scripts/module_013/013_process_test.py -q
```

結果：`14 passed`

---

## ✅ Bug 11：補強 X-AnyLabeling 版本與 security 文件/測試

### 需求

補上相關文件與測試，特別是 X-AnyLabeling 版本與 security 相關限制，避免未來又改回會被 WDAC 封鎖或會連外更新檢查的啟動方式。

### 固定契約

- X-AnyLabeling runtime：`x-anylabeling-cvhub[cpu]`
- 已驗證版本：`4.0.0-beta.7`
- 已驗證 Python：`3.11.9`
- 啟動方式：用 `py -3.11 -c "import sys; sys.path.insert(...); from anylabeling.app import main; main()"`
- 不直接執行 `.venv-xanylabeling\Scripts\xanylabeling.exe`
- 必須保留 `--nodata --autosave --no-auto-update-check`
- classes file 存在時必須保留 `--labels <file> --validatelabel exact`
- module_012 標注 JSON 固定寫到影像同目錄同名 `.json`

### 修法（已套用）

**測試**
- `012_output_test.py` 新增 WDAC/security regression：
  - `_find_venv_python_cmd()` 會讀 `pyvenv.cfg` 的 `version_info = 3.11.9` 並優先使用 `py -3.11`
  - `_launch_xany()` 不直接把 `xanylabeling.exe` 放進 command
  - command 會透過 trusted Python `-c` 載入 venv `site-packages`
  - command 保留 `--nodata --autosave --no-auto-update-check`
  - command 保留 `--output <image_dir>`
  - command 保留 `--labels` 與 `--validatelabel exact`

**文件**
- `docs/XANYLABELING_INTEGRATION.md`
  - 新增「目前鎖定的 runtime 與安全契約」
  - 明確標出 module_012 使用影像同目錄 JSON，不使用舊式 `frames/annotations`
  - 將舊式批次專案結構標示為 annotation-core / module_006 用
- `docs/components/ANNOTATION_XANYLABELING.md`
  - 更新 WDAC-safe 驗證方式
  - 移除直接執行 trampoline 的驗證指令
  - 加上 module_012 不可改動的安全限制
- `docs/modules/module_012.md`
  - 新增 X-AnyLabeling security/runtime contract
- `CLAUDE.md`
  - 常見錯誤補上不要改回直接執行 `xanylabeling.exe`
