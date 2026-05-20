# X-AnyLabeling 整合指南

> 本文件說明如何在獨立 Python 專案中安裝、啟動，並與 X-AnyLabeling 進行檔案式協作標注。

---

## 1. 安裝

### 建立專用虛擬環境

X-AnyLabeling 需安裝在獨立的 venv，不與主程式共用（其 PyQt5 依賴會與 headless OpenCV 衝突）。

```powershell
# 安裝 uv（快速套件管理器）
python -m pip install -U uv

# 建立 Python 3.11 獨立 venv
# 本機 WDAC 會封鎖 uv 下載的 unsigned Python 3.12 runtime；
# 3.11 可透過受信任的 Windows Python Launcher 啟動。
python -m uv venv --python 3.11 .venv-xanylabeling

# 安裝 x-anylabeling-cvhub（CPU 版本）
python -m uv pip install --python .venv-xanylabeling\Scripts\python.exe `
    --pre "x-anylabeling-cvhub[cpu]"

# 驗證安裝（WDAC-safe，不直接執行 uv trampoline exe）
py -3.11 -c "import sys; sys.path.insert(0, r'.venv-xanylabeling\Lib\site-packages'); from anylabeling.app import main; sys.argv=['xanylabeling','checks']; main()"
```

> 目前驗證通過的版本：**4.0.0-beta.7**  
> 目前本機驗證的 Python 版本：**3.11.9**
> `.venv-xanylabeling/` 應加入 `.gitignore`。

### 可執行檔路徑解析順序

| 優先順序 | 來源 |
|:---:|---|
| 1 | 環境變數 `XANYLABELING_EXE` |
| 2 | 專案根目錄 `.venv-xanylabeling\Scripts\xanylabeling.exe` |
| 3 | 系統 `PATH` 中的 `xanylabeling` |

---

## 2. 磁碟專案結構

X-AnyLabeling 開啟目錄後，讀寫以下結構：

```
{project_dir}/
│
├── frames/                     ← 輸入影像（X-AnyLabeling 讀取）
│   ├── frame_000000.jpg
│   ├── frame_000001.jpg
│   └── ...
│
├── classes.txt                 ← 標籤清單（每行一個類別，UTF-8）
│
├── annotations/                ← 標注 JSON（X-AnyLabeling 讀寫）
│   ├── frame_000000.json
│   └── ...
│
└── .xanylabeling/              ← GUI 暫存狀態（自動建立）
    ├── *_config.json
    └── *_state.json
```

### 事前準備步驟

```python
import shutil
from pathlib import Path

def prepare_project(project_dir: Path, labels: list[str]) -> None:
    (project_dir / "frames").mkdir(parents=True, exist_ok=True)
    (project_dir / "annotations").mkdir(parents=True, exist_ok=True)

    # 1. 將影像複製到 frames/ （六位數零補格式）
    for i, src in enumerate(sorted(image_paths)):
        dst = project_dir / "frames" / f"frame_{i:06d}.jpg"
        shutil.copy2(src, dst)

    # 2. 寫入標籤清單
    (project_dir / "classes.txt").write_text(
        "\n".join(labels), encoding="utf-8"
    )
```

---

## 3. 啟動 X-AnyLabeling

### 開啟整個 frames 目錄（批次標注）

```python
import subprocess
from pathlib import Path

def launch_xanylabeling(project_dir: Path, exe: str) -> subprocess.Popen:
    images_dir   = project_dir / "frames"
    labels_dir   = project_dir / "annotations"
    work_dir     = project_dir / ".xanylabeling"
    classes_path = project_dir / "classes.txt"

    cmd = [
        exe,
        "--filename",           str(images_dir),  # 開啟整個影像目錄
        "--output",             str(labels_dir),  # 標注 JSON 輸出位置
        "--work-dir",           str(work_dir),    # GUI 暫存目錄
        "--nodata",                               # 不在 JSON 內嵌影像資料
        "--autosave",                             # 切換影像時自動儲存
        "--no-auto-update-check",                 # 關閉版本檢查
    ]

    if classes_path.exists():
        cmd += [
            "--labels",        str(classes_path),
            "--validatelabel", "exact",           # 強制只能使用預定義標籤
        ]

    return subprocess.Popen(
        cmd,
        cwd=str(project_dir),
        close_fds=True,
    )
