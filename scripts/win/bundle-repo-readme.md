# nativeApp_BundleZip — 下載即安裝

這個 repo 就是 **nativeApp + AI4BI + LV + Labeling 的完整、已拼好的原始碼**。
**不需要 git、不需要 submodule、不需要任何指令拼裝** —— 全部都在這裡了,不會漏。

## 怎麼裝(只要三件事)

1. 在這個網頁按綠色 **`< > Code` → `Download ZIP`**。
2. 解壓,進到裡面的 **`nativeApp\`** 資料夾。
3. 打開 **`nativeApp\00-READ-ME-FIRST.md`**,把裡面那幾行貼進 PowerShell 跑完即可:
   ```powershell
   $env:PYTHONUTF8 = "1"
   npm install
   py -3.11 -m pip install -r sidecar\python-engine\requirements.txt
   py -3.11 -m pip install -e "sidecar\python-engine\vendor\AI4BI[llm]"
   py -3.11 -m pip install -r sidecar\python-engine\plugins\labeling\requirements-labeling.txt
   powershell -ExecutionPolicy Bypass -File scripts\win\verify-setup.ps1
   start-dev.bat
   ```

> 前置只要 **Node.js** 與 **Python 3.11**(`py -3.11 --version` 看得到 3.11.x)。

## 內容

- `nativeApp\` — 完整、可直接安裝的平台原始碼(AI4BI / LV / Labeling 都已實體放進
  `vendor\AI4BI`、`vendor\LV`、`plugins\labeling`)。
- `VERSION.txt` — 這份對應的 nativeApp 來源 commit 與打包時間。

## 注意

- 這是**原始碼**,仍需 Node.js + Python 3.11;不是免安裝執行檔。
- 模型權重與 torch 等重相依**刻意沒放**(太大),會在首次啟動對應工具時自動安裝/下載。
- 要更新就回來重新 Download ZIP(這份內容沒有 git,不能 `git pull`)。
