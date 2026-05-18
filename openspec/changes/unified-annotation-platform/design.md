# Design: Unified Annotation Platform (module_009)

**狀態**：草稿  
**日期**：2026-05-16

---

## 一、系統概觀

```
┌─────────────────────────────────────────────────────────────┐
│                    Electron Portal                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            annotation_runner.py (Streamlit)          │  │
│  │  ┌─────────────┐    ┌──────────────────────────────┐ │  │
│  │  │  Input 區   │    │   Annotation Master Table    │ │  │
│  │  │  (資料夾選擇) │    │   (即時狀態、操作按鈕)        │ │  │
│  │  └─────────────┘    └──────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │                            │
         ▼                            ▼
  annotation.sqlite            MCP annotation tools
  (video_assets,               (sidecar_start_tool,
   annotation_sessions,         annotation_launch_xanylabeling_project)
   frame_annotations)
         │
         ▼
  背景 tracking job (_worker.py)
  DINOv2 + Lucas-Kanade → 初始 bbox JSON
         │
         ▼
  X-AnyLabeling (外部工具，使用者手工修正)
```

---

## 二、模組結構

```
sidecar/python-engine/
├── scripts/
│   └── module_009/
│       ├── plugin.yaml              # runner: annotation_runner
│       ├── _config.py               # 讀寫 {CIM_LOG_DIR}/config/module_009.json
│       ├── _db.py                   # annotation.sqlite 存取層（DAL）
│       ├── _worker.py               # DINOv2+LK 背景追蹤 job（subprocess）
│       ├── _xany_launcher.py        # X-AnyLabeling 啟動、PID 監聽、解鎖邏輯
│       ├── 009_process.py           # 無 Streamlit；純計算 + DB 操作
│       ├── 009_runner.py            # annotation_runner 入口（單頁 Streamlit）
│       ├── 009_process_test.py      # pytest 測試
│       └── README.md
└── tools/
    └── annotation_runner.py         # 新 runner：載入 009_runner.py
```

**plugin.yaml**
```yaml
id: module_009
name: 統一標注平台
version: "1.0.0"
category: module
description: 影像與影片一體的標注管理系統，整合 DINOv2 追蹤與 X-AnyLabeling
author: system
tags: [annotation, video, image, tracking]
runner: annotation_runner
```

---

## 三、資料庫設計

**路徑**：`{CIM_LOG_DIR}/db/annotation.sqlite`

```sql
-- 所有資料來源（影片 or 圖片資料夾）
CREATE TABLE video_assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path   TEXT NOT NULL UNIQUE,   -- 絕對路徑（影片）或資料夾路徑（圖片集）
    asset_type  TEXT CHECK(asset_type IN ('video', 'image_dir')) NOT NULL,
    file_hash   TEXT,                   -- SHA256，用於重複偵測
    fps         REAL,                   -- 影片用；image_dir 為 NULL
    total_frames INTEGER,               -- 影片幀數；image_dir 為圖片數量
    duration_s  REAL,                   -- 影片長度；image_dir 為 NULL
    display_name TEXT,                  -- 顯示名稱（basename）
    created_at  TEXT DEFAULT (datetime('now'))
);

-- 每個 asset 的標注工作階段狀態
CREATE TABLE annotation_sessions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id              INTEGER NOT NULL REFERENCES video_assets(id),
    status                TEXT CHECK(status IN (
                              '未標記', '追蹤中', '標記中', '已標記', '已同步'
                          )) DEFAULT '未標記',
    xany_project_dir      TEXT,         -- X-AnyLabeling project 路徑
    tracking_job_pid      INTEGER,      -- 追蹤 job PID
    xany_pid              INTEGER,      -- X-AnyLabeling PID（process lock）
    locked_at             TEXT,
    annotation_count      INTEGER DEFAULT 0,   -- 已標注幀數
    last_summary          TEXT,         -- JSON：{frames, objects, avg_conf, updated_at}
    last_updated          TEXT DEFAULT (datetime('now')),
    synced_at             TEXT          -- 最後同步至 DB 的時間
);

-- 每幀的標注資料（含圖片的單幀 frame_idx=0）
CREATE TABLE frame_annotations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES annotation_sessions(id),
    frame_idx       INTEGER NOT NULL,          -- 圖片固定為 0
    annotation_json TEXT NOT NULL,             -- X-AnyLabeling JSON v6.0.0（完整）
    confidence_avg  REAL,                      -- 從 description 欄位解析
    source          TEXT CHECK(source IN ('tracking', 'manual', 'xanylabeling')),
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(session_id, frame_idx)
);

-- 索引
CREATE INDEX idx_sessions_asset ON annotation_sessions(asset_id);
CREATE INDEX idx_frames_session ON frame_annotations(session_id, frame_idx);
```

