# 變更：X-AnyLabeling 動物影像 MCP 整合

## 為何需要此變更

動物影像系統需要一個穩定、可審計、可由 AI Agent 呼叫的標註整合層，協調資料集、標籤規範、X-AnyLabeling 人工修正、AI 預標註、品質檢查與訓練資料匯出。

X-AnyLabeling 適合作為標註前台與 AI-assisted labeling 工具，但不應讓 MCP 直接依賴 GUI 點擊、視窗座標或螢幕截圖作為業務流程核心。MCP 應暴露穩定的 domain workflow API，並透過 adapter 與 X-AnyLabeling 的專案檔、標註格式、CLI/啟動流程互通。

## 變更目標

建立 `animal-labeling-mcp` 規劃，作為動物影像系統與 X-AnyLabeling 之間的整合層：

1. 管理動物影像資料集、影像 metadata 與 label schema。
2. 建立標註任務與審核流程。
3. 匯入/匯出 X-AnyLabeling 相容標註格式。
4. 支援 LabelMe 作為人工編輯格式、COCO 作為治理格式、YOLO 作為訓練輸出格式。
5. 透過 job-based API 觸發 AI 預標註，並保留 model/version/confidence/source。
6. 提供品質檢查、資料集統計與 review queue。
7. 避免將 X-AnyLabeling 私有格式滲入核心 domain model。

## MVP 範圍

**納入：**

- Animal labeling domain model：Dataset、ImageAsset、LabelSchema、AnnotationSet、Annotation、Geometry、LabelingJob。
- Local catalog 與 artifact layout 規劃。
- X-AnyLabeling adapter contract：project 建立、annotation import/export、啟動標註前台。
- MCP tools/resources API design。
- 標註狀態機、job 狀態機、錯誤格式與驗收準則。
- Annotation validation：label schema、geometry bounds、empty annotation、version conflict。
- Export：LabelMe / COCO / YOLO detection / YOLO segmentation。

**不納入 MVP：**

- GUI 點擊或座標式遙控 X-AnyLabeling。
- 即時多人協作。
- 完整模型訓練平台。
- keypoint 姿態標註的完整 schema 與訓練閉環。
- 大型資料湖治理與雲端同步。
- OAuth/SSO 等企業級權限。

## 長期方向

- Active learning queue：低信心、高分歧樣本自動送人工修正。
- 模型版本註冊、訓練資料版本化、model-to-human 差異分析。
- Animal keypoint schema，例如 `canine_pose_v1`、`bovine_pose_v1`。
- 追蹤 ID 與行為事件。
- 多標註員一致性分析。
- Dataset lineage、export approval、跨場域資料偏差報告。

## 設計原則

1. MCP tools 呼叫 application service，不直接操作 GUI 或底層檔案。
2. X-AnyLabeling 是 adapter，不是 domain model。
3. 修改型操作需具備 version / request id，避免覆寫人工標註。
4. 大型影像以 URI/resource 引用，不塞進 tool result。
5. 所有 artifacts 記錄 schema version、adapter version、X-AnyLabeling version。
6. 匯出 YOLO 時不可遺失 canonical annotation set；YOLO 僅為訓練 artifact。

