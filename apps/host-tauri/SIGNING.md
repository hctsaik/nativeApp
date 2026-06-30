# Windows Code Signing(Tauri)— 從 dev 到 production

> 這是把 Electron 換成 Tauri **唯一真正的遷移功課**:Tauri 產出的是「你自己的原生 exe/安裝包」,
> 在啟用 **WDAC 企業政策 / Smart App Control** 的機器上,未簽章原生碼會被擋(本機實測:
> `cargo build` 的 build-script 被 CI 政策 `{0283ac0f}` 封鎖、CI 事件 3077)。
> Electron 靠廠商**已簽章**的 `electron.exe` runtime 繞過;Tauri 必須自己簽。

## 現況(dev / demo,已設好)
- `tauri.conf.json` → `bundle.windows`:
  - `digestAlgorithm: sha256`、`timestampUrl: http://timestamp.digicert.com`
  - `certificateThumbprint: 9A91F8C5D5E93B2828773F57DDF6D0EBDE18A82E`(**自簽 dev 憑證**,在 `Cert:\CurrentUser\My`)
- `tauri build` 會自動用該 thumbprint 經 `signtool` 簽 NSIS 安裝包。
- 已驗證 `signtool sign /fd SHA256` 能成功簽 `cim-light.exe`(`Get-AuthenticodeSignature` → SignerCert 正確、sha256RSA)。
- 自簽憑證的 `Status=UnknownError` 只因「根未受信任」;這正是與真憑證的唯一差別。

### 重建 dev 憑證(若換機 / 過期)
```powershell
$c = New-SelfSignedCertificate -Type CodeSigningCert `
  -Subject "CN=CIM Hybrid Edge Platform (Dev Self-Signed)" `
  -CertStoreLocation Cert:\CurrentUser\My -KeyExportPolicy Exportable -NotAfter (Get-Date).AddYears(3)
$c.Thumbprint   # ← 貼回 tauri.conf.json bundle.windows.certificateThumbprint
```

## Production:三選一憑證
1. **OV(Organization Validation)code-signing 憑證**:DigiCert / Sectigo 等 CA 簽發。能讓檔案「有簽章、可驗證簽署者」,但 SmartScreen 信譽要時間累積。
2. **EV(Extended Validation)憑證(建議)**:憑證放硬體 token / HSM(或雲端如 Azure Trusted Signing)。**SmartScreen/SAC 即時信譽**,最少摩擦。Tauri 用 `signCommand` 走簽署服務(見下)。
3. **企業內部 CA**:若部署環境的 **WDAC 企業政策只信任特定簽署者**,則簽章憑證(或其 CA)必須被加入該 WDAC 政策的允許 signer 規則 —— **這步要找管理該政策的 IT/MDM 配合**,光有「合法簽章」不一定夠(政策可能要求「企業簽章層級」)。這是組織級成本,不是技術問題。

## Production 設定法
### A. 憑證在本機 cert store(OV / token)
把 `certificateThumbprint` 換成真憑證的 thumbprint;`tauri build` 即自動簽。

### B. 雲端 / HSM 簽署服務(EV、CI 友善,推薦)
改用 `signCommand`(Tauri 2.4+)把簽署委派給外部工具(如 Azure Trusted Signing 的 `dotnet sign`、或 `AzureSignTool`):
```json
"bundle": {
  "windows": {
    "signCommand": "AzureSignTool sign -kvu <vault> -kvc <cert> -kvt <tenant> -kvi <appid> -kvs <secret> -tr http://timestamp.digicert.com -td sha256 -fd sha256 %1"
  }
}
```
`%1` 由 Tauri 帶入待簽檔路徑。憑證機密走 CI secret/env,不進版控。

## 驗證
```powershell
$st = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe"
& $st verify /pa /v <安裝包或exe>      # 真憑證 → 通過;自簽(根未信任)→ 失敗屬正常
Get-AuthenticodeSignature <檔> | Format-List Status, SignerCertificate, TimeStamperCertificate
# Status=Valid 代表簽章 + 信任鏈 + 時間戳都成立
```

## 與 WDAC 的關係(本機特例)
本機是個人電腦,使用者已**關閉 Smart App Control**,故本機 dev 跑未簽章即可。
但要**分發到其他啟用 WDAC/SAC 的機器**時,上述簽章(尤其 EV + 政策 allow-list)才是必要條件。
打包成可攜安裝包(含 engine、python runtime 等 resource)屬後續 milestone(見 ROADMAP「未排程」)。
