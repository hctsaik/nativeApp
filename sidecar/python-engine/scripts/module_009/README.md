# module_009 — 統一標注平台

**Runner**: `annotation_runner.py` (單頁 Streamlit，無 Input/Output 分頁)

## 快速啟動

```bash
cd sidecar/python-engine
python -m pytest scripts/module_009/009_process_test.py   # 14 tests, 0 failures
```

## 檔案說明

| 檔案 | 說明 |
|---|---|
| `plugin.yaml` | 模組描述，runner=annotation_runner |
| `_config.py` | 讀寫 `{CIM_LOG_DIR}/config/module_009.json` |
| `_db.py` | annotation.sqlite DAL（3 張表 + acquire/release lock） |
| `_worker.py` | DINOv2+LK 追蹤背景 job，subprocess 執行 |
| `_xany_launcher.py` | X-AnyLabeling 啟動、PID 監聽、sync_to_db |
| `009_process.py` | 公開 API（無 Streamlit import） |
| `009_runner.py` | Streamlit 單頁 UI（Master Table） |
| `009_process_test.py` | pytest 測試（14 項） |

## 資料庫

**路徑**: `{CIM_LOG_DIR}/db/annotation.sqlite`

三張表：`video_assets` / `annotation_sessions` / `frame_annotations`

狀態流程：`未標記` → `追蹤中` → `標記中` → `已標記` → `已同步`

## 公開 API（009_process.py）

```python
scan_folder(folder_path)                    # 掃描資料夾，INSERT OR IGNORE
load_assets()                               # 讀所有 assets + sessions
start_annotation(session_id, anchor_info)   # 啟動追蹤 job
open_xanylabeling(session_id)               # 啟動 X-AnyLabeling
open_single_frame(session_id, frame_idx)    # 單幀校正模式
get_session_status(session_id)              # 讀 session row
update_after_xany_close(session_id)         # 解析 JSON → 更新 frame_annotations
sync_to_db(session_ids)                     # 歸檔至 backup/，status='已同步'
get_next_unannotated()                      # 下一個 status='未標記' 的 session_id
generate_summary(session_id)                # {frame_count, avg_confidence, object_counts}
poll_tracking_status(session_id)            # 查追蹤進度，若完成自動啟動 X-AnyLabeling
```

## 依賴

- `psutil` — PID 監聽（已在 requirements.txt）
- `cv2` — 影片拆幀、optical flow
- `torch` / `transformers` — DINOv2（可選，無則 flow-only）
- `streamlit-autorefresh` — 2 秒輪詢
