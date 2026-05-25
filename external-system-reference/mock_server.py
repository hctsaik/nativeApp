"""
外部系統 Mock Server — 模擬 AOI 機台 / MES 的 REST API

啟動方式：
    uvicorn mock_server:app --port 9000 --reload

此伺服器實作 CIM 平台對接所需的兩支 API：
    GET  /getAntList         — 回傳任務摘要列表
    POST /getAntTaskDetail   — 回傳特定任務的 ZIP 下載連結
    GET  /files/{filename}   — 提供 ZIP 靜態下載

驗證方式：
    所有 API 需帶 Header: Authorization: Bearer test-token-123
    驗證失敗回傳 HTTP 401。
"""

import io
import json
import zipfile
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ─── 應用程式初始化 ───────────────────────────────────────────────────────────

app = FastAPI(
    title="外部系統 Mock Server（AOI / MES）",
    description="模擬外部系統 API，供 CIM 平台標注對接開發與測試使用",
    version="1.0.0",
)

# ─── 設定 ────────────────────────────────────────────────────────────────────

VALID_API_TOKEN = "test-token-123"

# ─── 任務 Fixture 資料（記憶體內維護）────────────────────────────────────────
# antActive 狀態：
#   0 = 待標注（CIM 平台會主動拉取）
#   1 = 標注中
#   2 = 已完成

FIXTURE_TASKS = [
    {
        "antID": "TASK_001",
        "antActive": 0,
        "antPeriod": "2026-05-26T08:00:00Z",
        "external_context": {"lot_id": "L001", "eqp_id": "AOI-01", "product": "PANEL-A"},
    },
    {
        "antID": "TASK_002",
        "antActive": 0,
        "antPeriod": "2026-05-26T09:00:00Z",
        "external_context": {"lot_id": "L001", "eqp_id": "AOI-02", "product": "PANEL-B"},
    },
    {
        "antID": "TASK_003",
        "antActive": 1,
        "antPeriod": "2026-05-25T14:00:00Z",
        "external_context": {"lot_id": "L002", "eqp_id": "AOI-01", "product": "PANEL-C"},
    },
    {
        "antID": "TASK_004",
        "antActive": 1,
        "antPeriod": "2026-05-25T10:00:00Z",
        "external_context": {"lot_id": "L002", "eqp_id": "AOI-03", "product": "PANEL-D"},
    },
    {
        "antID": "TASK_005",
        "antActive": 2,
        "antPeriod": "2026-05-24T16:00:00Z",
        "external_context": {"lot_id": "L003", "eqp_id": "AOI-02", "product": "PANEL-E"},
    },
]

# ─── 驗證輔助函式 ─────────────────────────────────────────────────────────────


def _verify_token(authorization: Optional[str]) -> None:
    """
    驗證 Bearer Token。
    Authorization header 格式：Bearer <token>
    驗證失敗拋出 HTTP 401。
    """
    if authorization is None:
        raise HTTPException(status_code=401, detail="缺少 Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization header 格式錯誤，應為 Bearer <token>")
    if parts[1] != VALID_API_TOKEN:
        raise HTTPException(status_code=401, detail="API Token 無效")


# ─── Request / Response Models ───────────────────────────────────────────────


class TaskDetailRequest(BaseModel):
    antID: str
    format: str = "coco"  # 支援 "coco" 或 "yolo"


# ─── Endpoints ───────────────────────────────────────────────────────────────


@app.get("/getAntList", summary="回傳任務摘要列表")
def get_ant_list(authorization: Optional[str] = Header(default=None)):
    """
    回傳外部系統中所有任務的摘要列表。
    CIM 平台會定期呼叫此 API，拉取 antActive=0 的任務進行標注。

    回傳格式（JSON Array）：
    [
      {
        "antID": "TASK_001",
        "antActive": 0,          # 0=待標注, 1=標注中, 2=已完成
        "antPeriod": "2026-05-26T08:00:00Z",
        "external_context": {...}  # 機台自定義欄位，平台原樣儲存
      },
      ...
    ]
    """
    _verify_token(authorization)
    return FIXTURE_TASKS


