"""
示範外部系統如何下載 CIM 平台完工的標注結果。

注意：此腳本呼叫的是 CIM 平台的 API，不是外部系統自己的 API。
平台 API 規格尚在開發中，此為 reference 示意；實際 endpoint 路徑
待平台正式釋出後以官方文件為準。

使用方式：
    python downloader_client.py

流程：
  1. 向平台查詢哪些任務已完成（antActive=2）
  2. 下載對應的結果 ZIP
  3. 解壓並讀取標注 JSON
"""

import io
import json
import zipfile
from pathlib import Path

import httpx

# ─── 設定 ────────────────────────────────────────────────────────────────────

# CIM 平台地址（待確認正式 URL）
CIM_PLATFORM_URL = "http://localhost:8000"

# 由平台管理員核發的 API Token（Phase 0：每個 tenant 一組）
API_TOKEN = "your-tenant-api-token"

# 租戶識別碼（由平台管理員提供）
TENANT_ID = "your-tenant-id"

# ─── 平台 API 函式 ────────────────────────────────────────────────────────────


def list_completed_tasks(tenant_id: str) -> list[dict]:
    """
    向 CIM 平台查詢指定 tenant 下已完成標注的任務。

    API（規格草案，待正式文件確認）：
        GET {CIM_PLATFORM_URL}/api/v1/tasks?tenant_id={tenant_id}&antActive=2

    Returns:
        已完成任務的摘要列表，每筆格式：
        {
            "task_id":    "TASK_001",
            "antID":      "TASK_001",        # 外部系統原始 ID
            "antActive":  2,
            "completed_at": "2026-05-26T12:00:00Z",
            "external_context": {...}
        }
    """
    url = f"{CIM_PLATFORM_URL}/api/v1/tasks"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    params = {"tenant_id": tenant_id, "antActive": 2}

    print(f"[CIM] 查詢已完成任務：GET {url}")
    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=10.0)
        resp.raise_for_status()
        tasks = resp.json()
        print(f"[CIM] 找到 {len(tasks)} 筆已完成任務")
        return tasks
    except httpx.ConnectError:
        print(f"[警告] 無法連線至 CIM 平台（{CIM_PLATFORM_URL}）")
        print("       這是預期行為——平台 API 尚在開發中。")
        print("       以下改用 Mock 資料示範解析流程。\n")
        # 回傳模擬已完成任務（供示範用）
        return [
            {
                "task_id": "TASK_005",
                "antID": "TASK_005",
                "antActive": 2,
                "completed_at": "2026-05-26T12:00:00Z",
                "external_context": {"lot_id": "L003", "eqp_id": "AOI-02", "product": "PANEL-E"},
            }
        ]
    except httpx.HTTPStatusError as e:
        print(f"[錯誤] 平台回傳 HTTP {e.response.status_code}：{e.response.text}")
        return []


def download_result_zip(task_id: str, output_dir: Path) -> Path:
    """
    從 CIM 平台下載指定任務的標注結果 ZIP。

    API（規格草案，待正式文件確認）：
        GET {CIM_PLATFORM_URL}/api/v1/tasks/{task_id}/export

    Args:
        task_id:    CIM 平台任務 ID（即 antID）
        output_dir: 儲存 ZIP 的目錄

    Returns:
        下載後的 ZIP 檔案路徑
    """
    url = f"{CIM_PLATFORM_URL}/api/v1/tasks/{task_id}/export"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{task_id}_result.zip"

    print(f"[CIM] 下載結果 ZIP：GET {url}")
    try:
        with httpx.stream("GET", url, headers=headers, timeout=30.0) as resp:
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        print(f"[CIM] 已下載：{zip_path}（{zip_path.stat().st_size:,} bytes）")
        return zip_path
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        print(f"[警告] 無法下載結果 ZIP（{e}）")
        print("       改用 mock_server 的示範 ZIP 繼續示範解析流程。\n")
        # Fallback：從 mock_server 下載示範 ZIP
        return _download_from_mock_server(task_id, output_dir)


