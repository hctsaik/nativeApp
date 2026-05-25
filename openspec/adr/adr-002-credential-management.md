# ADR-002: Credential Management

## Status
Accepted

## Date
2026-05-26

## Context
CIM 需要儲存外部系統（Oracle DB、REST API、雲端儲存）的連線憑證（帳密、API key、connection string）。
需要決定憑證的加密方式與儲存位置：

1. **明文存 profile YAML**：最簡單但不安全。
2. **OS Keychain（keyring）**：最安全，但在 headless / CI 環境無法使用。
3. **本地 AES 加密 DB**：master key 存 OS keychain，ciphertext 存獨立 SQLite，可在 keyring 不可用時 fallback 到環境變數。

## Decision
採用 **Local CredentialStore**：

- 加密演算法：**AES-256-GCM**（提供認證加密，防止 ciphertext 竄改）。
- **Master key 儲存策略**（優先序）：
  1. OS keychain（透過 `keyring` library）
  2. 環境變數 `CIM_CREDENTIAL_MASTER_KEY`（Base64 encoded 32 bytes）
  3. Phase 4 fallback：若兩者皆不可用，拋出 `CredentialStoreError`（不 silently 使用 hardcoded key）
- **Ciphertext 儲存**：獨立的 `credentials.db`（SQLite），與 annotation 主資料庫分離，避免備份時一起外洩。
- `credential_ref` 欄位存在 `IntegrationProfile` 中，指向 `credentials.db` 的 row key。

Phase 4 先用環境變數 fallback，不強制依賴 keyring（CI 環境友善）。

## Consequences
- **優點**：憑證不以明文出現在 profile YAML 或 git repo。
- **優點**：AES-GCM 防止 ciphertext 在未持有 master key 的情況下被解密或偽造。
- **優點**：`credentials.db` 獨立，可設定不同備份策略（排除於一般備份之外）。
- **缺點**：需要管理 master key 的生命週期（輪換、遺失即資料無法解密）。
- **缺點**：`keyring` 在 Linux headless 環境需 `dbus` 或 `secret-service`，增加部署複雜度。
- Phase 4 的環境變數 fallback 在共用機器上仍有環境變數洩漏風險，生產環境應強制 keychain。
