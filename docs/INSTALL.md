# CIM Hybrid Edge Platform — 下載與安裝（Claude Code 可直接照做）

> 本文是**給 AI agent（Claude Code）或工程師照著執行**的乾淨安裝 runbook。
> 平台由**三個 git repo** 組成，labeling 與 AI4BI 以 submodule 掛在 nativeApp 下：
>
> | 角色 | Repo | 掛載位置 |
> |------|------|---------|
> | 平台主體 | `github.com/hctsaik/nativeApp` | — |
> | AI 商業分析 | `github.com/hctsaik/AI4BI` | `sidecar/python-engine/vendor/AI4BI`（submodule）|
> | 影像標註 | `github.com/hctsaik/ANnoTation` | `sidecar/python-engine/plugins/labeling`（submodule）|
>
> **已於 2026-05-31 做過 clean-room 實測**（另地全新 clone + 隔離 venv 安裝）：doctor 全 PASS、
> JS 測試 33 passed、Python 測試 715 passed（細節見文末「實測結果」）。

## 0. 前置需求

- **Git**、**Node.js（LTS）**
- **Python 3.11**（必須與 engine host 直譯器一致；目前 dev 預設 `pythoncore-3.11-64`）
- 對三個 repo 的存取權（私有 repo 需登入 / token）

## 1. 下載（一次取得三個 repo）

labeling submodule 的接線目前在 **`feat/platform-restructure`** 分支（尚未併入 `main`），
clone 時要指定該分支並**遞迴拉 submodule**（這一步就把 AI4BI 與 labeling 一起帶下來）：

```bash
git clone --branch feat/platform-restructure --recurse-submodules \
  https://github.com/hctsaik/nativeApp.git nativeApp
cd nativeApp
```

> 已經 clone 但沒帶 submodule？補跑：`git submodule update --init --recursive`
> 確認：`git submodule status` 應列出 `plugins/labeling`（ANnoTation）與 `vendor/AI4BI` 兩筆。

## 2. 安裝 Node 相依

```bash
npm install
```

## 3. 安裝 Python 相依

**務必裝進 engine 實際使用的那一支 Python 3.11**（見 §5 的對齊說明）。以下 `PY` 換成該 python.exe。
clean-room 測試用隔離 venv（`python -m venv` 後用 venv 的 python），正式機器可直接用系統 3.11。

```powershell
# (a) 平台核心
& $PY -m pip install -r sidecar/python-engine/requirements.txt
# (b) AI4BI（editable，submodule 原始碼即時生效）
& $PY -m pip install -e "sidecar/python-engine/vendor/AI4BI[llm]"
# (c) 影像標註專屬相依（AI 預標 torch/transformers 等；部分與 (a) 重疊，pip 會自動略過）
& $PY -m pip install -r sidecar/python-engine/plugins/labeling/requirements-labeling.txt
```

## 4. 驗證安裝（必跑）

```powershell
# 若用 venv，先讓 doctor 檢查那一支：$env:PYTHON = "<venv>\Scripts\python.exe"
powershell -ExecutionPolicy Bypass -File scripts\win\verify-setup.ps1
```

預期看到 **`[OK] 全部通過`**，且 Labeling 與 AI4BI 區段皆 `[PASS]`。doctor 會解析 `start-dev.bat`
實際使用的 python，並在**那一支**裡逐項檢查：git/node/npm、Python 3.11、兩個 submodule、
`node_modules`、engine 相依、AI4BI 進入點 `ai4bi.ui.app`、labeling 平台契約檔與 annotation 相依。

## 5. ⚠️ 最關鍵：對齊 engine 的 Python

dev 模式下 engine 由 `start-dev.bat` 的 `set PYTHON=...` 那行啟動（傳給 Electron，見
`apps/host-electron/src/main.js` 的 `process.env.PYTHON`）。**該行硬編了特定使用者路徑** ——
新機器務必改成本機 3.11 的 `python.exe` 絕對路徑，且 §3 要裝進**同一支**，否則 engine 啟動或
`import ai4bi` 會失敗。

## 6. 啟動

```powershell
start-dev.bat
```

## 7. 日後更新（與 AI4BI / labeling 各自獨立）

```bash
# 更新 AI4BI 或 影像標註：進對應 submodule git pull，平台端不需改動
cd sidecar/python-engine/vendor/AI4BI && git pull
cd sidecar/python-engine/plugins/labeling && git pull
# 回主 repo 釘新的 submodule 指標（要重現 release 時）
```

## 8. 注意事項（agent 必讀）

- **MCP 設定是機器本地、不進版控**：`.mcp.json` 與 `.claude/mcp.json` 被 gitignore，全新 clone**不會有**。
  因此 `tests/test_mcp_config.py` 的 2 個測試在 fresh clone 會 FileNotFoundError —— **這是預期、非整合問題**。
  需要 MCP（GUI 測試工具）時再各自設定；不影響 app 本身執行。
- **測試相依不在 runtime requirements**：要跑 `npm run test:python` 需另裝 `pip install pytest respx`。
- **分支**：待 `feat/platform-restructure` 併入 `main` 後，§1 可改 clone `main`（屆時更新本文）。
- **打包 release**（PyInstaller `engine.exe`）需把 AI4BI 套件納入打包；見 `docs/AI4BI_INTEGRATION.md`。

## 9. 實測結果（2026-05-31 clean-room）

在 `C:\code\claude\cleanroom` 另地全新 clone（branch + `--recurse-submodules`）、建獨立 venv（Python 3.11.9）安裝：

| 檢查 | 結果 |
|------|------|
| 遞迴 clone（submodule 解析） | ✅ labeling `4d0469c`、AI4BI `0cc6f83` 皆 checkout |
| `npm install` | ✅ 458 packages |
| pip：core + AI4BI[llm] + labeling | ✅ 全裝成功（torch/transformers/ai4bi/duckdb/streamlit-image-annotation…）|
| `verify-setup.ps1` doctor | ✅ `[OK] 全部通過`（含 Labeling + AI4BI 區段全 PASS）|
| `npm test`（JS） | ✅ 17 + 16 passed |
| `pytest`（Python，補裝 pytest+respx 後） | ✅ 715 passed、1 xpassed；2 個 MCP-config 測試因本機設定檔不存在而 fail（預期，見 §8）|

**結論：三個 repo 能乾淨 clone、安裝並整合運作。**
