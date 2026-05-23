# sheet-annotation_workflow — 標注作業流程

> 最後更新：2026-05-23

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `annotation_workflow` |
| Sheet | `sheet-annotation_workflow` |
| Runner | `sheet_runner` |
| 主要模組 | module_010 → 012 → 013 → 014 → 016 → 017 → 018 |

此 sheet 將資料來源建立、X-AnyLabeling 標注、整理、多格式匯出、進度統計、AI 預標注串成完整流程。X-AnyLabeling JSON 保持在影像同目錄，分類結果保存於 `{CIM_LOG_DIR}/config/module_012_classifications_*.json`。

---

## 流程

```
module_010  📦 Data Feeder
  └─ 建立 manifest + 寫 shared.json（last_manifest_id）
        │
        ▼
module_016  🤖 AI Pre-labeling（可選）
  ├─ YOLO → {stem}.json（rectangle shapes）
  └─ Classifier → {stem}.json（flags.classification）+ 更新分類 config
        │
        ▼
module_012  🏷️ Annotation Session
  ├─ 讀 shared.json 取 manifest_id
  ├─ 開啟 X-AnyLabeling，標注 JSON 寫到影像同目錄
  └─ 分類寫入 module_012_classifications_*.json
        │
        ▼
module_013  🔄 Update
  ├─ 確認影像同目錄 .json 存在（B 操作）
  ├─ 依分類複製圖片到 export 子資料夾（C 操作）
  └─ 寫出 source_folder/update_result_{timestamp}.json
        │
        ▼
module_014  📤 Export
  ├─ 支援格式：COCO JSON / YOLO txt / Pascal VOC / ImageFolder / CSV
  ├─ 可選 Train/Val/Test 分割
  └─ 寫 annotation_exports 記錄（供管理中心讀取）
        │
        ▼
module_017  📊 管理中心
  ├─ [統計總覽 tab]
  │   ├─ 標注進度（BBox / 分類完成度 + 進度條）
  │   ├─ 標注健康度（最後活動時間、每圖框數、尚未標注數）
  │   ├─ BBox 標籤分布 + 分類標籤分布（bar chart）
  │   └─ 匯出記錄（最近一次置頂 + 完整歷史）
  └─ [標籤管理 tab]
      ├─ 掃描全 Manifest 的 label 統計
      ├─ 近似重複標籤偵測（fuzzy match threshold=0.8）
      └─ Rename / Merge / Delete（全部 atomic write）
        │
        ▼
module_018  🖼️ Review Gallery（可選）
  ├─ PIL BBox overlay 縮圖（per-label 色彩，mtime LRU cache）
  ├─ 分頁格狀瀏覽（30/頁）+ label / 狀態篩選
  ├─ 詳細檢視 + 「在 X-AnyLabeling 開啟」按鈕
  └─ 「Flag for re-annotation」（寫 .flag sidecar，縮圖顯示黃框）
```

---

## Tab 順序

| tab_order | plugin_id | 頁籤標籤 |
|-----------|-----------|---------|
| 0 | module_010 | 📦 Data Feeder |
| 1 | module_012 | 🏷️ Annotation |
| 2 | module_013 | 🔄 Update |
| 3 | module_014 | 📤 Export |
| 4 | module_016 | 🤖 AI Pre-labeling |
| 5 | module_017 | 📊 管理中心 |
| 6 | module_018 | 🖼️ Review Gallery |

> module_015（Dashboard）已於 2026-05-23 合併至 module_017，從 sheet.yaml 移除。

---

## 共用資料契約

| 檔案 | 責任 |
|------|------|
| `{CIM_LOG_DIR}/config/shared.json` | module_010 寫入最新 manifest；012/013/014/016/017 讀取 |
| `{CIM_LOG_DIR}/db/manifest.sqlite` | DatasetManifest、manifest items、annotation_exports |
| `{CIM_LOG_DIR}/config/module_012_classes_{manifest_id[:12]}.txt` | X-AnyLabeling label 清單 |
| `{CIM_LOG_DIR}/config/module_012_classifications_{manifest_id[:12]}.json` | 分類結果；012 寫、013/014/016/017 讀 |
| `{CIM_LOG_DIR}/xanylabeling_state/module_012_{manifest_id[:12]}/` | X-AnyLabeling GUI 暫存狀態 |
| `{image_dir}/{image_stem}.json` | X-AnyLabeling 原生 LabelMe JSON（所有模組讀寫） |

---

## 注意事項

- 切換資料集時，回到 Data Feeder 重新執行，讓 `shared.json` 更新。
- AI Pre-labeling 產生的預標注可以直接在 Annotation 頁籤修正；覆蓋選項預設關閉，已有人工標注的圖片不會被覆蓋。
- Export 的輸出目錄應放在原始圖片資料夾外，避免下一次 Data Feeder 掃描到匯出副本。
- 新增模組 tab 時，透過 `engine.py _initialize()` 的 `INSERT OR IGNORE` migration 寫入 `sheet_tabs` 資料表；不可依賴 `sheet.yaml` 自動同步（DB 是 runtime source of truth）。