def _download_from_mock_server(task_id: str, output_dir: Path) -> Path:
    """
    從 mock_server（localhost:9000）下載示範 ZIP，供平台 API 不可用時的 fallback。
    """
    mock_url = f"http://localhost:9000/files/{task_id}.zip"
    mock_headers = {"Authorization": "Bearer test-token-123"}
    zip_path = output_dir / f"{task_id}_result.zip"

    try:
        with httpx.stream("GET", mock_url, headers=mock_headers, timeout=10.0) as resp:
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        print(f"[Mock] 已從 mock_server 下載：{zip_path}")
        return zip_path
    except Exception as e:
        print(f"[警告] mock_server 也無法連線（{e}）")
        print("       請先啟動 mock_server：uvicorn mock_server:app --port 9000")
        raise


def parse_result_zip(zip_path: Path, target_format: str = "coco") -> dict:
    """
    解壓結果 ZIP 並讀取標注資料。

    Args:
        zip_path:       ZIP 檔案路徑
        target_format:  "coco" 或 "yolo"

    Returns:
        COCO 格式：annotations.json 的內容（dict）
        YOLO 格式：{"classes": [...], "labels": {"img_001.txt": "0 0.5 0.5..."}}
    """
    if not zip_path.exists():
        raise FileNotFoundError(f"找不到 ZIP 檔案：{zip_path}")

    print(f"\n[解析] 開啟 ZIP：{zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        print(f"[解析] ZIP 內容（{len(names)} 個檔案）：")
        for name in names:
            print(f"       {name}")

        if target_format == "coco":
            # 讀取 COCO 標注
            if "annotations.json" not in names:
                raise ValueError("ZIP 中找不到 annotations.json")
            with zf.open("annotations.json") as f:
                coco = json.loads(f.read().decode("utf-8"))
            print(f"\n[COCO] 類別數：{len(coco.get('categories', []))}")
            print(f"[COCO] 圖片數：{len(coco.get('images', []))}")
            print(f"[COCO] 標注數：{len(coco.get('annotations', []))}")
            return coco

        elif target_format == "yolo":
            # 讀取 YOLO 標注
            result: dict = {"classes": [], "labels": {}}
            if "classes.txt" in names:
                with zf.open("classes.txt") as f:
                    result["classes"] = f.read().decode("utf-8").strip().splitlines()
            label_files = [n for n in names if n.startswith("labels/") and n.endswith(".txt")]
            for label_file in label_files:
                with zf.open(label_file) as f:
                    content = f.read().decode("utf-8").strip()
                    result["labels"][Path(label_file).name] = content
            print(f"\n[YOLO] 類別：{result['classes']}")
            print(f"[YOLO] 標注檔數：{len(result['labels'])}")
            return result

        else:
            raise ValueError(f"不支援的格式：{target_format}（支援 coco / yolo）")


# ─── 主程式（示範完整下載流程）──────────────────────────────────────────────


def main():
    print("=" * 60)
    print("CIM 平台結果下載示範")
    print("=" * 60)
    print()

    output_dir = Path(__file__).parent / "tmp" / "downloads"

    # 步驟 1：查詢已完成任務
    print("步驟 1：查詢已完成任務")
    print("-" * 40)
    completed_tasks = list_completed_tasks(TENANT_ID)
    if not completed_tasks:
        print("目前沒有已完成的任務。")
        return
    print()

    # 步驟 2：下載第一個已完成任務的結果 ZIP
    task = completed_tasks[0]
    task_id = task["antID"]
    print(f"步驟 2：下載任務 {task_id} 的結果 ZIP")
    print("-" * 40)
    zip_path = download_result_zip(task_id, output_dir)
    print()

    # 步驟 3：解析標注結果
    print("步驟 3：解析標注結果")
    print("-" * 40)
    result = parse_result_zip(zip_path, target_format="coco")

    # 步驟 4：根據 external_context 寫回外部系統
    print("\n步驟 4：根據 external_context 寫回外部系統")
    print("-" * 40)
    ctx = task.get("external_context", {})
    print(f"  任務 ID:     {task_id}")
    print(f"  lot_id:      {ctx.get('lot_id', 'N/A')}")
    print(f"  eqp_id:      {ctx.get('eqp_id', 'N/A')}")
    print(f"  product:     {ctx.get('product', 'N/A')}")
    annotations = result.get("annotations", [])
    print(f"  標注總數:    {len(annotations)}")
    if annotations:
        defect_count = sum(1 for a in annotations if a.get("category_id") == 1)
        print(f"  缺陷數:      {defect_count}")

    print("\n[完成] 結果已下載並解析，可寫回 MES/資料庫。")


if __name__ == "__main__":
    main()