---

## 四、資料生命週期

```
1. 使用者選擇資料夾
   └→ 掃描影片（mp4/avi/mov）+ 圖片（jpg/png）
   └→ INSERT INTO video_assets（skip 已存在的）
   └→ INSERT INTO annotation_sessions（status='未標記'）

2. 使用者點「🛠️ 開啟標注」
   └→ 檢查 xany_pid 是否存活（process lock）
   └→ 若有歷史 → 從 frame_annotations 生成暫存 JSON
   └→ 啟動 _worker.py（DINOv2+LK 追蹤，status → '追蹤中'）
   └→ 追蹤完成 → 草稿 JSON 寫入 xany_project_dir
   └→ 啟動 X-AnyLabeling（帶入 project 路徑），記錄 xany_pid
   └→ status → '標記中'，鎖定列（UI disabled）

3. 使用者在 X-AnyLabeling 標注完，關閉軟體
   └→ PID 監聽（psutil）偵測進程結束
   └→ 掃描 xany_project_dir，解析新 JSON
   └→ UPSERT INTO frame_annotations
   └→ UPDATE annotation_sessions SET status='已標記', annotation_count=N, last_summary=...
   └→ xany_pid = NULL（解鎖）
   └→ 自動聚焦下一個 status='未標記' 的 asset

4. 使用者點「💾 存檔備份」（確認對話框：將存入 N 幀標注結果）
   └→ 讀取 frame_annotations WHERE session_id IN (已標記 sessions)
   └→ 寫入 DB（已是 annotation.sqlite，status → '已同步'）
   └→ 將暫存 JSON 移至 {xany_project_dir}/../backup/
```

---

## 五、UI 佈局設計

### annotation_runner.py（單頁 Streamlit，無 Input/Output 分頁）

```
┌──────────────────────────────────────────────────────────────┐
│  🗂 統一標注平台                    [● DB連線] [● MCP連線]    │
├──────────────────────────────────────────────────────────────┤
│  📁 資料來源                                                  │
│  [_______________資料夾路徑_______________] [📂 瀏覽] [載入]   │
│  篩選：[全部▼]  類型：[☑影片 ☑圖片]  搜尋：[________]         │
├──────────────────────────────────────────────────────────────┤
│  Annotation Master Table                                      │
│  # │ 名稱          │ 類型 │ 狀態     │ 幀數   │ 摘要ⓘ │ 操作  │
│  ──┼───────────────┼──────┼──────────┼────────┼───────┼────── │
│  1 │ cam_0516.mp4  │  🎬  │ 🟡 標記中 │ 45/240 │ hover │[🔒]  │
│  2 │ cam_0515.mp4  │  🎬  │ ⬜ 未標記 │  0/180 │  —    │[🛠️]  │
│  3 │ images/       │  🖼  │ 🟢 已標記 │ 32/32  │ hover │[🔍]  │
│  4 │ cam_0514.mp4  │  🎬  │ 🔵 已同步 │120/120 │ hover │[🔍]  │
├──────────────────────────────────────────────────────────────┤
│  [💾 存檔備份（2 筆待同步）]  ← 灰色 disabled 直到有已標記項目  │
└──────────────────────────────────────────────────────────────┘
```

### 操作按鈕狀態對應

| 狀態 | 按鈕 | 行為 |
|---|---|---|
| 未標記 | `[🛠️ 開啟標注]` | 啟動追蹤 + X-AnyLabeling |
| 追蹤中 | `[⏳ 追蹤中...]`（disabled）| 等待 |
| 標記中 | `[🔒 標注中]`（disabled）| X-AnyLabeling 使用中 |
| 已標記 | `[🔍 修正]` | 重開 X-AnyLabeling（帶現有標注）|
| 已同步 | `[🔍 修正]` | 同上，修正後 status 回到「已標記」|

### 摘要 Tooltip（hover 顯示）

```
標注摘要
─────────────────
幀數：45 / 總幀：240
物件：眼睛×34  鼻子×28  嘴巴×21
平均信心：0.87（DINOv2）
最後標注：2026-05-16 14:22
```

