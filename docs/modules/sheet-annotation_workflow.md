# sheet-annotation_workflow — 標注作業流程

> 最後更新：2026-05-19

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `annotation_workflow` |
| Sheet | `sheet-annotation_workflow` |
| Runner | `sheet_runner` |
| 主要模組 | module_010 → module_012 → module_013 |

此 sheet 將資料來源建立、X-AnyLabeling 標注、分類整理串成一條輕量流程。它不使用 `annotation-core`，X-AnyLabeling JSON 保持在影像同目錄，分類結果保存於 `{CIM_LOG_DIR}/config/module_012_classifications_*.json`。

---

## 流程

```
module_010 Data Feeder
  └─ 建立 manifest + shared.json
        │
        ▼
module_012 Annotation Session
  ├─ 讀 shared.json:last_manifest_id
  ├─ 開啟 X-AnyLabeling，標注 JSON 寫到影像同目錄
  └─ 分類寫入 config/module_012_classifications_*.json
        │
        ▼
module_013 Update
  ├─ B：確認影像同目錄的同名 .json
  ├─ C：依分類複製圖片到 export 子資料夾
  └─ 寫出 source_folder/update_result_{timestamp}.json
```

---

## 共用資料契約

| 檔案 | 責任 |
|------|------|
| `{CIM_LOG_DIR}/config/shared.json` | module_010 寫入最新 manifest，012/013 讀取 |
| `{CIM_LOG_DIR}/db/manifest.sqlite` | DatasetManifest 與 manifest items |
| `{CIM_LOG_DIR}/config/module_012_classes_{manifest_id[:12]}.txt` | X-AnyLabeling label 清單 |
| `{CIM_LOG_DIR}/config/module_012_classifications_{manifest_id[:12]}.json` | module_012 分類結果，module_013 讀取 |
| `{CIM_LOG_DIR}/xanylabeling_state/module_012_{manifest_id[:12]}/` | X-AnyLabeling GUI 暫存狀態 |
| `{image_dir}/{image_stem}.json` | X-AnyLabeling 原生 LabelMe JSON |

---

## 注意事項

- 切換資料集時，回到 Data Feeder 重新執行，讓 `shared.json` 更新。
- C 操作的 export 目錄應放在原始圖片資料夾外，避免下一次 Data Feeder 掃描到整理後副本。
- B 操作是確認影像同目錄標注 JSON 已存在；來源和目標相同時不做實際複製。