```

### 開啟單一影像（局部修正）

```python
def launch_single_frame(project_dir: Path, frame_idx: int, exe: str) -> subprocess.Popen:
    frame_path = project_dir / "frames" / f"frame_{frame_idx:06d}.jpg"
    output_dir = project_dir / "single_frame_correction"
    output_dir.mkdir(exist_ok=True)

    return subprocess.Popen(
        [exe, "--filename", str(frame_path),
              "--output",   str(output_dir),
              "--autosave",
              "--no-auto-update-check"],
        cwd=str(project_dir),
        close_fds=True,
    )
```

---

## 4. JSON 標注格式

X-AnyLabeling 輸出 **LabelMe v6.0.0** 相容格式：

```json
{
  "version": "6.0.0",
  "imagePath": "../frames/frame_000042.jpg",
  "imageHeight": 1080,
  "imageWidth": 1920,
  "imageData": null,
  "flags": {},
  "shapes": [
    {
      "label": "cat",
      "shape_type": "rectangle",
      "points": [[100.0, 80.0], [250.0, 200.0]],
      "description": "confidence=0.872",
      "flags": {},
      "group_id": null,
      "other_data": {}
    }
  ]
}
```

### 欄位說明

| 欄位 | 說明 |
|---|---|
| `version` | 固定為 `"6.0.0"` |
| `imagePath` | 相對路徑，指向 `frames/frame_XXXXXX.jpg` |
| `imageData` | 固定 `null`（影像不嵌入 JSON） |
| `shapes[].label` | 類別名稱 |
| `shapes[].shape_type` | `"rectangle"` 或 `"polygon"` |
| `shapes[].points` | 矩形：`[[x1,y1],[x2,y2]]`；多邊形：多個頂點 |
| `shapes[].description` | 自訂元資料，例如 `"confidence=0.872"` |

### 座標系統

- 原點 `(0, 0)` 在左上角
- X 向右，Y 向下，單位為像素浮點數
- 矩形用兩個對角點 `[左上, 右下]` 表示

### 手動寫入標注 JSON

```python
import json
from pathlib import Path

def write_annotation(output_dir: Path, frame_idx: int,
                     width: int, height: int,
                     shapes: list[dict]) -> None:
    data = {
        "version": "6.0.0",
        "imagePath": f"../frames/frame_{frame_idx:06d}.jpg",
        "imageHeight": height,
        "imageWidth": width,
        "imageData": None,
        "flags": {},
        "shapes": [
            {
                "label":       s["label"],
                "shape_type":  "rectangle",
                "points":      [[s["x1"], s["y1"]], [s["x2"], s["y2"]]],
                "description": f"confidence={s.get('confidence', 1.0):.3f}",
                "flags":       {},
                "group_id":    None,
                "other_data":  {},
            }
            for s in shapes
        ],
    }
    path = output_dir / f"frame_{frame_idx:06d}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
```

### 讀取與解析標注 JSON

```python
import json
from pathlib import Path