### 單幀校正流程（Row 展開）

點「🔍 修正」→ 列下方展開縮圖列（所有已標注幀）  
→ 使用者點選目標幀縮圖  
→ 系統以單幀模式啟動 X-AnyLabeling（只傳那一幀的 JSON）  
→ 存檔後只更新 `frame_annotations` 的該列，不影響其他幀

---

## 六、追蹤背景 Job（_worker.py）

**輸入**（從 annotation_sessions 讀取）：
```json
{
  "asset_id": 1,
  "file_path": "/path/to/video.mp4",
  "anchor_frame_idx": 60,
  "anchor_bboxes": [{"label": "眼睛", "x1": 100, "y1": 80, "x2": 150, "y2": 120}],
  "time_range_sec": [-1.0, 1.0],
  "labels": ["眼睛", "鼻子", "嘴巴"],
  "session_id": 1
}
```

**追蹤流程**：
1. 拆幀 → `{xany_project_dir}/frames/frame_{idx:06d}.jpg`
2. DINOv2 anchor 特徵提取（DINO_AVAILABLE 判斷）
3. LK optical flow 追蹤（9 點網格，median displacement）
4. 合成信心：`0.5 × flow_conf + 0.5 × dino_conf`
5. 每幀輸出 X-AnyLabeling JSON → `{xany_project_dir}/annotations/`
6. INSERT INTO frame_annotations（source='tracking'）
7. 完成後 UPDATE annotation_sessions SET status='標記中' → 觸發 X-AnyLabeling 啟動

**DINO_AVAILABLE = False**（無 torch）→ flow-only，信心 = flow_conf，正常執行

---

## 七、Process Lock 機制

```python
import psutil

def acquire_lock(session_id: int, pid: int, db: Connection) -> bool:
    row = db.execute(
        "SELECT xany_pid FROM annotation_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if row and row["xany_pid"]:
        if psutil.pid_exists(row["xany_pid"]):
            return False  # 真的還在跑
        # PID 已死亡，自動釋放
    db.execute(
        "UPDATE annotation_sessions SET xany_pid=?, locked_at=datetime('now') WHERE id=?",
        (pid, session_id)
    )
    return True

def release_lock(session_id: int, db: Connection):
    db.execute(
        "UPDATE annotation_sessions SET xany_pid=NULL, locked_at=NULL WHERE id=?",
        (session_id,)
    )
```

---

## 八、009_process.py 公開 API

```python
# 資產管理
scan_folder(folder_path: str) -> list[dict]           # 掃描資料夾，回傳 asset 清單
load_assets(db_path: str) -> list[dict]               # 從 DB 讀所有 assets + sessions

# 標注工作流
start_annotation(session_id: int, anchor_info: dict) -> dict   # 啟動追蹤 job
open_xanylabeling(session_id: int) -> dict            # 啟動 X-AnyLabeling（帶入 project）
open_single_frame(session_id: int, frame_idx: int) -> dict     # 單幀校正模式

# 狀態管理
get_session_status(session_id: int) -> dict           # 讀 annotation_sessions row
update_after_xany_close(session_id: int) -> dict      # 解析 JSON，更新 frame_annotations
sync_to_db(session_ids: list[int]) -> dict            # 歸檔已標記結果

# 工具
get_next_unannotated(db_path: str) -> int | None      # 回傳下一個未標記 asset_id
generate_summary(session_id: int) -> dict             # 計算摘要（frames, objects, conf）
```

---

## 九、與 module_006 的整合點

| 整合點 | 方式 |
|---|---|
| 標注格式 | 都用 X-AnyLabeling JSON v6.0.0，無轉換需本 |
| 標注類別 | module_009 有自己的 `{CIM_LOG_DIR}/config/module_009.json`，預設同 module_006 |
| 單幀校正 | 複用 X-AnyLabeling 啟動邏輯（_xany_launcher.py），不直接 import module_006 |
| 未來擴充 | module_006 可讀取 `annotation.sqlite` 的 frame_annotations 作為起點 |

---

## 十、設定系統（_config.py）

**路徑**：`{CIM_LOG_DIR}/config/module_009.json`

```json
{
  "annotation_labels": ["眼睛", "鼻子", "嘴巴"],
  "default_before_sec": 1.0,
  "default_after_sec": 1.0,
  "auto_advance": true,
  "backup_after_sync": true
}
```
