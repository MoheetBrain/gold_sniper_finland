"""
11b — Top-k capture metrics + the BEAT-THE-BASELINE gate.

Evaluates the model's out-of-fold scores against the distance-to-fault baseline
(the bar to beat), random (the floor), and distance-to-known-deposit (a leaky
reference ceiling). Metrics on the labelled positive/background set:
    - top 1% / 5% / 10% cell-count capture of positive cells (the metric that matters)
    - ROC-AUC (reported with a small-sample caveat)

HARD GATE
    model "beats baseline" only if its top-5% capture AND ROC-AUC both exceed
    distance-to-fault. If not -> verdict FAIL and target ranking must not proceed on
    the model score (the pipeline falls back to the baseline / flags insufficient data).
    The ">80% in top 5%" target is reported as a strong-pass benchmark, not a hard fail.

OUTPUTS
    data/outputs/STEP2_VALIDATION_BASELINE_REPORT.md
    data/outputs/STEP2_VALIDATION.json
    data/outputs/topk_capture_curves.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("11b_metrics")
KS = [1, 5, 10]


from _evaluation import topk_capture, capture_tie_bounds


def capture_curve(scores, y, grid_pcts):
    return [topk_capture(scores, y, p) for p in grid_pcts]


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs")
    size = cfg["step2"]["primary_grid"].split("_")[-1].replace(".gpkg", "")

    mp = processed / f"model_scores_{size}.parquet"
    bp = processed / f"baseline_scores_{size}.parquet"
    lp = processed / f"cell_labels_{size}.parquet"
    rp = processed / f"cell_role_{size}.parquet"
    if not all(p.exists() for p in [mp, bp, lp, rp]):
        log.error("Missing inputs for metrics — run 06-11 first.")
        return 2

    model = pd.read_parquet(mp)
    base = pd.read_parquet(bp)
    labels = pd.read_parquet(lp)
    roles = pd.read_parquet(rp)
    df = (roles.merge(labels, on="cell_id").merge(base, on="cell_id")
          .merge(model, on="cell_id"))

    # Evaluate on labelled positive/background cells with a valid OOF model score.
    ev = df[df["role"].isin(["positive", "background"])].copy()
    ev_model = ev[ev["in_cv"] & ev["model_score"].notna()].copy()
    y = (ev_model["role"] == "positive").astype(int).values
    n_pos = int(y.sum())
    if len(ev_model) != len(ev) or len(np.unique(y)) != 2:
        log.error("Incomplete OOF coverage or missing class; refusing misleading evaluation")
        return 2

    methods = {
        "model_xgb_oof": ev_model["model_score"].values,
        "baseline_distfault": ev_model["score_distfault"].values,
        "baseline_random": ev_model["score_random"].values,
        "ref_distdeposit_leaky": ev_model["score_distdeposit"].values,
    }

    result = {"grid": size, "n_eval_cells": int(len(ev_model)), "n_positives": n_pos,
              "capture": {}, "roc_auc": {}, "tie_bounds": {}}
    from sklearn.metrics import roc_auc_score
    for name, sc in methods.items():
        result["tie_bounds"][name] = {f"top{k}pct": capture_tie_bounds(sc,y,k) for k in KS}
        result["capture"][name] = {f"top{k}pct": round(topk_capture(sc, y, k), 3) for k in KS}
        try:
            result["roc_auc"][name] = round(float(roc_auc_score(y, sc)), 3) if n_pos > 0 else None
        except Exception:  # noqa: BLE001
            result["roc_auc"][name] = None

    # Beat-baseline gate.
    m5 = result["capture"]["model_xgb_oof"]["top5pct"]
    b5 = result["capture"]["baseline_distfault"]["top5pct"]
    ma = result["roc_auc"]["model_xgb_oof"] or 0
    ba = result["roc_auc"]["baseline_distfault"] or 0
    beats = (m5 > b5) and (ma > ba)
    result["model_beats_distfault"] = bool(beats)
    result["enough_data"] = bool(n_pos >= 4 and len(methods["model_xgb_oof"]) > 0
                                 and not np.isnan(methods["model_xgb_oof"]).all())
    if not result["enough_data"]:
        result["verdict"] = "NOT ENOUGH DATA"
    else:
        result["verdict"] = "PASS (model beats distance-to-fault)" if beats else \
                            "FAIL (model does NOT beat distance-to-fault)"
    result["strong_pass_benchmark_top5_ge_0.8"] = bool(m5 >= 0.8)
    result["model_beats_distfault_topk"] = {
        f"top{k}pct": bool(result["capture"]["model_xgb_oof"][f"top{k}pct"] >
                           result["capture"]["baseline_distfault"][f"top{k}pct"])
        for k in KS
    }

    # Honesty flags requested for Step 2.2A.
    model_meta_path = outputs / "STEP2_MODEL_FEATURE_IMPORTANCE.json"
    model_meta = {}
    if model_meta_path.exists():
        try:
            model_meta = json.loads(model_meta_path.read_text(encoding="utf-8")).get(size, {})
        except Exception:  # noqa: BLE001
            model_meta = {}
    result["single_signal_hallucination"] = bool(
        model_meta.get("single_signal_hallucination", False)
    )
    result["single_signal_top_feature"] = model_meta.get("top_feature")
    result["single_signal_top_feature_importance_fraction"] = model_meta.get(
        "top_feature_importance_fraction"
    )

    mag_low_confidence = False
    mag_path = processed / f"magnetics_features_{size}.parquet"
    if mag_path.exists():
        try:
            mag = pd.read_parquet(mag_path)
            if "magnetics_status" in mag:
                mag_low_confidence = mag["magnetics_status"].astype(str).str.contains(
                    "visual|low|unreadable", case=False, regex=True
                ).any()
            if "mag_visual_proxy_low_confidence" in mag and mag["mag_visual_proxy_low_confidence"].notna().any():
                mag_low_confidence = True
        except Exception:  # noqa: BLE001
            mag_low_confidence = True
    result["magnetics_low_confidence"] = bool(mag_low_confidence)

    (outputs / "STEP2_VALIDATION.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    # --- Capture curves plot ---
    pcts = np.linspace(0.5, 30, 60)
    fig, ax = plt.subplots(figsize=(8, 5))
    styles = {"model_xgb_oof": "-", "baseline_distfault": "--",
              "baseline_random": ":", "ref_distdeposit_leaky": "-."}
    for name, sc in methods.items():
        ax.plot(pcts, [topk_capture(sc, y, p) for p in pcts], styles.get(name, "-"), label=name)
    ax.axhline(0.8, color="grey", lw=0.6, ls=":")
    ax.set_xlabel("top % of ranked cells"); ax.set_ylabel("fraction of positives captured")
    ax.set_title(f"Top-k capture ({size}, {n_pos} positives) — OOF spatial CV")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(outputs / "topk_capture_curves.png", dpi=130)
    plt.close(fig)

    # --- Markdown report ---
    L = ["# Step 2 Validation & Baselines Report", "",
         f"Spatial-block out-of-fold evaluation on the **{size}** grid "
         f"({n_pos} positives, {len(ev_model)} labelled cells).", "",
         f"## Verdict: **{result['verdict']}**", "",
         f"- Model beats distance-to-fault: **{result['model_beats_distfault']}**",
         f"- Model beats distance-to-fault by top-k: **{result['model_beats_distfault_topk']}**",
         f"- Strong-pass benchmark (≥80% positives in top 5%): "
         f"**{result['strong_pass_benchmark_top5_ge_0.8']}** "
         f"(benchmark only, not a hard fail)", "",
         "## Honesty flags", "",
         f"- `single_signal_hallucination`: **{result['single_signal_hallucination']}** "
         f"(top feature: {result['single_signal_top_feature']}, fraction: "
         f"{result['single_signal_top_feature_importance_fraction']})",
         f"- `magnetics_low_confidence`: **{result['magnetics_low_confidence']}**",
         "",
         "## Top-k capture (fraction of positives)", "",
         "| method | top 1% | top 5% | top 10% | ROC-AUC |",
         "|--------|--------|--------|---------|---------|"]
    for name in methods:
        c = result["capture"][name]
        L.append(f"| {name} | {c['top1pct']} | {c['top5pct']} | {c['top10pct']} | "
                 f"{result['roc_auc'][name]} |")
    L += ["", "## How to read this",
          "- **baseline_distfault** is the bar to beat (orogenic gold is fault-hosted).",
          "- **baseline_random** is the floor.",
          "- **ref_distdeposit_leaky** is a circular reference (distance to the very",
          "  deposits we're trying to find) — expect it high; it is NOT an honest model.",
          "- With ~8 positives, all numbers are high-variance. Treat as indicative.", "",
          "## Consequence",
          ("- Model is **not** trusted for ranking; candidates fall back to baseline /"
           " geology scores and are flagged. " if not beats else
           "- Model may inform ranking, but still requires multi-layer support. "),
          "- Either way, NO output is a 'gold target' — only modelling candidates.", ""]
    (outputs / "STEP2_VALIDATION_BASELINE_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Verdict: %s | model top5=%.2f vs distfault top5=%.2f | AUC m=%.2f b=%.2f",
             result["verdict"], m5, b5, ma, ba)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
