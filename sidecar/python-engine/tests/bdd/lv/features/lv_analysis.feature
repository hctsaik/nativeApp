# language: en
# LV pure dataset-analysis workflows. Tier-B scenarios run live against a
# provisioned random-weight resnet18 + the generated coco8 fixture; each carries a
# deterministic framework-free contract assertion (interaction.py / manifest.py /
# completeness.py) as its backbone so the proof never depends on Plotly canvas
# interaction that headless browsers cannot perform.
Feature: LV analyses an image dataset's embedding distribution
  As a data curator
  I want to extract embeddings, find mislabels/outliers/duplicates and compare distributions
  So that I can judge dataset quality before annotation

  @tierB @S06 @smoke
  Scenario: One-click coco8 demo extracts embeddings and writes the manifest contract
    Given a resnet18 model and the coco8 demo dataset are provisioned
    When I load the coco8 demo (train + val) and run "Visualize Embeddings"
    Then extraction completes for 19 images across 2 splits with no error alert
    And a 2-D scatter renders with a per-class legend
    And each loaded folder gains a manifest.jsonl whose entries carry path, sha256, phash, split, labels and embedding_refs

  @tierB @S07
  Scenario: Selecting points surfaces their member images in the right pane
    Given the demo run has produced a scatter
    Then the right pane offers 選取 / 相似 / 重複 / 選樣 / 匯出清單 panels
    And the default unselected view ranks by 離群度
    And selection_points_to_indices maps a plotly selection payload to de-duplicated, order-preserved row indices
    And feeding the selected indices through records_to_csv surfaces exactly those member images

  @tierB @S08
  Scenario: Recolouring by label disagreement flags neighbour conflicts honestly
    Given the demo run has produced a scatter with >=2 classes
    When I set 著色依據 to "標籤分歧"
    Then a disagreement colour scale is applied with the disclaimer "非品質判定"
    And compute_label_disagreement returns 0 for an all-same-label neighbourhood and >0 when neighbours differ

  @tierB @S09
  Scenario: Outlier sort surfaces the most isolated images first
    Given the demo run has produced a scatter
    Then the unselected default view ranks by 離群度 (geometric distance only)
    And compute_outlier_scores excludes an image's own self-neighbour and ranks higher for more isolated points

  @tierB @S10
  Scenario: Nearest-neighbour query chain pivots from image to image
    Given the demo run has produced embeddings
    Then the 相似 panel can show k nearest neighbours for a query image
    And find_similar_indices excludes the query itself, returns ascending cosine distance and clamps k to N-1

  @tierB @S11
  Scenario: phash near-duplicate scan finds the planted train-val leakage pair
    Given the coco8 fixture planted one byte-identical image across train and val
    When a cross-split phash duplicate scan runs at Hamming threshold 4
    Then the planted leakage pair is reported and every reported pair spans different splits
    And find_duplicate_pairs_phash returns (i, j, hamming) with i<j sorted closest-first

  @tierB @S12
  Scenario: Compare Distributions projects two folders into one embedding space
    Given LV is open on "Compare Distributions" with two folders provisioned
    When I run the comparison
    Then a joint projection renders two colour-coded groups
    And build_projection_figure produces two traces plus PCA/t-SNE/UMAP toggle buttons

  @tierB @S13
  Scenario: Completeness heatmap scores coverage and guards against fake-complete cells
    Given the demo run has produced records and embeddings
    When the completeness grid is built over two attribute axes
    Then a Coverage Health score in [0,100] is shown and empty cells are excluded from scoring
    And classify_cell flags a high-count low-diversity cell as 假完整 before 過多
