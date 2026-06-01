# Fleet 分發與遠端更新（Tool Distribution）— 設計提案

> 狀態：提案 → 實作中。對應功能 **#1**（讓「在 A 機核准的工具版本」能分發到 N 台邊緣裝置；單機可完整模擬整個 fleet）。
> 本文件同時是實作規格與 as-built 文件；實作完成後請更新「實作現況」。

## 1. 問題

工具 publish 只寫進**本機** `tools.sqlite` 的 `content_json`。沒有任何機制把一個已核准的工具版本推到另外 N 台裝置——每台裝置都是孤島。這讓系統實際上是「單機治理 app」而非「fleet 平台」。

## 2. 核心觀念：在一台機器上模擬 production

**Production 真實度 = 拓撲保真 + 介面保真 + 重現限制**，與是否有高級基礎設施（Oracle 等）無關。

- **拓撲保真**：一個 fleet = N 個**狀態隔離**的 engine 實例，全指向同一個 registry。engine 已支援隔離（`CIM_TOOLS_DB` / `CIM_LOG_DIR`）。N=2~3 跑在同一台電腦即可重現 fleet 行為。
- **介面保真**：切出 `ToolDistributionSource` 邊界。今天用 `LocalFsSource`，未來換 `HttpRegistrySource` 只是改 base URL，不動商業邏輯。
- **重現限制**：分發的是可執行碼，所以**必須簽章 + 載入前驗章**（呼應治理閘門的價值）；離線/低頻寬則用本機 HTTP 服務模擬內網 registry。

> Oracle 之類的企業 RDBMS，免費忠實替身就是 Docker 裡的一個 Postgres——本期 registry-server 後端先用 SQLite，但走 DAL 邊界，日後可換。

## 3. 目標 / 非目標

**目標（本期）**
- `core/distribution/`：`ToolDistributionSource` ABC + `LocalFsSource` + `HttpRegistrySource`。
- `core/distribution/signing.py`：對工具快照（artifact）簽章與驗章（stdlib `hmac`+`hashlib`，共享密鑰 MVP；預留 Ed25519 升級點）。
- `tools/registry_server.py`：最小 FastAPI registry server，可獨立啟動（`/publish`、`/catalog`、`/artifact`）。
- 完整單元測試 + 一支 `start-fleet.bat`（多實例模擬腳本，由 orchestrator 接線）。

**非目標（本期不做）**
- Electron app 殼層的 auto-update（electron-updater）——另列後續（本文 §8 給出做法）。
- 真正的 IdP/SSO（屬認證議題）。
- 把 engine 啟動鏈硬切到 remote source：整合採 **env-gated、預設 LocalFs**，不改變既有單機行為。

## 4. Artifact 模型

一個 artifact = 一個工具版本的可分發單位：

```python
@dataclass(frozen=True)
class ToolArtifact:
    tool_id: str           # e.g. module_042
    version: str           # semver
    channel: str           # "dev" | "prod"
    content: dict          # plugin.yaml + *.py 原始碼快照（同 content_json 格式）
    sha256: str            # canonical-json(content) 的 sha256
    signature: str         # sign(sha256)；驗章用
    created_at: str
    author: str
```

- `content` 沿用既有 `plugin_registry` 的 `content_json` 形狀（檔名 → 原始碼），讓本機 publish 與分發共用同一份快照概念。
- `sha256` 對 `content` 的 **canonical JSON**（`sort_keys=True, ensure_ascii=False, separators` 固定）取雜湊，確保跨機器可重算。

## 5. 元件設計

### 5.1 `core/distribution/signing.py`（純函式、可測、無第三方相依）
```python
def content_sha256(content: dict) -> str: ...           # canonical-json → sha256 hex
def sign(sha256_hex: str, secret: str) -> str: ...       # hmac-sha256(secret, sha256) hex
def verify(sha256_hex: str, signature: str, secret: str) -> bool: ...  # 常數時間比較
def make_artifact(tool_id, version, channel, content, author, secret) -> ToolArtifact: ...
def verify_artifact(artifact: ToolArtifact, secret: str) -> bool:
    """重算 content 的 sha256，比對 artifact.sha256，再驗 signature。任一不符即 False。"""
```
- secret 來自 `CIM_DISTRIBUTION_SECRET` 環境變數（dev 預設一個固定測試值，但需有 log 警告）。
- 文件需註明：HMAC 共享密鑰是 MVP；production 應升級為非對稱簽章（Ed25519，`cryptography` 套件），介面不變。

