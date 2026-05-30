# module_016 — AI Pre-labeling（AI 自動預標注）

> 最後更新：2026-05-23

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `module_016` |
| Runner | `cv_framework` |
| Sheet | `sheet-annotation` |
| 上游依賴 | module_026（manifest） |

使用本地 YOLO 或影像分類模型對整批圖片做推論，結果寫成 X-AnyLabeling JSON，供人工用 module_012 修正。

---

## 推論模式

### YOLO（Object Detection）

- 支援 YOLOv5 / v8 / v11 `.pt` 權重（透過 `ultralytics` 套件）
- 每張圖輸出 `{stem}.json`，shapes 為 `rectangle` 類型

### Image Classifier（影像分類）

- 讀取 torchvision ResNet50 state_dict（標準 `.pt` checkpoint）
- 標籤來源：同名 `.json`（陣列或 `{index: label}` dict）或 `.txt`（每行一個 label），或 checkpoint 內的 `class_names` key
- 每張圖輸出 `{stem}.json`，shapes 為空陣列，分類結果寫入 `flags.classification`
- 同時更新 `module_012_classifications_{manifest_id[:12]}.json`，讓 module_015 / module_014 可讀取

---

## 架構

```
016_input.py   → 模型類型 radio、模型路徑瀏覽、信心分數 slider、覆蓋 checkbox
016_process.py → _run_yolo() / _run_classifier()、_write_xany_json() helper
016_output.py  → 摘要 metrics（成功 / 跳過 / 錯誤）+ 可篩選結果表格
_config.py     → 設定持久化 + shared manifest 解析
```

---

## Input Page（`016_input.py`）

- **不顯示 Manifest 選擇器**：自動從 `shared.json` 取
- **模型類型**：YOLO / Image Classifier（radio）
- **模型路徑**：text input + 📂 瀏覽按鈕（tkinter filedialog）
- **Confidence Threshold**：slider 0.01–1.0，預設 0.25
- **覆蓋已有標注**：預設不覆蓋（跳過已有 `.json` 的圖片）

---

## Process（`016_process.py`）

### `_xany_rect(label, x1, y1, x2, y2, score)`

建立標準 X-AnyLabeling rectangle shape dict。

### `_write_xany_json(file_path, shapes, img_w, img_h, flags)`

將 shapes + flags 寫成 `{stem}.json`（X-AnyLabeling 格式）。

### `_run_yolo(items, model_path, conf, overwrite)`

```
for each item:
  → 跳過（已有 .json 且 overwrite=False）
  → model(fp, conf) → boxes → _xany_rect × N → _write_xany_json
```

依賴 `ultralytics`；未安裝時回傳 `error_detail` 說明安裝指令。

### `_run_classifier(items, model_path, conf, overwrite, manifest_id)`

```
讀取 class labels（同名 .json/.txt 或 checkpoint["class_names"]）
→ 載入 ResNet50 state_dict
for each item:
  → transform + model inference → softmax → top-1
  → top_conf >= conf → _write_xany_json(flags={"classification": label})
                     → 更新 module_012 classifications JSON
  → top_conf < conf  → 記錄 "low_conf" 狀態
```

依賴 `torch` + `torchvision`。

### 跳過規則

| 條件 | 狀態 |
|------|------|
| `.json` 已存在且 `overwrite=False` | `skipped`（已有標注） |
| 信心分數 < threshold（Classifier 模式） | `low_conf` |
| 檔案不存在 | `error` |

---

## Output Page（`016_output.py`）

- **摘要 metrics**：總圖數 / 成功推論 / 跳過 / 錯誤
- **模式說明 caption**：YOLO Detection 或 Image Classifier
- **可篩選結果表格**：下拉篩選 全部 / 成功 / 跳過 / 信心不足 / 錯誤；分頁（每頁 100 筆）

---

## 安裝依賴

```bash
# YOLO 模式
pip install ultralytics

# Classifier 模式
pip install torch torchvision pillow
```

---

## 資料流

```
shared.json → manifest_id → manifest.sqlite → items (file_path)
model.pt (+ 可選 model.json/model.txt)
        │
        ▼
016_process.execute_logic()
  ├─ YOLO    → {image_dir}/{stem}.json（shapes: [rectangle, ...]）
  └─ Classifier → {image_dir}/{stem}.json（flags: {classification, confidence}）
                  module_012_classifications_{mid[:12]}.json（更新）
```

---

## 常見問題

### Classifier 載入後全部預測同一個 class

ResNet50 在 `load_state_dict(strict=False)` 模式下僅載入可對應的權重。若模型架構與 ResNet50 差異過大，分類頭可能未正確初始化。請確認 `.pt` 檔案是 ResNet50 的標準 state_dict。

### YOLO 推論後標注框與實際圖片偏移

確認影像解析度與訓練時一致。`orig_shape` 取自 YOLO 輸出（非檔案 metadata），通常是正確的。
