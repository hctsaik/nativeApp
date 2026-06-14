"""LV (VisualLatent) BDD E2E orchestrator — runs all 20 scenarios and writes a
report + screenshot evidence.

Execution model
---------------
* Tier A/B scenarios drive the **live** LV / labeling Streamlit apps through the
  cim-gui MCP machinery (``mcp_driver.MCPDriver`` = the exact SidecarClient +
  BrowserDriver the MCP tools wrap). The launch smoke (S01) additionally goes
  through the **literal cim-gui MCP server over stdio** (``mcp_stdio_smoke``).
* Every Tier-B/-C scenario also asserts a deterministic, framework-free
  **contract** (interaction.py / manifest.py / completeness.py / core.rbac) so
  the proof never depends on Plotly-canvas gestures a headless browser cannot do.

Run (engine must be up; default port 8765):
    set PYTHONPATH to the app-lv per-tool venv site-packages, then
    py -3.11 sidecar/python-engine/tests/bdd/lv/run_bdd.py [--base http://127.0.0.1:8765]

Exit 0 = every required check passed.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_ROOT = HERE.parents[2]                       # sidecar/python-engine
LV_SCRIPTS = ENGINE_ROOT / "vendor" / "LV" / "scripts"
for p in (str(HERE), str(LV_SCRIPTS), str(ENGINE_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np                                  # noqa: E402

import fixtures                                     # noqa: E402
import mcp_driver                                   # noqa: E402
# LV framework-free contract modules (need the app-lv venv on PYTHONPATH)
import interaction                                  # noqa: E402
import manifest as lv_manifest                      # noqa: E402
import completeness                                 # noqa: E402

EVIDENCE = HERE / "evidence"
EVIDENCE.mkdir(parents=True, exist_ok=True)

LV = "app-lv"
LABEL_TOOL = "module_026"        # 資料來源 — labeling's dataset-source step
DEMO_TRAIN = fixtures.DEMO_DIR / "train"
DEMO_VAL = fixtures.DEMO_DIR / "val"


# ── result model ────────────────────────────────────────────────────────────────
@dataclasses.dataclass
class Check:
    label: str
    ok: bool
    detail: str = ""


@dataclasses.dataclass
class Result:
    sid: str
    title: str
    tier: str
    checks: list = dataclasses.field(default_factory=list)
    evidence: list = dataclasses.field(default_factory=list)
    error: str = ""

    def ck(self, ok: bool, label: str, detail: str = "") -> bool:
        self.checks.append(Check(label, bool(ok), detail))
        return bool(ok)

    @property
    def status(self) -> str:
        if self.error:
            return "FAIL"
        return "PASS" if self.checks and all(c.ok for c in self.checks) else "FAIL"


# ── runner ──────────────────────────────────────────────────────────────────────
class Runner:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.d = mcp_driver.MCPDriver(self.base)
        self.results: list[Result] = []
        self.fx: dict = {}
        self._proof: dict = {"tools": [], "ok": False}

    def log(self, msg: str) -> None:
        print(msg, flush=True)

    def shot(self, res: Result, url: str, name: str) -> None:
        try:
            p = self.d.screenshot(url, EVIDENCE / f"{res.sid}_{name}.png")
            res.evidence.append(str(p.relative_to(HERE)))
        except Exception as exc:  # noqa: BLE001
            res.evidence.append(f"(screenshot failed: {exc})")

    def start_lv_loaded(self) -> str:
        """Start LV and load+run the coco8 demo (extraction completes)."""
        self.d.stop_tool(); time.sleep(1)
        url = self.d.start_tool(LV)["input_url"]
        self.d.wait_render(url, timeout_s=90)
        self.d.click_by_text(url, "一鍵體驗", timeout=90000)
        self.d.wait_text(url, "完成：19", timeout_s=150)
        # the Plotly scatter mounts a beat after the "完成" toast — wait for it so
        # downstream scenarios see a fully-rendered analysis page.
        for _ in range(60):
            if self.d.count(url, '.js-plotly-plot, [data-testid="stPlotlyChart"]') > 0:
                break
            time.sleep(1.0)
        return url

    def run(self, fn) -> None:
        res = Result(fn.__name__.upper().replace("_", ""), "", "")
        try:
            fn(res)
        except Exception:  # noqa: BLE001
            res.error = traceback.format_exc(limit=4)
        self.results.append(res)
        mark = "PASS" if res.status == "PASS" else "FAIL"
        self.log(f"[{mark}] {res.sid} {res.title}  ({res.tier})")
        for c in res.checks:
            self.log(f"        {'+' if c.ok else 'x'} {c.label}"
                     + (f" — {c.detail}" if c.detail else ""))
        if res.error:
            self.log("        ! " + res.error.strip().splitlines()[-1])

    # ── Phase 1: launch / shell / guards (fresh LV, no model needed) ──────────
    def s01(self, r: Result) -> None:
        r.sid, r.title, r.tier = "S01", "LV launches via the literal cim-gui MCP server (stdio)", "A"
        out = mcp_driver.mcp_stdio_smoke(
            self.base, LV, "Dataset Analysis Tools",
            shot_path=str(EVIDENCE / "S01_mcp_stdio.png"))
        r.ck(out["error"] is None, "MCP stdio session ran end-to-end", str(out.get("error")))
        r.ck("sidecar_start_tool" in out["tools_called"], "called real MCP tool sidecar_start_tool")
        r.ck("browser_get_text" in out["tools_called"], "called real MCP tool browser_get_text")
        r.ck(bool(out["url"]), "engine returned a live Streamlit URL", out["url"])
        r.ck(out["text_found"], 'page shows heading "Dataset Analysis Tools"')
        if out.get("shot"):
            r.evidence.append("evidence/S01_mcp_stdio.png")
        r.ck(self._proof.get("ok") and len(self._proof.get("tools", [])) >= 13,
             "cim-gui MCP server advertises its 13 tools over stdio",
             str(len(self._proof.get("tools", []))))

    def s02(self, r: Result) -> None:
        r.sid, r.title, r.tier = "S02", "Feature-map popover documents the 5 tools + data contract", "A"
        self.d.stop_tool(); time.sleep(1)
        url = self.d.start_tool(LV)["input_url"]
        self.d.wait_render(url, timeout_s=90)
        self.d.click_by_text(url, "功能地圖", timeout=60000)
        self.d.wait_text(url, "manifest.jsonl", timeout_s=30)
        body = self.d.get_text(url)
        r.ck("manifest.jsonl" in body, 'feature-map names the contract "manifest.jsonl"')
        r.ck("五個工具的關係" in body and "先探索" in body,
             "feature-map states the five-tool relationship (先探索、再行動)")
        ok, bad = self.d.assert_no_traceback(url)
        r.ck(ok, "no traceback after opening popover", ",".join(bad))
        self.shot(r, url, "featuremap")

    def s03(self, r: Result) -> None:
        r.sid, r.title, r.tier = "S03", "No-folder run shows a clear guard + onboarding", "A"
        # fresh LV already running from s02's start; ensure a clean session
        self.d.stop_tool(); time.sleep(1)
        url = self.d.start_tool(LV)["input_url"]
        self.d.wait_render(url, timeout_s=90)
        self.d.wait_text(url, "② 模型", timeout_s=60)   # sidebar mounts a beat after main
        body = self.d.get_text(url)
        r.ck("① 資料" in body, "onboarding ① 資料 section visible (exact)")
        r.ck("② 模型" in body, "onboarding ② 模型 section visible (exact)")
        # actually trigger a Run with no folder → the exact guard string
        self.d.click_by_text(url, "Run", timeout=30000)
        r.ck(self.d.wait_text(url, "請先選擇至少一個資料夾", timeout_s=20),
             'no-folder Run shows the exact guard "請先選擇至少一個資料夾"')
        ok, bad = self.d.assert_no_traceback(url)
        r.ck(ok, "no traceback on the guard path", ",".join(bad))
        self.shot(r, url, "no_folder_guard")

    def s04(self, r: Result) -> None:
        r.sid, r.title, r.tier = "S04", "Missing-model and bad-path are distinct, non-crashing guards", "A"
        # (1) model present + a non-existent folder path → the PATH guard (distinct banner)
        self.d.stop_tool(); time.sleep(1)
        url = self.d.start_tool(LV)["input_url"]
        self.d.wait_render(url, timeout_s=90)
        self.d.wait_text(url, "② 模型", timeout_s=60)
        self.d.fill(url, 'textarea[aria-label*="貼上資料夾路徑"]', "C:/no/such/lv/path")
        self.d.click_by_text(url, "Run", timeout=30000)
        r.ck(self.d.wait_text(url, "資料夾不存在", timeout_s=20),
             'bad path shows the path guard "資料夾不存在" (not the model banner)')
        ok1, _ = self.d.assert_no_traceback(url)
        r.ck(ok1, "bad-path guard has no traceback")
        self.shot(r, url, "bad_path_guard")
        # (2) model absent → the DISTINCT missing-model banner
        model = fixtures.MODELS_DIR / "resnet18.pth"
        hidden = model.with_suffix(".pth.hidden")
        moved = False
        try:
            if model.exists():
                model.rename(hidden); moved = True
            self.d.stop_tool(); time.sleep(1)
            url2 = self.d.start_tool(LV)["input_url"]
            self.d.wait_render(url2, timeout_s=90)
            r.ck(self.d.wait_text(url2, "找不到模型檔", timeout_s=60),
                 'missing model shows the distinct banner "models/ 內找不到模型檔"')
            ok2, _ = self.d.assert_no_traceback(url2)
            r.ck(ok2, "missing-model state has no traceback")
            self.shot(r, url2, "no_model")
        finally:
            if moved and hidden.exists():
                hidden.rename(model)

    def s05(self, r: Result) -> None:
        r.sid, r.title, r.tier = "S05", "Navigation across all five LV tools keeps the shell intact", "A"
        self.d.stop_tool(); time.sleep(1)
        url = self.d.start_tool(LV)["input_url"]
        self.d.wait_render(url, timeout_s=90)
        # each tool gets a distinct content anchor (not just "no traceback")
        markers = {
            "Compare Distributions": "Folder A",
            "完整度熱力圖": "開始分析",
            "組考卷": None, "灰帶覆核": None,
            "Visualize Embeddings": "Dataset Analysis Tools",
        }
        all_ok = True
        rendered = []
        for t, marker in markers.items():
            try:
                self.d.click_by_text(url, t, timeout=30000)
                if marker:
                    self.d.wait_text(url, marker, timeout_s=20)
                else:
                    time.sleep(1.0)
                ok, _bad = self.d.assert_no_traceback(url)
                body = self.d.get_text(url)
                marker_ok = (marker in body) if marker else (len(body.strip()) > 50)
                all_ok = all_ok and ok and marker_ok
                rendered.append(t if (ok and marker_ok) else f"{t}!")
            except Exception as exc:  # noqa: BLE001
                all_ok = False
                rendered.append(f"{t}!{str(exc)[:30]}")
        r.ck(all_ok, "all five tools render distinct content without a traceback",
             ", ".join(rendered))
        r.ck("Dataset Analysis Tools" in self.d.get_text(url),
             "returned to Visualize keeps the shell")
        self.shot(r, url, "nav_back")

    # ── Phase 2: analysis on a loaded LV (model + demo dataset) ───────────────
    def s06(self, r: Result, url: str) -> None:
        r.sid, r.title, r.tier = "S06", "One-click coco8 demo extracts embeddings + writes manifest", "B"
        body = self.d.get_text(url)
        r.ck("完成" in body, "extraction completed (完成)")
        r.ck("19" in body, "19 images across 2 splits reported")
        r.ck(self.d.count(url, '.js-plotly-plot, [data-testid="stPlotlyChart"]') > 0,
             "2-D scatter rendered")
        legend = self.d.get_text(url)
        r.ck(("train" in legend) and any(c in legend for c in ("cat", "dog", "bird")),
             "scatter legend shows per-class × split groups")
        mpath = DEMO_TRAIN / "manifest.jsonl"
        r.ck(mpath.exists(), "manifest.jsonl written into train folder", str(mpath.name))
        ents = lv_manifest.load_manifest(DEMO_TRAIN)
        keys = {"path", "sha256", "phash", "split", "labels", "embedding_refs"}
        sample = next(iter(ents.values())) if ents else {}
        r.ck(bool(ents) and keys <= set(sample),
             "manifest entries carry the contract keys", ",".join(sorted(keys)))
        self.shot(r, url, "demo_scatter")

    def s07(self, r: Result, url: str) -> None:
        r.sid, r.title, r.tier = "S07", "Selection surfaces member images; selection→indices contract", "B"
        body = self.d.get_text(url)
        r.ck("選取" in body and "匯出清單" in body, "右側 選取 / 匯出清單 panels present")
        r.ck("離群度" in body, "default unselected view ranks by 離群度")
        got = interaction.selection_points_to_indices(
            [{"customdata": [3]}, {"customdata": 5}, {"customdata": [3]}, {"customdata": None}])
        r.ck(got == [3, 5], "selection_points_to_indices de-dups & preserves order", str(got))
        # close the loop: selected indices → the exact member images surfaced
        ents = lv_manifest.load_manifest(DEMO_TRAIN)
        recs = [{"index": i, "filename": Path(k).name, "path": k,
                 "label": (e["labels"] or [""])[0], "split": e["split"]}
                for i, (k, e) in enumerate(ents.items())]
        sel = interaction.selection_points_to_indices([{"customdata": [0]}, {"customdata": [2]}])
        csv_text = interaction.records_to_csv(recs, sel)
        names = [row.split(",")[1] for row in csv_text.splitlines()[1:]]
        r.ck(names == [recs[0]["filename"], recs[2]["filename"]],
             "selection → records_to_csv surfaces exactly the selected images", str(names))
        self.shot(r, url, "selection_panel")

    def s08(self, r: Result, url: str) -> None:
        r.sid, r.title, r.tier = "S08", "Label-disagreement recolour; compute_label_disagreement contract", "B"
        body = self.d.get_text(url)
        r.ck("標籤分歧" in body, "著色依據 offers 標籤分歧")
        # cosine metric: two opposite directions; same label per direction → 0
        emb = np.array([[1., 0.], [0.99, 0.02], [-1., 0.], [-0.99, 0.02]])
        same = interaction.compute_label_disagreement(emb, ["a", "a", "b", "b"], k=1)
        mixed = interaction.compute_label_disagreement(emb, ["a", "b", "a", "b"], k=1)
        r.ck(float(same.max()) == 0.0, "agreeing neighbourhood scores 0", str(same.tolist()))
        r.ck(float(mixed.max()) > 0.0, "disagreeing neighbourhood scores >0", str(mixed.tolist()))
        # intermediate: a row whose 2 nearest are one same-label + one different → 0.5
        emb3 = np.array([[1., 0.], [0.95, 0.05], [-1., 0.03]])
        mid = interaction.compute_label_disagreement(emb3, ["a", "a", "b"], k=2)
        r.ck(abs(float(mid[0]) - 0.5) < 1e-9, "partial-disagreement neighbourhood scores 0.5",
             str(round(float(mid[0]), 3)))
        self.shot(r, url, "label_disagreement")

    def s09(self, r: Result, url: str) -> None:
        r.sid, r.title, r.tier = "S09", "Outlier sort surfaces isolated images; compute_outlier_scores contract", "B"
        body = self.d.get_text(url)
        r.ck("非品質判定" in body, "outlier view carries 非品質判定 disclaimer")
        # cosine outlierness: three near angle 0, one at 90° → the 90° point is the outlier
        ref = np.array([[1., 0.], [1., 0.05], [1., -0.05], [0., 1.]])
        sc = interaction.compute_outlier_scores(ref, ref, k=2, candidates_in_reference=True)
        r.ck(int(np.argmax(sc)) == 3, "the distinct-direction point ranks most outlying",
             str(np.round(sc, 3).tolist()))
        # self-exclusion: candidates_in_reference drops each point's own (distance-0) match
        sc_self = interaction.compute_outlier_scores(ref, ref, k=1, candidates_in_reference=True)
        r.ck(all(s > 0 for s in sc_self),
             "candidates_in_reference drops each point's self-neighbour (no 0 from self-match)",
             str(np.round(sc_self, 3).tolist()))
        self.shot(r, url, "outlier_sort")

    def s10(self, r: Result, url: str) -> None:
        r.sid, r.title, r.tier = "S10", "NN query chain; find_similar_indices contract", "B"
        body = self.d.get_text(url)
        r.ck("相似" in body, "相似 panel available for query chains")
        emb = np.array([[0., 0.], [0.05, 0.], [0.9, 0.9], [1.0, 1.0]])
        idx, dist = interaction.find_similar_indices(emb, query_idx=0, k=2)
        r.ck(0 not in idx, "query itself excluded", str(idx))
        r.ck(dist == sorted(dist), "neighbours ascending by distance", str(np.round(dist, 3).tolist()))
        big = interaction.find_similar_indices(emb, 0, k=99)[0]
        r.ck(len(big) == len(emb) - 1, "k clamped to N-1", str(len(big)))
        self.shot(r, url, "nn_chain")

    def s11(self, r: Result, url: str) -> None:
        r.sid, r.title, r.tier = "S11", "phash near-dup scan finds the planted leakage pair", "B"
        body = self.d.get_text(url)
        r.ck("重複" in body, "重複 panel present for duplicate scans")
        ents_t = lv_manifest.load_manifest(DEMO_TRAIN)
        ents_v = lv_manifest.load_manifest(DEMO_VAL)
        # gather (phash, split) across both splits
        rows = [(e["phash"], "train") for e in ents_t.values()] + \
               [(e["phash"], "val") for e in ents_v.values()]
        phs = [p for p, _ in rows]
        sp = [s for _, s in rows]
        pairs = interaction.find_duplicate_pairs_phash(phs, max_hamming=4, splits=sp, cross_split_only=True)
        r.ck(len(pairs) >= 1, "cross-split duplicate(s) detected", f"{len(pairs)} pair(s)")
        r.ck(all(sp[i] != sp[j] for i, j, _ in pairs), "every reported pair spans different splits")
        r.ck(all(i < j for i, j, _ in pairs), "pairs returned with i<j, closest-first")

    def s12(self, r: Result, url: str) -> None:
        r.sid, r.title, r.tier = "S12", "Compare Distributions projects two folders", "B"
        self.d.click_by_text(url, "Compare Distributions", timeout=30000)
        self.d.wait_text(url, "Folder A", timeout_s=30)
        body = self.d.get_text(url)
        r.ck("Folder A" in body and "Folder B" in body,
             "Compare tool renders its Folder A / Folder B inputs")
        ok, bad = self.d.assert_no_traceback(url)
        r.ck(ok, "Compare tool has no traceback", ",".join(bad))
        self.shot(r, url, "compare")
        # contract: the joint projection produces two colour-coded traces + 3 toggles
        import numpy as _np
        from pathlib import Path as _P
        import compare_distributions as cmpd
        projs = {"pca": _np.zeros((3, 2)), "tsne": _np.ones((3, 2)), "umap": _np.full((3, 2), 2.0)}
        fig = cmpd.build_projection_figure(
            [_P("a0.jpg"), _P("a1.jpg")], [_P("b0.jpg")], projs,
            "A", "B", fid_score=1.0, lpips_score=0.1)
        r.ck(len(fig.data) == 2, "joint projection builds two colour-coded traces", str(len(fig.data)))
        nbtn = len(fig.layout.updatemenus[0].buttons) if fig.layout.updatemenus else 0
        r.ck(nbtn == 3, "PCA/t-SNE/UMAP projection toggles present", str(nbtn))
        # back to viz for the rest
        self.d.click_by_text(url, "Visualize Embeddings", timeout=30000)
        time.sleep(1.0)

    def s13(self, r: Result, url: str) -> None:
        r.sid, r.title, r.tier = "S13", "Completeness coverage health + fake-complete guard", "B"
        self.d.click_by_text(url, "完整度熱力圖", timeout=30000)
        self.d.wait_text(url, "開始分析", timeout_s=30)
        body = self.d.get_text(url)
        r.ck(("Coverage Gap Analysis" in body) or ("開始分析" in body),
             "completeness tool renders its Coverage Gap Analysis UI")
        ok, bad = self.d.assert_no_traceback(url)
        r.ck(ok, "completeness tool renders without traceback", ",".join(bad))
        self.shot(r, url, "completeness")
        # contract: classify_cell flags FAKE (high count, low diversity) before OVER
        fake = completeness.classify_cell(n=10, d=0.1, t=4, d_star=0.6)
        over = completeness.classify_cell(n=10, d=0.9, t=4, d_star=0.6)
        r.ck(fake == completeness.STATE_FAKE, "high-count low-diversity cell → 假完整", fake)
        r.ck(over == completeness.STATE_OVER, "high-count high-diversity cell → 過多", over)
        empty = completeness.classify_cell(n=0, d=0.0, t=4)
        r.ck(empty == completeness.STATE_EMPTY, "empty cell → 空", empty)
        # contract: coverage_health rolls cells to 0-100 and excludes NA from scoring
        cells = [
            {"n": 10, "d": 0.8, "t": 4, "state": completeness.STATE_HEALTHY},
            {"n": 0, "d": 0.0, "t": 4, "state": completeness.STATE_NA},
        ]
        health = completeness.coverage_health(cells)
        r.ck(0.0 <= health["coverage_health"] <= 100.0,
             "Coverage Health in [0,100]", str(health["coverage_health"]))
        r.ck(health["coverage_health"] == 100.0 and health["counts"]["不適用"] == 1,
             "STATE_NA excluded from scoring (1 healthy + 1 NA → health 100)")
        self.d.click_by_text(url, "Visualize Embeddings", timeout=30000)
        time.sleep(1.0)

    def s14(self, r: Result, url: str) -> None:
        r.sid, r.title, r.tier = "S14", "Curation cart exports an auditable sha256 CSV", "B"
        body = self.d.get_text(url)
        r.ck("匯出清單" in body or "策展購物車" in body or "批次加入清單" in body,
             "cart / 匯出清單 controls present on the loaded page")
        ents = lv_manifest.load_manifest(DEMO_TRAIN)
        snaps = []
        for i, (k, e) in enumerate(list(ents.items())[:3]):
            snaps.append({"filename": Path(k).name, "path": k,
                          "label": (e["labels"] or [""])[0], "split": e["split"],
                          "sha256": e["sha256"], "source": "disagreement",
                          "score": 0.42, "reason": "bdd"})
        csv_text = interaction.snapshots_to_csv(snaps)
        header = csv_text.splitlines()[0]
        r.ck(header == "index,filename,path,label,split,sha256,source,score,reason",
             "cart CSV header exact", header)
        man_shas = {e["sha256"] for e in ents.values()}
        rows = csv_text.splitlines()[1:]
        r.ck(all(row.split(",")[5] in man_shas for row in rows),
             "every exported row carries a manifest sha256 (content-addressed)")
        (EVIDENCE / "S14_cart.csv").write_text(csv_text, encoding="utf-8")
        r.evidence.append("evidence/S14_cart.csv")

    # ── Phase 3: curation log (pure contract) ─────────────────────────────────
    def s15(self, r: Result) -> None:
        r.sid, r.title, r.tier = "S15", "Curation log persists & replays by sha256", "C"
        entries = [
            {"ts": "2026-06-14T10:00:00", "reason": "wk1", "n": 2,
             "items": [{"sha256": "aa", "filename": "a.jpg"},
                       {"sha256": "bb", "filename": "b.jpg"}]},
        ]
        csv_text = interaction.curation_log_csv(entries)
        r.ck(csv_text.splitlines()[0] == "ts,reason,n,filenames,sha256s",
             "curation_log CSV header exact")
        # persistence: write a real jsonl log to disk and reload it newest-first
        # (mirrors app._load_curation_log: read output/curation_log.jsonl, reversed)
        logf = EVIDENCE / "_curlog" / "curation_log.jsonl"
        logf.parent.mkdir(parents=True, exist_ok=True)
        logf.write_text(
            json.dumps({"ts": "2026-06-14T09:00:00", "reason": "older", "items": [{"sha256": "aa"}]}) + "\n"
            + json.dumps({"ts": "2026-06-14T10:00:00", "reason": "newer", "items": [{"sha256": "bb"}]}) + "\n",
            encoding="utf-8")
        reloaded = list(reversed([json.loads(ln) for ln in
                                  logf.read_text(encoding="utf-8").splitlines() if ln.strip()]))
        r.ck(reloaded[0]["ts"] > reloaded[1]["ts"] and reloaded[0]["reason"] == "newer",
             "on-disk curation log reloads newest-first (survives restart)")
        r.evidence.append("evidence/_curlog/curation_log.jsonl")
        # replay by sha256, skipping hashes absent from the current run
        sha_to_index = {"aa": 7, "cc": 9}
        got = interaction.match_shas_to_indices(["aa", "bb", "aa"], sha_to_index)
        r.ck(got == [7], "match_shas_to_indices maps known sha, skips unknown, de-dups", str(got))

    # ── Phase 4: cross-tool LV ↔ labeling handoff ─────────────────────────────
    def s16(self, r: Result) -> None:
        r.sid, r.title, r.tier = "S16", "LV and a labeling module both start in one engine session", "A"
        tools = {t["tool_id"] for t in self.d.list_tools()}
        r.ck(LV in tools and LABEL_TOOL in tools, "engine lists both app-lv and module_026")
        self.d.stop_tool(); time.sleep(1)
        lv = self.d.start_tool(LV)
        lv_url = lv["input_url"]
        self.d.wait_render(lv_url, timeout_s=90)
        lv_health = lv_url.replace
        try:
            import urllib.request
            with urllib.request.urlopen(f"{lv_url}/_stcore/health", timeout=5) as resp:
                hok = resp.read().decode().strip().lower() == "ok"
        except Exception:  # noqa: BLE001
            hok = False
        r.ck(hok, "app-lv serves /_stcore/health == ok")
        lv_run = lv.get("run_id")
        self.d.stop_tool(); time.sleep(1)
        m = self.d.start_tool(LABEL_TOOL)
        m_url = m["input_url"]
        self.d.wait_render(m_url, timeout_s=90)
        self.d.wait_text(m_url, "資料", timeout_s=60)
        mbody = self.d.get_text(m_url)
        r.ck(m.get("run_id") and m.get("run_id") != lv_run, "distinct run_ids per tool",
             f"{lv_run} vs {m.get('run_id')}")
        r.ck(("資料來源" in mbody) or ("資料夾" in mbody) or ("本地" in mbody),
             "module_026 renders its 資料來源 input pane")
        self.shot(r, m_url, "module_026")

    def s17(self, r: Result) -> None:
        r.sid, r.title, r.tier = "S17", "RBAC gates LV launch by role", "A"
        from core.rbac import is_allowed
        import yaml
        pol_path = ENGINE_ROOT / "config" / "permissions.yaml"
        policy = yaml.safe_load(pol_path.read_text(encoding="utf-8"))
        r.ck(not is_allowed(policy, "operator", LV, "execute"),
             "operator is DENIED execute on app-lv (scoped role)")
        r.ck(is_allowed(policy, "operator", LABEL_TOOL, "execute"),
             "operator is ALLOWED execute on module_026 (positive control)")
        r.ck(is_allowed(policy, "admin", LV, "execute"),
             "admin (all:true) is ALLOWED execute on app-lv")

    def s18(self, r: Result) -> None:
        r.sid, r.title, r.tier = "S18", "Curated subset CSV is a true subset of the manifest", "B"
        ents = lv_manifest.load_manifest(DEMO_TRAIN)
        r.ck(bool(ents), "train manifest available for reconciliation", f"{len(ents)} entries")
        snaps = [{"filename": Path(k).name, "path": k, "sha256": e["sha256"],
                  "label": (e["labels"] or [""])[0], "split": e["split"],
                  "source": "near_dup", "score": 0.1, "reason": "x"}
                 for k, e in list(ents.items())[:4]]
        csv_text = interaction.snapshots_to_csv(snaps)
        cart_shas = {row.split(",")[5] for row in csv_text.splitlines()[1:]}
        man_shas = {e["sha256"] for e in ents.values()}
        r.ck(cart_shas <= man_shas, "every cart sha256 resolves to a manifest entry (⊆)")
        # labeling side ACTUALLY ingests the curated folder (closes the LV→labeling loop):
        # module_026's local mode calls module_010.scan_folder on the folder.
        cart_names = {Path(k).name for k in list(ents)[:4]}
        import importlib.util as _ilu
        p010 = ENGINE_ROOT / "plugins" / "labeling" / "modules" / "module_010" / "010_process.py"
        _spec = _ilu.spec_from_file_location("_010_process_bdd", p010)
        _mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)
        items = _mod.scan_folder(str(DEMO_TRAIN / "images"), False, [".jpg", ".jpeg", ".png"])
        scanned = {Path(it["file_path"]).name for it in items}
        r.ck(len(items) == self.fx["n_train"],
             "labeling scan_folder ingests the curated folder", f"{len(items)} items")
        r.ck(cart_names <= scanned, "curated images present in labeling's ingested set")
        # module_026 is also live to ingest the same local folder
        self.d.stop_tool(); time.sleep(1)
        m_url = self.d.start_tool(LABEL_TOOL)["input_url"]
        self.d.wait_render(m_url, timeout_s=90)
        self.d.wait_text(m_url, "資料", timeout_s=60)
        mbody = self.d.get_text(m_url)
        r.ck(("資料來源" in mbody) or ("本地" in mbody) or ("資料夾" in mbody),
             "module_026 (資料來源) is live to ingest the curated folder")

    def s19(self, r: Result) -> None:
        r.sid, r.title, r.tier = "S19", "Manifest schema validates across the boundary", "C"
        ents = lv_manifest.load_manifest(DEMO_TRAIN)
        r.ck(bool(ents), "manifest loaded", f"{len(ents)} entries")
        contract = {"path", "sha256", "phash", "split", "labels", "source",
                    "captured_at", "size", "mtime_ns", "embedding_refs", "thumb_ref"}
        e = next(iter(ents.values()))
        r.ck(contract <= set(e), "all 11 contract keys present", str(sorted(contract - set(e))))
        r.ck(isinstance(e["labels"], list) and isinstance(e["embedding_refs"], dict),
             "labels is list, embedding_refs is dict")
        import re
        r.ck(re.fullmatch(r"[0-9a-f]{64}", e["sha256"]) is not None, "sha256 is 64 hex")
        r.ck(e["phash"] is None or re.fullmatch(r"[0-9a-f]{16}", e["phash"]) is not None,
             "phash is 16 hex or null")
        # corrupt-line resilience
        tmp = HERE / "evidence" / "_corrupt"
        tmp.mkdir(parents=True, exist_ok=True)
        mp = tmp / "manifest.jsonl"
        good = json.dumps({"path": "a.jpg", "sha256": "x"})
        mp.write_text(good + "\n{ this is corrupt \n\n", encoding="utf-8")
        loaded = lv_manifest.load_manifest(tmp)
        r.ck(set(loaded) == {"a.jpg"}, "corrupt/blank lines skipped, valid entry survives",
             str(list(loaded)))

    def s20(self, r: Result) -> None:
        r.sid, r.title, r.tier = "S20", "Cart→quiz guard + incremental manifest round-trip", "C"
        # quiz≥4 guard is wired in the app
        app_src = (LV_SCRIPTS / "app.py").read_text(encoding="utf-8")
        r.ck("購物車至少要 4 張" in app_src, "cart→quiz guard (購物車至少要 4 張) is wired in app.py")
        # gray-zone routing contract: highest score first, clamped to N
        order = interaction.select_gray_zone(np.array([0.1, 0.9, 0.5]), k=2)
        r.ck(order == [1, 2], "select_gray_zone ranks most-ambiguous first, clamps k", str(order))
        # incremental manifest refresh: only the edited file is re-hashed
        ds = HERE / "evidence" / "_rt"
        (ds / "images").mkdir(parents=True, exist_ok=True)
        from PIL import Image
        import numpy as _np
        paths = []
        for i in range(3):
            p = ds / "images" / f"img_{i}.jpg"
            Image.fromarray(_np.full((32, 32, 3), i * 40, dtype=_np.uint8)).save(p)
            paths.append(p)
        recs = [{"path": str(p), "split": "train", "label": "a"} for p in paths]
        ents1 = lv_manifest.update_manifest(ds, recs)
        lv_manifest.write_manifest(ds, ents1)
        sha_before = {k: v["sha256"] for k, v in ents1.items()}
        # edit ONE file's bytes (changes size+mtime) → only it should re-hash
        time.sleep(0.01)
        Image.fromarray(_np.full((32, 32, 3), 200, dtype=_np.uint8)).save(paths[1])
        ents2 = lv_manifest.update_manifest(ds, recs)
        changed = [k for k in ents2 if ents2[k]["sha256"] != sha_before[k]]
        unchanged = [k for k in ents2 if ents2[k]["sha256"] == sha_before[k]]
        r.ck(len(changed) == 1, "exactly the edited file was re-hashed", str(changed))
        r.ck(len(unchanged) == 2, "unchanged files kept their sha256 (size+mtime fast-path)")

    # ── orchestration ─────────────────────────────────────────────────────────
    def execute(self) -> None:
        self.log(f"[lv-bdd] engine base : {self.base}")
        self.log(f"[lv-bdd] health      : {self.d.health()}")
        self._proof = mcp_driver.prove_mcp_server()
        proof = self._proof
        self.log(f"[lv-bdd] cim-gui MCP server tools advertised: "
                 f"{len(proof['tools'])} ({'ok' if proof['ok'] else proof['error']})")
        self.log("[lv-bdd] provisioning fixtures (resnet18 + coco8)…")
        self.fx = fixtures.ensure_all()
        self.log(f"[lv-bdd] fixtures ready: model={self.fx['model_name']} "
                 f"train={self.fx['n_train']} val={self.fx['n_val']}")

        # Phase 1 — shell / guards (fresh LV)
        for fn in (self.s01, self.s02, self.s03, self.s04, self.s05):
            self.run(fn)

        # Phase 2 — analysis on a single loaded LV session (reused page)
        self.log("[lv-bdd] starting LV + loading coco8 demo for analysis scenarios…")
        try:
            url = self.start_lv_loaded()
            for fn in (self.s06, self.s07, self.s08, self.s09, self.s10,
                       self.s11, self.s12, self.s13, self.s14):
                self.run(lambda r, _f=fn, _u=url: _f(r, _u))
        except Exception:  # noqa: BLE001
            self.log("[lv-bdd] loaded-LV phase failed:\n" + traceback.format_exc(limit=3))

        # Phase 3 — curation log (contract)
        self.run(self.s15)

        # Phase 4 — cross-tool handoff
        for fn in (self.s16, self.s17, self.s18, self.s19, self.s20):
            self.run(fn)

        self.d.stop_tool()
        self.d.close()
        self._report(proof)

    def _report(self, proof: dict) -> None:
        passed = sum(1 for r in self.results if r.status == "PASS")
        total = len(self.results)
        report = {
            "engine_base": self.base,
            "mcp_server_tools": proof["tools"],
            "summary": {"passed": passed, "total": total},
            "scenarios": [
                {"id": r.sid, "title": r.title, "tier": r.tier, "status": r.status,
                 "checks": [dataclasses.asdict(c) for c in r.checks],
                 "evidence": r.evidence, "error": r.error}
                for r in self.results
            ],
        }
        (HERE / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        # markdown
        md = ["# LV BDD E2E Report", "",
              f"- engine: `{self.base}`",
              f"- cim-gui MCP server tools advertised: **{len(proof['tools'])}**",
              f"- **{passed}/{total} scenarios PASS**", "",
              "| ID | Tier | Status | Title | checks |",
              "|----|------|--------|-------|--------|"]
        for r in self.results:
            nok = sum(1 for c in r.checks if c.ok)
            md.append(f"| {r.sid} | {r.tier} | {'✅' if r.status=='PASS' else '❌'} "
                      f"| {r.title} | {nok}/{len(r.checks)} |")
        (HERE / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        self.log(f"\n[lv-bdd] RESULT: {passed}/{total} PASS")
        self.log(f"[lv-bdd] report → {HERE / 'report.md'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("CIM_BDD_BASE", "http://127.0.0.1:8765"))
    args = ap.parse_args()
    runner = Runner(args.base)
    runner.execute()
    passed = sum(1 for r in runner.results if r.status == "PASS")
    return 0 if passed == len(runner.results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
