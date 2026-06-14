# language: en
# EVERY LV feature hands a subset to the Labeling tool through ONE mechanism
# (labeling_handoff.send_to_labeling), content-addressed by sha256, async
# (launching Labeling tears LV down → state lives on disk in a _pending.json
# registry). The hand-over is ONE-WAY for all DATASET feedback (relabel / verify
# / adjudicate / fresh): LV does not track or read those batches back — there is
# no inbox in LV. Annotation + feedback complete on the Labeling side; the batch
# is closed out when it reaches export (module_014), which marks the registry
# entry delivered so the Source tab (module_026) stops re-suggesting it. The
# read-back library functions still exist as a CONTRACT (consumed by module_026's
# peek and the export close-out), just not by an LV-side inbox.
# The quiz (組考卷) does NOT hand off to Labeling at all: it is an in-LV blind
# self-consistency measurement (score_quiz), fully one-way / self-contained — no
# send, no read-back.
Feature: Every LV dataset-feedback feature hands a subset to Labeling one-way; the loop closes on the Labeling side
  As a curator
  I want every LV dataset-feedback signal (cart / disagreement / outlier / near-dup /
  diversity / gap / compare-novel / gray-zone / single image) to go to Labeling the same way
  So that the cross-tool hand-over is one coherent, auditable, fire-and-forget loop

  @tierC @S21
  Scenario: All features hand off through one content-addressed contract
    Given a subset of records from any LV feature
    When send_to_labeling(records, indices, source, task, class_options) runs
    Then it writes <CIM_LOG_DIR>/lv_labeling_handoff/<source>_<ts>/ with images/<sha256>.<ext>, classes.txt and _handoff.json
    And the image filename stem equals its sha256 (content-addressed, rename-proof)
    And the handoff is registered in _pending.json so it survives LV being torn down

  @tierC @S35
  Scenario: An empty selection writes nothing and launches nothing
    Given no images are selected
    When send_to_labeling runs with an empty index set
    Then it returns None and creates no handoff folder on disk

  @tierC @S36
  Scenario: Reading back before annotation reports pending, not failure
    Given a handoff folder exists but Labeling has written no sidecar JSON yet
    When read_labeling_results parses it
    Then every item is reported status "pending" and nothing is scored or committed

  @tierC @S23 @S33
  Scenario: Read-back is keyed by sha256 and reconciles rename-proof
    Given Labeling wrote xAnyLabeling <sha256>.json (shapes[].label) for some images
    When read_labeling_results parses the folder
    Then each label is keyed by the image's sha256, not its filename
    And reconcile_to_records maps them onto current LV record indices by content hash
    And a returned image whose sha256 is absent from the current run is dropped, not mis-attached

  @tierC @S34
  Scenario: Each batch tracks sent → annotated → read counts
    Given a handoff batch of N images
    When 0, then k, then N images have parseable sidecar labels
    Then handoff_status reports n_annotated = 0, k, N respectively without reopening Labeling

  @tierC @S24
  Scenario: Re-label read-back produces a change-list vs the original label (library contract)
    Given the handoff recorded each image's original label
    When Labeling returns a different label for some images
    Then read_labeling_results / reconcile_to_records list exactly the images whose label changed (original → new)
    And the corrected labels are the deliverable on the Labeling side (exported), not applied back into LV

  @tierB @S22
  Scenario: The curation cart hands its sha256-keyed subset to Labeling one-way
    Given LV is loaded with a curation cart holding images
    When I click "📤 送整車到 Labeling 標註"
    Then a handoff folder containing exactly the cart images is written and registered
    And LV shows a one-way send confirmation and posts OPEN_TOOL so the portal switches to sheet-annotation
    And module_026 auto-prefills the handoff folder path (no return to LV; the batch is closed out on export)

  @tierB @S31 @smoke
  Scenario: Quiz is an in-LV blind measurement and does NOT hand off to Labeling
    Given a generated quiz (skinned questions + golden key)
    When the curator answers it blind inside LV
    Then score_quiz reports self_consistency and vs_golden in LV, with no Labeling round-trip
    And the quiz never sends a handoff or writes labels back to the dataset (measurement only, fully one-way)

  @tierA @S32
  Scenario: The viewer slot sends exactly one image through the same mechanism
    Given a single image is active in the LV viewer slot
    When I click "📤 送這張到 Labeling"
    Then a handoff folder with exactly that one image is written
    And re-sending the same image reuses the open handoff (idempotent by sha256)
