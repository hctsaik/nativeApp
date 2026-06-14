# language: en
# The curation cart is LV's hand-off staging area: a curator collects images
# (with a reason + provenance), exports a sha256-keyed CSV, and an on-disk
# curation log makes selections replayable across restarts.
Feature: LV curation cart stages a sha256-addressed subset for hand-off
  As a curator
  I want to collect chosen images with reasons and export them with content hashes
  So that the downstream labeling step receives an auditable, rename-proof subset

  @tierB @S14
  Scenario: The cart exports an auditable CSV carrying source, score and sha256
    Given the demo run has produced records with sha256 from the manifest
    When images are added to the 策展購物車 from a view with a source tag and a reason
    And the cart is exported to CSV
    Then the CSV header is exactly index,filename,path,label,split,sha256,source,score,reason
    And every exported row carries a non-empty sha256 (content-addressed hand-off)

  @tierC @S15
  Scenario: The curation log persists across restart and is replayable by sha256
    Given a curation entry was appended to output/curation_log.jsonl
    When the log is reloaded
    Then entries come back newest-first
    And match_shas_to_indices re-selects the same images by sha256 and skips hashes absent from the current run
