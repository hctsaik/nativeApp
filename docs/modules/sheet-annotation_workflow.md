# sheet-annotation_workflow - Annotation Workflow

## Overview

`sheet-annotation_workflow` is the Labeling workflow sheet. It connects dataset download, data feeding, annotation, sync back, dashboard, export, AI pre-labeling, label management, and review into one ordered page.

## Tab Order

| Order | Plugin | Purpose |
|---:|---|---|
| 0 | `module_019` Data Downloader | Download source datasets from a remote service. |
| 1 | `module_010` Data Feeder | Build the active `DatasetManifest`. |
| 2 | `module_012` Annotation | Open and manage the annotation session. |
| 3 | `module_013` Sync Back | Sync annotation results back to service/output storage. |
| 4 | `module_020` Download | View/download uploaded or archived annotation packages. |
| 5 | `module_015` Dashboard | Inspect annotation progress and dataset statistics. |
| 6 | `module_014` Export | Export COCO/YOLO/Pascal VOC/ImageFolder/CSV packages. |
| 7 | `module_016` AI Pre-labeling | Run YOLO/classifier pre-labeling. |
| 8 | `module_017` Label Manager | Rename, merge, delete, and audit labels. |
| 9 | `module_018` Review Gallery | Review images with overlays and mark rework. |

## Shared Data

| Path | Used For |
|---|---|
| `{CIM_LOG_DIR}/config/shared.json` | Latest manifest handoff between modules. |
| `{CIM_LOG_DIR}/db/manifest.sqlite` | Dataset manifests, items, exports, sync queue, snapshots. |
| `{CIM_LOG_DIR}/config/module_012_classifications_*.json` | Image-level classifications. |
| `{CIM_LOG_DIR}/xanylabeling_state/` | X-AnyLabeling runtime state. |
| `{image_dir}/{image_stem}.json` | X-AnyLabeling/LabelMe annotation JSON. |

The runtime database owns the actual tab list. `engine.py` reconciles stale `annotation_workflow` tabs on startup so older local `logs/data/tools.sqlite` files receive Dashboard, AI Pre-labeling, and the rest of the workflow without manual reset.