### 5.2 `core/distribution/sources.py`
```python
class ToolDistributionSource(ABC):
    @abstractmethod
    def list_artifacts(self, channel: str) -> list[ToolArtifactMeta]: ...  # 不含 content，輕量目錄
    @abstractmethod
    def fetch(self, tool_id: str, version: str) -> ToolArtifact: ...        # 取完整 artifact

class LocalFsSource(ToolDistributionSource):
    """讀一個本機資料夾：<root>/<channel>/<tool_id>/<version>.json（artifact JSON）。
       這是今天就能用的 source，也是測試與 start-fleet 模擬的預設。"""

class HttpRegistrySource(ToolDistributionSource):
    """打 registry-server HTTP：GET /catalog?channel=、GET /artifact/{id}/{ver}。
       與 LocalFsSource 同介面 → dev→prod 只換這個類別 + base URL。"""
```
- 兩者 `fetch` 後都應呼叫 `verify_artifact`；驗章失敗丟例外，**拒絕安裝未驗證的碼**。
- `ToolArtifactMeta`：`tool_id/version/channel/sha256/created_at`（目錄用，不含 content）。

### 5.3 `tools/registry_server.py`（最小 FastAPI，可獨立跑）
端點：
- `POST /publish`：收 `ToolArtifact` JSON，驗章後存進 server 端 store（SQLite 或資料夾，走 DAL 邊界），同 (tool_id, version, channel) 覆寫。
- `GET /catalog?channel=prod`：回 `list[ToolArtifactMeta]`。
- `GET /artifact/{tool_id}/{version}`：回完整 `ToolArtifact`。
- `GET /health`：`{"status":"ok"}`（給多實例 / 監控用）。
- 啟動：`python tools/registry_server.py --port 9000 --store <dir>`；只聽 `127.0.0.1`。

## 6. 整合點（由 orchestrator 接線，env-gated，預設不改變現狀）

1. **engine 啟動**：若設 `CIM_DISTRIBUTION_SOURCE`（如 `local:<dir>` 或 `http://127.0.0.1:9000`），在 `SQLiteToolAdapter` 初始化後，從 source 拉 `channel=prod` 的 artifacts → 逐一 `verify_artifact` → 寫進本機 catalog（重用 `plugin_registry` 寫快照路徑）。未設則完全照舊。
2. **`start-fleet.bat`**：起 registry-server → 起 2~3 個帶不同 `--log-dir` 的 engine/Electron 實例（全設 `CIM_DISTRIBUTION_SOURCE=http://127.0.0.1:9000`）→ 在「管理機」publish → 觀察其他實例拉到。
3. 不在本期改動既有 publish 流程；新增「publish 同時推送到 source」可作為後續。

## 7. 測試計畫
- `tests/test_distribution.py`：
  - `content_sha256` 對等內容不同順序鍵 → 相同 hash（canonical 驗證）。
  - `sign`/`verify` 正確；竄改 content 或 signature → `verify_artifact=False`。
  - `LocalFsSource.list_artifacts/fetch` 來回（用 `tmp_path` 寫 artifact JSON）。
  - `fetch` 對被竄改的 artifact 應拋例外（拒裝）。
- `tests/test_registry_server.py`（用 `fastapi.testclient.TestClient`，仿 `tests/test_api.py`）：
  - `/health`、`/publish`（驗章成功/失敗 → 400）、`/catalog`、`/artifact`（404 路徑）。
  - publish 後 `HttpRegistrySource`（指向 TestClient base）能拉回並驗章通過。

## 8. 後續（本期外，先記錄做法）
- **Electron auto-update**：`electron-updater` 的 generic provider 只需「URL + `latest.yml` + 安裝檔」。本機用 `python -m http.server` 指向 `update-feed/` 即可完整跑過「偵測→下載→重啟套用」；上線換成內網檔案伺服器。
- **publish→push**：管理中心 publish 後自動 `POST /publish` 到 registry。
- **裝置註冊 / channel 指派**：registry 記錄 device_id 與訂閱 channel，支援分批 rollout。
- **Postgres 後端**：`docker compose` 起 Postgres 替換 registry-server 的 SQLite store（DAL 邊界已預留）。

## 9. 實作現況（as-built）
- [x] `core/distribution/__init__.py` / `signing.py` / `sources.py`（HMAC 簽章 + LocalFs/Http 兩 source）
- [x] `tools/registry_server.py`（FastAPI，`FileArtifactStore`/`SqliteArtifactStore` 雙 DAL）
- [x] `tests/test_distribution.py` / `tests/test_registry_server.py`（43 passed，store 兩後端各跑一遍）
- [x] engine 啟動 env-gated 接線（[engine.py](../../sidecar/python-engine/engine.py) `pull_distribution_into_catalog`，`main()` 與 `/reload` 皆呼叫；env-gated 預設不改現狀）
- [x] `tools/fleet_publish.py` 發布 CLI（簽章打包 + urllib POST `/publish`）
- [x] `start-fleet.bat` 單機多實例模擬（1 registry + 2 裝置）
- [x] `tests/test_distribution_integration.py`（端到端：拉取→驗章→寫 catalog→讀回；含「竄改 artifact 被拒裝」）
- [x] 實機 HTTP loopback 冒煙通過（uvicorn registry + `fleet_publish` + `HttpRegistrySource` 驗章 fetch）

### 後續（§8 仍未做）
electron auto-update、publish→push 自動化、裝置註冊/分批 rollout、Postgres 後端替換。