def read_annotation(annotation_path: Path) -> dict:
    """回傳 {shapes, image_path, width, height} 或空 dict。"""
    if not annotation_path.exists():
        return {}
    try:
        return json.loads(annotation_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def parse_confidence(description: str) -> float:
    """從 description 欄位解析信心值，預設為 1.0。"""
    if description and "confidence=" in description:
        try:
            return float(description.split("confidence=")[1].split()[0])
        except (IndexError, ValueError):
            pass
    return 1.0
```

---

## 5. 監控 X-AnyLabeling 結束

X-AnyLabeling 是獨立 GUI 程序，關閉後你的程式才能讀取最終標注。用背景執行緒監控 PID：

```python
import threading
import time
import psutil

def start_pid_monitor(pid: int, on_close: callable, poll_interval: float = 2.0) -> None:
    """當 X-AnyLabeling 關閉時呼叫 on_close()。"""
    def _watch():
        while True:
            time.sleep(poll_interval)
            if not psutil.pid_exists(pid):
                on_close()
                return

    t = threading.Thread(target=_watch, daemon=True)
    t.start()

# 使用方式
proc = launch_xanylabeling(project_dir, exe)
start_pid_monitor(proc.pid, on_close=lambda: import_annotations(project_dir))
```

---

## 6. 批次匯入標注結果

X-AnyLabeling 關閉後，掃描 `annotations/` 目錄取回所有 JSON：

```python
from pathlib import Path
import json

def import_all_annotations(project_dir: Path) -> list[dict]:
    """
    回傳清單，每筆為:
      {frame_idx, label, x1, y1, x2, y2, confidence}
    """
    results = []
    ann_dir = project_dir / "annotations"
    for json_file in sorted(ann_dir.glob("frame_*.json")):
        frame_idx = int(json_file.stem.split("_")[1])
        data = json.loads(json_file.read_text(encoding="utf-8"))
        for shape in data.get("shapes", []):
            pts = shape.get("points", [])
            if len(pts) < 2:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            results.append({
                "frame_idx":  frame_idx,
                "label":      shape.get("label", ""),
                "x1": min(xs), "y1": min(ys),
                "x2": max(xs), "y2": max(ys),
                "confidence": parse_confidence(shape.get("description", "")),
            })
    return results
```

---

## 7. 偵測 X-AnyLabeling 是否已安裝

```python
import subprocess
from pathlib import Path

def detect_xanylabeling(project_root: Path) -> dict:
    """
    回傳 {"available": bool, "executable": str, "version": str, "source": str}
    """
    candidates = [
        (Path(os.environ.get("XANYLABELING_EXE", "")), "XANYLABELING_EXE"),
        (project_root / ".venv-xanylabeling" / "Scripts" / "xanylabeling.exe", "repo .venv"),
    ]
    for exe_path, source in candidates:
        if exe_path and exe_path.exists():
            try:
                r = subprocess.run(
                    [str(exe_path), "version"],
                    capture_output=True, text=True, timeout=10,
                )
                version = r.stdout.strip() or r.stderr.strip()
                return {"available": True, "executable": str(exe_path),
                        "version": version, "source": source}
            except Exception:
                continue

    # 嘗試 PATH
    try:
        r = subprocess.run(
            ["xanylabeling", "version"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return {"available": True, "executable": "xanylabeling",
                    "version": r.stdout.strip(), "source": "PATH"}
    except FileNotFoundError:
        pass

    return {"available": False, "executable": "", "version": "", "source": ""}
```

---

## 8. 完整工作流程總覽

```
你的程式
  │
  ├─ 1. prepare_project()         建立 frames/ + classes.txt + annotations/
  │
  ├─ 2. launch_xanylabeling()     subprocess.Popen → 返回 PID
  │
  ├─ 3. start_pid_monitor()       背景執行緒每 2s 輪詢 PID
  │        │
  │        └─ X-AnyLabeling GUI（使用者標注中）
  │             │
  │             └─ 使用者關閉視窗
  │
  └─ 4. on_close callback()       import_all_annotations() 解析 JSON
                                   → 存入資料庫 / 匯出 COCO / YOLO
```

---

## 9. 快速參考

| 項目 | 值 |
|---|---|
| 套件名稱 | `x-anylabeling-cvhub[cpu]` |
| 驗證版本 | 4.0.0-beta.7 |
| Python 版本 | 3.11.9 |
| 可執行檔 | `Scripts/xanylabeling.exe` |
| JSON 格式 | LabelMe v6.0.0 |
| `imageData` | 永遠為 `null` |
| `imagePath` | 相對路徑 `../frames/frame_XXXXXX.jpg` |
| 信心值位置 | `shapes[].description = "confidence=0.872"` |
| 關閉偵測 | `psutil.pid_exists(pid)` 輪詢 |
| 必要旗標 | `--nodata --autosave --no-auto-update-check` |
| 標籤驗證 | `--labels classes.txt --validatelabel exact` |
