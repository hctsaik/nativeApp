# language: en
# The cross-tool journey in the CIM Native App: a curator uses LV to pick a
# subset, then hands it to the labeling plugin (module_026 資料來源 → 012 標注 →
# 018 審查 → 013 Sync Back). The boundary is the manifest.jsonl + cart CSV.
Feature: LV hands a curated subset to the labeling plugin inside the Native App
  As a labeling-operations lead
  I want LV and the labeling tools to run together and exchange a sha256-keyed subset
  So that annotators only see the images the curator selected, with full lineage

  @tierA @S16 @smoke
  Scenario: LV and a labeling module run live in one engine session
    Given the engine lists both "app-lv" and "module_026"
    When I start app-lv and module_026 in the same session
    Then both return 200 with distinct run_ids
    And app-lv serves /_stcore/health == "ok" while module_026 renders its 資料來源 input pane
    And the engine log has no traceback or readiness failure

  @tierA @S17
  Scenario: RBAC gates LV launch by role
    Given config/permissions.yaml grants operator execute on module_026 but not app-lv
    Then an operator is denied execute on app-lv while still allowed module_026
    And an admin (all:true) is allowed execute on app-lv
    And the deny is a policy decision, not a crash

  @tierB @S18
  Scenario: A curated subset CSV is consumable by labeling without path drift
    Given LV exported a cart CSV and wrote manifest.jsonl for the same folder
    When the curated rows are reconciled against that folder's manifest
    Then every cart sha256 resolves to a manifest entry (subset is a true subset)
    And labeling's folder scanner (module_010 scan_folder, used by module_026 local mode) ingests the curated folder
    And the ingested set matches the folder's image count and contains the curated filenames
    And module_026 is live to ingest the same local folder as a dataset source

  @tierC @S19
  Scenario: The manifest schema validates across the LV↔labeling boundary
    Given LV wrote a manifest.jsonl for a folder
    When a consumer loads it
    Then every entry exposes the 11 contract keys with correct types (labels is a list, embedding_refs a dict)
    And sha256 is 64 hex and phash is 16 hex or null
    And a corrupt or blank line is skipped without taking down the dataset load

  @tierC @S20
  Scenario: Cart-to-quiz needs four images and the round-trip refresh is incremental
    Given a cart with fewer than four images
    When the cart routes to 組考卷
    Then it refuses with "購物車至少要 4 張" and does not switch tools
    And with four or more images it seeds quiz records and switches to 組考卷
    And after a label edit, a manifest refresh re-hashes only the changed file (size+mtime fast-path)
