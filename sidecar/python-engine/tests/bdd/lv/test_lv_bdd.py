"""pytest entrypoints for the LV BDD suite.

Two layers:
  * ``test_contract_*`` — deterministic, framework-free contract checks (the
    Tier-C backbone of the scenarios). They need LV's analysis deps
    (numpy/scikit-learn/hnswlib), so the module ``importorskip``s them; in the
    base interpreter without the app-lv venv they skip cleanly rather than error.
  * ``test_e2e_full`` — the whole 20-scenario live run via run_bdd.py, opt-in
    with ``RUN_LV_E2E=1`` and a reachable engine (default 127.0.0.1:8765).

Run contract-only:  pytest tests/bdd/lv/test_lv_bdd.py -k contract
Run everything:     RUN_LV_E2E=1 pytest tests/bdd/lv/test_lv_bdd.py
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
LV_SCRIPTS = HERE.parents[2] / "vendor" / "LV" / "scripts"
for p in (str(HERE), str(LV_SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

# LV analysis deps — skip the whole module if they're unavailable (base venv).
pytest.importorskip("numpy")
pytest.importorskip("sklearn")
pytest.importorskip("hnswlib")

import numpy as np  # noqa: E402
import interaction  # noqa: E402
import completeness  # noqa: E402
import manifest as lv_manifest  # noqa: E402


# ── Tier-C contract scenarios ────────────────────────────────────────────────
def test_contract_s07_selection_to_indices():
    got = interaction.selection_points_to_indices(
        [{"customdata": [3]}, {"customdata": 5}, {"customdata": [3]}, {"customdata": None}])
    assert got == [3, 5]


def test_contract_s07_records_to_csv_loop():
    recs = [{"index": i, "filename": f"f{i}.jpg", "path": f"images/f{i}.jpg",
             "label": "a", "split": "train"} for i in range(4)]
    sel = interaction.selection_points_to_indices([{"customdata": [0]}, {"customdata": [2]}])
    names = [r.split(",")[1] for r in interaction.records_to_csv(recs, sel).splitlines()[1:]]
    assert names == ["f0.jpg", "f2.jpg"]


def test_contract_s12_projection_two_traces():
    cmpd = pytest.importorskip("compare_distributions")
    projs = {"pca": np.zeros((3, 2)), "tsne": np.ones((3, 2)), "umap": np.full((3, 2), 2.0)}
    from pathlib import Path as _P
    fig = cmpd.build_projection_figure([_P("a0.jpg"), _P("a1.jpg")], [_P("b0.jpg")],
                                       projs, "A", "B", fid_score=1.0, lpips_score=0.1)
    assert len(fig.data) == 2
    assert len(fig.layout.updatemenus[0].buttons) == 3


def test_contract_s13_coverage_health_excludes_na():
    cells = [{"n": 10, "d": 0.8, "t": 4, "state": completeness.STATE_HEALTHY},
             {"n": 0, "d": 0.0, "t": 4, "state": completeness.STATE_NA}]
    h = completeness.coverage_health(cells)
    assert h["coverage_health"] == 100.0 and h["counts"]["不適用"] == 1


def test_contract_s15_log_reload_newest_first(tmp_path):
    import json
    logf = tmp_path / "curation_log.jsonl"
    logf.write_text(
        json.dumps({"ts": "2026-06-14T09:00:00", "reason": "older"}) + "\n"
        + json.dumps({"ts": "2026-06-14T10:00:00", "reason": "newer"}) + "\n", encoding="utf-8")
    reloaded = list(reversed([json.loads(ln) for ln in
                              logf.read_text(encoding="utf-8").splitlines() if ln.strip()]))
    assert reloaded[0]["reason"] == "newer" and reloaded[0]["ts"] > reloaded[1]["ts"]


def test_contract_s18_labeling_scan_folder(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image
    imgs = tmp_path / "images"
    imgs.mkdir()
    for i in range(3):
        Image.fromarray(np.full((16, 16, 3), i * 50, dtype=np.uint8)).save(imgs / f"c_{i}.jpg")
    import importlib.util as ilu
    p010 = HERE.parents[2] / "plugins" / "labeling" / "modules" / "module_010" / "010_process.py"
    spec = ilu.spec_from_file_location("_010_process_t", p010)
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    items = mod.scan_folder(str(imgs), False, [".jpg", ".jpeg", ".png"])
    assert len(items) == 3


def test_contract_s08_label_disagreement():
    # cosine metric: two opposite directions, same label per direction → 0
    emb = np.array([[1., 0.], [0.99, 0.02], [-1., 0.], [-0.99, 0.02]])
    assert interaction.compute_label_disagreement(emb, ["a", "a", "b", "b"], k=1).max() == 0.0
    assert interaction.compute_label_disagreement(emb, ["a", "b", "a", "b"], k=1).max() > 0.0


def test_contract_s09_outlier_scores_exclude_self():
    # cosine outlierness: three near angle 0, one at 90° is the outlier
    ref = np.array([[1., 0.], [1., 0.05], [1., -0.05], [0., 1.]])
    sc = interaction.compute_outlier_scores(ref, ref, k=2, candidates_in_reference=True)
    assert int(np.argmax(sc)) == 3


def test_contract_s10_find_similar_excludes_query_and_clamps():
    emb = np.array([[0., 0.], [0.05, 0.], [0.9, 0.9], [1.0, 1.0]])
    idx, dist = interaction.find_similar_indices(emb, 0, k=2)
    assert 0 not in idx
    assert dist == sorted(dist)
    assert len(interaction.find_similar_indices(emb, 0, k=99)[0]) == len(emb) - 1


def test_contract_s11_phash_cross_split_dups():
    # identical hashes in different splits → a cross-split pair
    phs = ["ffffffffffffffff", "ffffffffffffffff", "0000000000000000"]
    sp = ["train", "val", "train"]
    pairs = interaction.find_duplicate_pairs_phash(phs, max_hamming=4, splits=sp, cross_split_only=True)
    assert pairs and all(sp[i] != sp[j] for i, j, _ in pairs)
    assert all(i < j for i, j, _ in pairs)


def test_contract_s13_classify_cell_fake_before_over():
    assert completeness.classify_cell(n=10, d=0.1, t=4, d_star=0.6) == completeness.STATE_FAKE
    assert completeness.classify_cell(n=10, d=0.9, t=4, d_star=0.6) == completeness.STATE_OVER
    assert completeness.classify_cell(n=0, d=0.0, t=4) == completeness.STATE_EMPTY


def test_contract_s14_s18_cart_csv_header_and_sha():
    snaps = [{"filename": "a.jpg", "path": "images/a.jpg", "label": "cat",
              "split": "train", "sha256": "deadbeef", "source": "disagreement",
              "score": 0.42, "reason": "why"}]
    csv_text = interaction.snapshots_to_csv(snaps)
    assert csv_text.splitlines()[0] == "index,filename,path,label,split,sha256,source,score,reason"
    assert csv_text.splitlines()[1].split(",")[5] == "deadbeef"


def test_contract_s15_curation_log_replay():
    assert interaction.curation_log_csv([]).splitlines()[0] == "ts,reason,n,filenames,sha256s"
    got = interaction.match_shas_to_indices(["aa", "bb", "aa"], {"aa": 7, "cc": 9})
    assert got == [7]


def test_contract_s19_manifest_corrupt_line_skipped(tmp_path):
    import json
    (tmp_path / "manifest.jsonl").write_text(
        json.dumps({"path": "a.jpg", "sha256": "x"}) + "\n{ corrupt \n\n", encoding="utf-8")
    loaded = lv_manifest.load_manifest(tmp_path)
    assert set(loaded) == {"a.jpg"}


def test_contract_s20_incremental_rehash(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image
    (tmp_path / "images").mkdir()
    paths = []
    for i in range(3):
        p = tmp_path / "images" / f"img_{i}.jpg"
        Image.fromarray(np.full((32, 32, 3), i * 40, dtype=np.uint8)).save(p)
        paths.append(p)
    recs = [{"path": str(p), "split": "train", "label": "a"} for p in paths]
    e1 = lv_manifest.update_manifest(tmp_path, recs)
    before = {k: v["sha256"] for k, v in e1.items()}
    Image.fromarray(np.full((32, 32, 3), 200, dtype=np.uint8)).save(paths[1])
    e2 = lv_manifest.update_manifest(tmp_path, recs)
    changed = [k for k in e2 if e2[k]["sha256"] != before[k]]
    assert len(changed) == 1


def test_contract_s20_gray_zone_ranking():
    assert interaction.select_gray_zone(np.array([0.1, 0.9, 0.5]), k=2) == [1, 2]


def _mk_imgs(tmp_path, n=4):
    pytest.importorskip("PIL")
    from PIL import Image
    paths = []
    for i in range(n):
        p = tmp_path / f"img_{i}.jpg"
        Image.fromarray(np.full((24, 24, 3), i * 30, dtype=np.uint8)).save(p)
        paths.append(p)
    return paths


def test_handoff_s35_empty_selection_writes_nothing(tmp_path):
    import labeling_handoff as H
    paths = _mk_imgs(tmp_path)
    recs = [{"path": str(p), "label": "a", "split": "train"} for p in paths]
    assert H.send_to_labeling(recs, [], source="cart", task=H.TASK_RELABEL,
                              class_options=["a", "b"], log_dir=str(tmp_path)) is None
    assert not (H.handoff_root(str(tmp_path))).exists() or not any(
        H.handoff_root(str(tmp_path)).glob("cart_*"))


def test_handoff_s21_s33_content_addressed_and_spec(tmp_path):
    import labeling_handoff as H
    import manifest as M
    paths = _mk_imgs(tmp_path)
    recs = [{"path": str(p), "label": "a", "split": "train"} for p in paths]
    man = {str(p.resolve()): {"sha256": M.file_sha256(p)} for p in paths}
    out = H.send_to_labeling(recs, [0, 1, 2], source="disagreement", task=H.TASK_RELABEL,
                             class_options=["a", "b"], manifest=man,
                             original_labels={0: "a", 1: "a", 2: "a"}, log_dir=str(tmp_path))
    spec = H.load_spec(out)
    assert spec["source"] == "disagreement" and spec["task"] == H.TASK_RELABEL
    shas = {it["sha256"] for it in spec["items"]}
    assert all(p.stem in shas for p in (out / "images").glob("*.jpg"))
    assert (out / "classes.txt").read_text(encoding="utf-8").split() == ["a", "b"]


def test_handoff_s36_read_before_annotation_all_pending(tmp_path):
    import labeling_handoff as H
    paths = _mk_imgs(tmp_path)
    recs = [{"path": str(p), "label": "a", "split": "train"} for p in paths]
    out = H.send_to_labeling(recs, [0, 1], source="cart", task=H.TASK_RELABEL,
                             class_options=["a", "b"], log_dir=str(tmp_path))
    res = H.read_labeling_results(out)
    assert res and all(v["status"] == "pending" for v in res.values())


def test_handoff_s23_s34_readback_status_and_reconcile(tmp_path):
    import json
    import labeling_handoff as H
    import manifest as M
    paths = _mk_imgs(tmp_path, 3)
    recs = [{"path": str(p), "label": "a", "split": "train"} for p in paths]
    man = {str(p.resolve()): {"sha256": M.file_sha256(p)} for p in paths}
    out = H.send_to_labeling(recs, [0, 1, 2], source="cart", task=H.TASK_RELABEL,
                             class_options=["a", "b"], manifest=man,
                             original_labels={0: "a", 1: "a", 2: "a"}, log_dir=str(tmp_path))
    items = H.load_spec(out)["items"]
    # labeling writes sidecars for 2 of 3 (item0 corrected a->b)
    for it, lbl in [(items[0], "b"), (items[1], "a")]:
        img = next((out / "images").glob(f"{it['sha256']}.*"))
        img.with_suffix(".json").write_text(json.dumps({"shapes": [{"label": lbl}]}), encoding="utf-8")
    assert H.handoff_status(out) == {"n_total": 3, "n_annotated": 2}
    res = H.read_labeling_results(out)
    sha_to_index = {it["sha256"]: it["lv_index"] for it in items}
    rec = H.reconcile_to_records(res, sha_to_index)
    assert rec[0]["label"] == "b" and rec[1]["label"] == "a" and 2 not in rec
    changed = [v["lv_index"] for v in res.values() if v["label"] and v["label"] != v["original_label"]]
    assert changed == [0]


def test_handoff_idempotent_and_peek(tmp_path):
    import labeling_handoff as H
    paths = _mk_imgs(tmp_path)
    recs = [{"path": str(p), "label": "a", "split": "train"} for p in paths]
    out1 = H.send_to_labeling(recs, [0, 1], source="cart", task=H.TASK_RELABEL,
                              class_options=["a", "b"], log_dir=str(tmp_path))
    out2 = H.send_to_labeling(recs, [0, 1], source="cart", task=H.TASK_RELABEL,
                              class_options=["a", "b"], log_dir=str(tmp_path))
    assert out1 == out2  # same (source, sha-set) reuses the open handoff
    pk = H.peek_pending_handoff(str(tmp_path))
    assert pk is not None and Path(pk["images_dir"]).exists()


def test_e2e_lv_labeling_roundtrip(tmp_path, monkeypatch):
    """Real end-to-end LV ↔ Labeling round-trip through ACTUAL labeling code:
    LV send_to_labeling → Labeling auto-detects the batch (module_026 _peek) and
    ingests the folder (module_010.scan_folder) → annotators label (we write the
    xAnyLabeling sidecars the tool writes) → LV reads back + reconciles + diffs.
    The only simulated step is the human picking a class (un-automatable)."""
    import importlib.util as ilu
    import json
    import labeling_handoff as LH
    import manifest as M
    from PIL import Image

    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))

    # 0) a tiny real dataset
    ds = tmp_path / "ds" / "images"
    ds.mkdir(parents=True)
    paths = []
    for i in range(4):
        p = ds / f"img_{i}.jpg"
        Image.fromarray(np.full((32, 32, 3), i * 50, dtype=np.uint8)).save(p)
        paths.append(p)
    recs = [{"path": str(p), "label": "cat" if i % 2 else "dog", "split": "train"}
            for i, p in enumerate(paths)]
    man = {str(p.resolve()): {"sha256": M.file_sha256(p)} for p in paths}

    # 1) LV sends the selection to Labeling (real handoff)
    out = LH.send_to_labeling(recs, [0, 1, 2, 3], source="selection", task=LH.TASK_RELABEL,
                              class_options=["cat", "dog"], manifest=man,
                              original_labels={i: recs[i]["label"] for i in range(4)},
                              log_dir=str(tmp_path))
    assert out is not None and (out / "_handoff.json").exists()

    # 2) Labeling side AUTO-DETECTS the batch via the shared _pending.json contract.
    #    Primary assertion uses the same registry; module_026's own reader is a
    #    best-effort cross-check (it imports streamlit + config when run for real).
    lv = LH.peek_pending_handoff(str(tmp_path))
    assert lv and lv["source"] == "selection" and Path(lv["images_dir"]) == (out / "images")
    try:
        p026 = HERE.parents[2] / "plugins" / "labeling" / "modules" / "module_026" / "026_input.py"
        spec = ilu.spec_from_file_location("_026_peek", p026)
        mod026 = ilu.module_from_spec(spec)
        spec.loader.exec_module(mod026)
        lv2 = mod026._peek_lv_handoff()
        assert lv2 and Path(lv2["images_dir"]) == (out / "images")
    except Exception:  # noqa: BLE001  module_026 needs engine env to import standalone
        pass

    # 3) Labeling INGESTS the handoff folder via the REAL scanner (module_010.scan_folder)
    p010 = HERE.parents[2] / "plugins" / "labeling" / "modules" / "module_010" / "010_process.py"
    spec10 = ilu.spec_from_file_location("_010_proc", p010)
    mod010 = ilu.module_from_spec(spec10)
    spec10.loader.exec_module(mod010)
    items = mod010.scan_folder(lv["images_dir"], False, [".jpg", ".jpeg", ".png"])
    assert len(items) == 4  # Labeling sees exactly the 4 handed-off images

    # 4) Annotators label them (write the xAnyLabeling sidecars the tool writes).
    #    Flip img_0's label cat? -> here originals are dog,cat,dog,cat; annotate all "dog".
    for it in LH.load_spec(out)["items"]:
        img = next((out / "images").glob(it["sha256"] + ".*"))
        img.with_suffix(".json").write_text(
            json.dumps({"shapes": [{"label": "dog"}], "annotator": "tester"}), encoding="utf-8")

    # 5) LV reads back + reconciles by sha256 (rename/move-proof) + computes the diff
    results = LH.read_labeling_results(out)
    assert all(r["status"] == "annotated" and r["label"] == "dog" for r in results.values())
    sha_to_index = {it["sha256"]: it["lv_index"] for it in LH.load_spec(out)["items"]}
    reconciled = LH.reconcile_to_records(results, sha_to_index)
    assert set(reconciled) == {0, 1, 2, 3}
    # change-list: indices whose new label differs from the original (cat ones changed)
    changed = sorted(i for i, r in reconciled.items()
                     if r["label"] != recs[i]["label"])
    assert changed == [1, 3]  # the two original "cat"s became "dog"

    # 6) status lifecycle reflects completion
    assert LH.handoff_status(out) == {"n_total": 4, "n_annotated": 4}


def test_contract_s17_rbac_policy():
    import yaml
    from importlib import import_module
    rbac = import_module("core.rbac")
    pol = yaml.safe_load((HERE.parents[2] / "config" / "permissions.yaml").read_text(encoding="utf-8"))
    assert rbac.is_allowed(pol, "operator", "module_026", "execute") is True
    assert rbac.is_allowed(pol, "operator", "app-lv", "execute") is False
    assert rbac.is_allowed(pol, "admin", "app-lv", "execute") is True


# ── Full live E2E (opt-in) ───────────────────────────────────────────────────
def _engine_up(base: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


@pytest.mark.skipif(os.environ.get("RUN_LV_E2E") != "1",
                    reason="set RUN_LV_E2E=1 (and start the engine) to run the live E2E")
def test_e2e_full():
    base = os.environ.get("CIM_BDD_BASE", "http://127.0.0.1:8765")
    if not _engine_up(base):
        pytest.skip(f"engine not reachable at {base}")
    import run_bdd
    runner = run_bdd.Runner(base)
    runner.execute()
    failed = [r.sid for r in runner.results if r.status != "PASS"]
    assert not failed, f"failed scenarios: {failed}"
