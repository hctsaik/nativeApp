# 需求：CV 框架 Hello World 範本模組（module_002）

## 目的

建立一個**最簡單可運作的模組**，作為兩個用途：

1. **框架驗收**：確認 input → process → output 三層架構端到端可運作
2. **開發範本**：讓開發者知道「建立新模組」的標準流程與檔案結構

---

## 功能說明

### 模組名稱
**影像資訊讀取（Image Metadata Reader）**

### 測試資料
使用 `sidecar/python-engine/tools/road.png` 作為固定測試圖片，不需使用者上傳。

### Input 頁籤（`002_input.py`）

使用者看到：
- 圖片預覽（顯示 road.png）
- 一個 Inputbox：「Memo / 備註」（讓 User 自由輸入文字）
- 按下「▶ 執行」後送出

`render_input()` 回傳：
```python
{
    "image_path": str,          # road.png 的絕對路徑
    "memo": str,                # 使用者輸入的備註
}
```

### Process 層（`002_process.py`）

`execute_logic(params)` 接收上面的 dict，純函式：
- 開啟 `image_path`，讀取解析度（width, height）
- 讀取檔案大小（bytes）
- 格式化為可顯示的文字

回傳：
```python
{
    "filename": str,            # 檔案名稱（不含路徑）
    "resolution": (int, int),   # (width, height)
    "file_size_bytes": int,
    "file_size_kb": float,      # 四捨五入到小數點後 2 位
    "memo": str,                # 原樣帶入
}
```

**規範**：
- 禁止 `import streamlit`
- 不依賴任何 Streamlit session_state
- 可被 pytest 直接測試

### Output 頁籤（`002_output.py`）

`render_output(result)` 顯示：
- 一個 Streamlit 表格（`st.table` 或 `st.dataframe`），欄位：

| 欄位       | 值                           |
|-----------|------------------------------|
| 檔案名稱   | road.png                     |
| 解析度     | 1280 × 720                   |
| 檔案大小   | 245,123 bytes（239.4 KB）    |
| Memo       | 使用者輸入的文字              |

---

## 為什麼這個模組很重要

1. **最小可運作**：只用 stdlib（PIL/cv2 讀圖，os.path.getsize）+ Streamlit，無複雜邏輯
2. **框架契約的活說明**：`render_input() → dict`、`execute_logic(params) → dict`、`render_output(result)` 三行 code 就能說清楚整個框架
3. **unit test 的錨點**：`002_process_test.py` 測試的是「給定 road.png 路徑，回傳的 dict 是否符合預期欄位與型別」，這個測試永遠不會因為 UI 改動而失敗
4. **skill 範本**：完成後把整個流程（建立資料夾、三個檔案、測試）寫成 `/new-cv-module` skill，讓以後生成新模組只需要一個指令

---

## 完成後同步工作

1. 更新 `openspec/changes/cv-modular-tool-framework/design.md`，加入「如何使用框架建立新模組」的步驟說明（以 module_002 為例）
2. 建立 `.claude/commands/new-cv-module.md` skill（Phase 3 of cv-modular-tool-framework）
3. 加入 unit test：給定 road.png 真實路徑，驗證 `execute_logic` 回傳的欄位型別與值範圍
