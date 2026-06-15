#!/usr/bin/env python3
"""
v2_03_capture_gate.py — HARD GATE: does the v2 full-data evidence model beat the
distance-to-fault baseline on top-k capture of the 8 known CLGB orogenic-gold cells?
Builds a deterministic v2 score for ALL eval cells from structure+gravity+lithology+till+magnetics,
then computes top-1/5/10% capture vs distance-to-fault and vs the v1 model.
"""
import numpy as np, pandas as pd, geopandas as gpd, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT=Path("/Users/mk/AL_THAHAB/gold_sniper")
V2W={"structure":0.28,"gravity":0.20,"lithology_rheology":0.14,"geochemistry":0.22,"magnetics":0.16}

g=gpd.read_file(ROOT/"data/outputs/geology_ranked_modelling_candidates.gpkg")
keep=["cell_id","structural_score","lithology_score","geophysics_score","distance_to_major_shear","model_score","baseline_score"]
d=pd.DataFrame(g[keep])
till=pd.read_parquet(ROOT/"data/processed/till_glacial_v2_features.parquet")[["cell_id","till_evidence"]]
mag =pd.read_parquet(ROOT/"data/processed/magnetics_v2_features.parquet")[["cell_id","mag_1vd_score","magnetic_break_score"]]
d=d.merge(till,on="cell_id",how="left").merge(mag,on="cell_id",how="left")

# labels
lab=pd.read_parquet(ROOT/"data/processed/cell_labels_2km.parquet")
labcol=[c for c in lab.columns if c.lower() in ("label","is_positive","positive","y","target")]
labcol=labcol[0] if labcol else [c for c in lab.columns if lab[c].dropna().isin([0,1]).all() and lab[c].sum()<50][0]
pos=set(lab.loc[lab[labcol]==1,"cell_id"]) if "cell_id" in lab.columns else set()
d["y"]=d.cell_id.isin(pos).astype(int)
print(f"label col='{labcol}'  positives in eval set: {d.y.sum()} / {len(d)}")

# build group 0-1 scores (fill neutral/weak for missing)
S=d.structural_score.fillna(d.structural_score.median()).clip(0,1).values
G=d.geophysics_score.fillna(d.geophysics_score.median()).clip(0,1).values
L=d.lithology_score.fillna(d.lithology_score.median()).clip(0,1).values
T=(d.till_evidence.fillna(0.3)*0.85).clip(0,1).values
M=(0.5*d.mag_1vd_score.fillna(0.0)+0.5*d.magnetic_break_score.fillna(0.0)).clip(0,1).values
eps=1e-6
def wgeo(parts):
    ls=np.zeros(len(d));wt=0
    for w,a in parts: ls+=w*np.log(np.clip(a,eps,1)); wt+=w
    return np.exp(ls/wt)
d["v2_score"]=wgeo([(V2W["structure"],S),(V2W["gravity"],G),(V2W["lithology_rheology"],L),(V2W["geochemistry"],T),(V2W["magnetics"],M)])
# v2 WITHOUT new data (structure+gravity+lithology only) for an apples-to-apples "did new data help"
d["v2_struct_grav_only"]=wgeo([(0.5,S),(0.3,G),(0.2,L)])
# baseline: distance-to-fault (closer=higher)
dd=d.distance_to_major_shear.fillna(d.distance_to_major_shear.max())
d["baseline_distfault"]=1.0/(1.0+dd/1000.0)

def capture(score):
    r=d.assign(s=score).sort_values("s",ascending=False)
    n=len(r); out={}
    for k in (1,5,10):
        topn=max(1,int(np.ceil(n*k/100)))
        out[k]=r.head(topn).y.sum()/max(d.y.sum(),1)
    return out
def auc(score):
    from sklearn.metrics import roc_auc_score
    try: return roc_auc_score(d.y, score)
    except: return float("nan")

print("\nTOP-K CAPTURE of 8 positives (fraction captured):")
print(f"{'model':28} {'top1%':>7} {'top5%':>7} {'top10%':>7} {'ROC-AUC':>8}")
rows={}
for name,sc in [("v2 FULL (struct+grav+lith+till+mag)",d.v2_score.values),
                ("v2 minus new data (str+grav+lith)",d.v2_struct_grav_only.values),
                ("baseline distance-to-fault",d.baseline_distfault.values),
                ("v1 model_score (gpkg)",d.model_score.fillna(0).values)]:
    c=capture(sc); a=auc(sc); rows[name]=(c,a)
    print(f"{name:28} {c[1]:>7.3f} {c[5]:>7.3f} {c[10]:>7.3f} {a:>8.3f}")

cf=rows["v2 FULL (struct+grav+lith+till+mag)"][0]; bf=rows["baseline distance-to-fault"][0]
beats={k: cf[k]>=bf[k] for k in (1,5,10)}
verdict = "PASS (v2 beats distance-to-fault on top-1% & top-5%)" if (beats[1] and beats[5]) else \
          ("WEAK PASS" if any(beats.values()) else "FAIL -> WAIT/KILL")
print(f"\nv2 beats baseline?  top1%={beats[1]} top5%={beats[5]} top10%={beats[10]}")
print("HARD GATE VERDICT:", verdict)
print(f"NOTE: only {d.y.sum()} positive labels -> capture moves in ~{1/ max(d.y.sum(),1):.0%} steps; statistically fragile.")

import json
out=ROOT/"data/outputs/full_model_v2"; out.mkdir(parents=True,exist_ok=True)
json.dump({"positives":int(d.y.sum()),"n_eval":int(len(d)),
           "capture":{k:{kk:float(vv) for kk,vv in v[0].items()} for k,v in rows.items()},
           "roc_auc":{k:float(v[1]) for k,v in rows.items()},
           "v2_beats_distfault":{str(k):bool(v) for k,v in beats.items()},
           "verdict":verdict}, open(out/"v2_capture_gate.json","w"), indent=2)
d[["cell_id","y","v2_score","baseline_distfault","v2_struct_grav_only"]].to_parquet(out/"v2_allcell_scores.parquet",index=False)
print("[saved] v2_capture_gate.json + v2_allcell_scores.parquet")
