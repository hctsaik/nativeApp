# LV BDD E2E Report

- engine: `http://127.0.0.1:8765`
- cim-gui MCP server tools advertised: **13**
- **20/20 scenarios PASS**

| ID | Tier | Status | Title | checks |
|----|------|--------|-------|--------|
| S01 | A | ✅ | LV launches via the literal cim-gui MCP server (stdio) | 6/6 |
| S02 | A | ✅ | Feature-map popover documents the 5 tools + data contract | 3/3 |
| S03 | A | ✅ | No-folder run shows a clear guard + onboarding | 4/4 |
| S04 | A | ✅ | Missing-model and bad-path are distinct, non-crashing guards | 4/4 |
| S05 | A | ✅ | Navigation across all five LV tools keeps the shell intact | 2/2 |
| S06 | B | ✅ | One-click coco8 demo extracts embeddings + writes manifest | 6/6 |
| S07 | B | ✅ | Selection surfaces member images; selection→indices contract | 4/4 |
| S08 | B | ✅ | Label-disagreement recolour; compute_label_disagreement contract | 4/4 |
| S09 | B | ✅ | Outlier sort surfaces isolated images; compute_outlier_scores contract | 3/3 |
| S10 | B | ✅ | NN query chain; find_similar_indices contract | 4/4 |
| S11 | B | ✅ | phash near-dup scan finds the planted leakage pair | 4/4 |
| S12 | B | ✅ | Compare Distributions projects two folders | 4/4 |
| S13 | B | ✅ | Completeness coverage health + fake-complete guard | 7/7 |
| S14 | B | ✅ | Curation cart exports an auditable sha256 CSV | 3/3 |
| S15 | C | ✅ | Curation log persists & replays by sha256 | 3/3 |
| S16 | A | ✅ | LV and a labeling module both start in one engine session | 4/4 |
| S17 | A | ✅ | RBAC gates LV launch by role | 3/3 |
| S18 | B | ✅ | Curated subset CSV is a true subset of the manifest | 5/5 |
| S19 | C | ✅ | Manifest schema validates across the boundary | 6/6 |
| S20 | C | ✅ | Cart→quiz guard + incremental manifest round-trip | 4/4 |
