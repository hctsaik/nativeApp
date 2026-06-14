# language: en
# LV (VisualLatent) — launch, shell & guard states.
# Driven through the cim-gui MCP machinery (sidecar start + Playwright on the live
# Streamlit page). Every Tier-A scenario needs no model weights and no dataset.
Feature: LV launches into the Native App and degrades gracefully
  As a curator opening VisualLatent from the CIM Native App
  I want the tool to launch, show its five-tool workspace, and guide me when inputs are missing
  So that I can trust the shell before doing any heavy analysis

  @tierA @S01 @smoke
  Scenario: LV registers as an app tool and serves its own Streamlit shell
    Given the engine has scanned plugins/lv/modules/app-lv/plugin.yaml on boot
    When I POST /tools/app-lv/start
    Then the response is 200 with a single Streamlit URL and category "app"
    And the URL serves /_stcore/health == "ok"
    And the page heading "Dataset Analysis Tools" is visible
    And the tool selector exposes "Visualize Embeddings", "Compare Distributions", "完整度熱力圖", "組考卷", "灰帶覆核"
    And no Python traceback is present on first paint

  @tierA @S02
  Scenario: Feature-map popover documents the five-tool relationship and the data contract
    Given LV is open on "Visualize Embeddings"
    When I open the "✨ 功能地圖" popover
    Then it explains the relationship of the five tools (先探索、再行動)
    And it names the handoff artifact "manifest.jsonl"
    And no traceback appears after opening it

  @tierA @S03
  Scenario: Running with no folder shows a clear guard and keeps the onboarding card
    Given LV is open on "Visualize Embeddings" with no folder entered
    When the analysis would run without any folder
    Then the app shows the guard "請先選擇至少一個資料夾"
    And the quick-start onboarding (① 資料 / ② 模型) remains visible
    And no traceback is raised

  @tierA @S04
  Scenario: Missing-model and bad-path are reported as distinct, non-crashing states
    Given the model-house has no usable .pth weights
    Then the sidebar shows "models/ 內找不到模型檔"
    When I paste a non-existent folder path and attempt to run
    Then a path/empty guard message is shown rather than a Python traceback
    And the missing-model and missing-folder conditions are distinguishable

  @tierA @S05
  Scenario: Navigating across all five LV tools preserves shell integrity
    Given LV is open on "Visualize Embeddings"
    When I switch the selector to "Compare Distributions", "完整度熱力圖", "組考卷" and "灰帶覆核" in turn
    Then each tool renders its own body without a traceback
    And switching back to "Visualize Embeddings" restores its workspace