@app.post("/getAntTaskDetail", summary="回傳任務 ZIP 下載連結")
def get_ant_task_detail(
    body: TaskDetailRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    回傳指定任務的資料包下載連結。
    CIM 平台在建立標注任務前會呼叫此 API，取得 ZIP 包的 URL 後下載影像與初始標注。

    Request body：
        { "antID": "TASK_001", "format": "coco" }

    Response：
        { "download_url": "http://localhost:9000/files/TASK_001.zip" }
    """
    _verify_token(authorization)

    # 確認任務存在
    task = next((t for t in FIXTURE_TASKS if t["antID"] == body.antID), None)
    if task is None:
        raise HTTPException(status_code=404, detail=f"找不到任務 {body.antID}")

    download_url = f"http://localhost:9000/files/{body.antID}.zip"
    return {"download_url": download_url}


@app.get("/files/{task_id}.zip", summary="下載任務 ZIP 資料包")
def download_task_zip(task_id: str, authorization: Optional[str] = Header(default=None)):
    """
    動態產生並提供任務 ZIP 下載。
    ZIP 內包含：
      - images/sample.png   （程式動態產生的測試灰階圖）
      - annotations.json    （COCO 格式標注，含一個示範 bounding box）

    實際外部系統應提供真實影像與標注資料。
    """
    _verify_token(authorization)

    # 確認任務存在
    task = next((t for t in FIXTURE_TASKS if t["antID"] == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail=f"找不到任務 {task_id}")

    zip_bytes = _build_demo_zip(task_id, task)

    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={task_id}.zip"},
    )


# ─── ZIP 動態建立輔助函式 ─────────────────────────────────────────────────────


def _build_demo_zip(task_id: str, task: dict) -> bytes:
    """
    在記憶體中動態建立示範 ZIP，不依賴外部圖片檔。

    ZIP 結構：
      images/
        sample_01.png   — 64×64 灰階漸層測試圖
        sample_02.png   — 64×64 紅色方塊測試圖
      annotations.json  — COCO 格式，含兩個示範 bounding box
    """
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 產生測試圖一（灰階漸層）
        img1_bytes = _make_gradient_png(64, 64)
        zf.writestr("images/sample_01.png", img1_bytes)

        # 產生測試圖二（紅色方塊）
        img2_bytes = _make_solid_color_png(64, 64, color=(200, 50, 50))
        zf.writestr("images/sample_02.png", img2_bytes)

        # 產生 COCO 格式標注
        coco = {
            "info": {
                "description": f"CIM 對接示範資料 — {task_id}",
                "version": "1.0",
                "external_context": task.get("external_context", {}),
            },
            "images": [
                {"id": 1, "file_name": "sample_01.png", "width": 64, "height": 64},
                {"id": 2, "file_name": "sample_02.png", "width": 64, "height": 64},
            ],
            "categories": [
                {"id": 1, "name": "defect", "supercategory": "anomaly"},
                {"id": 2, "name": "scratch", "supercategory": "anomaly"},
            ],
            "annotations": [
                {
                    "id": 1,
                    "image_id": 1,
                    "category_id": 1,
                    "bbox": [10, 10, 20, 20],  # [x, y, width, height]
                    "area": 400,
                    "iscrowd": 0,
                },
                {
                    "id": 2,
                    "image_id": 2,
                    "category_id": 2,
                    "bbox": [5, 15, 30, 15],
                    "area": 450,
                    "iscrowd": 0,
                },
            ],
        }
        zf.writestr("annotations.json", json.dumps(coco, ensure_ascii=False, indent=2))

    return buf.getvalue()


def _make_gradient_png(width: int, height: int) -> bytes:
    """
    在記憶體中產生灰階漸層 PNG，不需要外部圖片檔。
    使用 Pillow 產生，若 Pillow 未安裝則 fallback 至最小合法 PNG。
    """
    try:
        from PIL import Image

        img = Image.new("L", (width, height))
        pixels = img.load()
        for y in range(height):
            for x in range(width):
                pixels[x, y] = int((x / width) * 255)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        return _minimal_png()


def _make_solid_color_png(width: int, height: int, color: tuple = (128, 128, 128)) -> bytes:
    """
    在記憶體中產生純色 PNG。
    """
    try:
        from PIL import Image

        img = Image.new("RGB", (width, height), color=color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        return _minimal_png()


def _minimal_png() -> bytes:
    """
    最小合法 1×1 灰色 PNG（Pillow 未安裝時的 fallback）。
    """
    import base64

    # 預先產生的 1×1 灰色 PNG base64
    b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVQI12NgAAAAAgAB4iG8MwAAAABJRU5ErkJggg=="
    )
    return base64.b64decode(b64)
