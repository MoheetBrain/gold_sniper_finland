#!/usr/bin/env python3
"""
run_monte_carlo_v2.py — FULL-DATA v2 Monte Carlo with REAL till + NUMERIC magnetics.

Differences vs v1 (run_monte_carlo_top10.py):
  - geochemistry group now uses REAL till_evidence (Au+Te, regional-ECDF, up-ice corrected)
    instead of the v1 0-default till_*_clr.  (As/Sb/Bi/W absent -> pathfinder_incomplete penalty.)
  - magnetics group now uses NUMERIC 1VD (mag_1vd_score, magnetic_break_score) instead of
    the v1 hard-coded 0.5.  magnetic_confidence = high.
  - both groups now count as PRESENT (no missing-group penalty for them).
  - group weights rebalanced because these two layers are now genuine evidence.
Perturbs: structural decay scales, group weights, prior, LR, ice/geochem uncertainty (till_evidence noise),
          pathfinder-incompleteness factor.
Runs seeds 42, 7, 99 and reports per-seed + seed-averaged posteriors and package probabilities.
"""
import sys, math, json, numpy as np, pandas as pd
from pathlib import Path
ROOT = Path("/Users/mk/AL_THAHAB/gold_sniper"); sys.path.insert(0, str(ROOT/"scripts"))
import run_monte_carlo_top10 as v1   # reuse math + loaders

TOP10=["g2k_01385","g2k_00779","g2k_00780","g2k_02275","g2k_01922","g2k_02274","g2k_01993","g2k_01850","g2k_01386","g2k_01314"]
OUT = ROOT/"data/outputs/full_model_v2"; OUT.mkdir(parents=True, exist_ok=True)

# ---- v2 config: rebalanced because till + magnetics are now real evidence ----
V2W = {"structure":0.28,"gravity":0.20,"lithology_rheology":0.14,"geochemistry":0.22,"magnetics":0.16}

def load_v2():
    df, missing = v1.load_and_map_cells(ROOT/"data/outputs/review_candidates_audited.csv", multi_layer_only=True)
    df = v1.add_map_numbers(df, ROOT/"data/outputs/clgb_grid_2km_number_lookup.csv")
    df = v1.add_town_distances(df, ROOT/"data/outputs/clgb_grid_2km_number_lookup.csv")
    till = pd.read_parquet(ROOT/"data/processed/till_glacial_v2_features.parquet")[["cell_id","till_evidence","backproj_supported","ice_flow_confidence"]]
    mag  = pd.read_parquet(ROOT/"data/processed/magnetics_v2_features.parquet")[["cell_id","mag_1vd_score","magnetic_break_score","magnetic_confidence"]]
    # drop v1 placeholder magnetics/geochem columns to avoid merge collisions
    df = df.drop(columns=[c for c in ["mag_1vd","mag_low_in_high_proxy","magnetic_break_score"] if c in df.columns])
    df = df.merge(till, on="cell_id", how="left").merge(mag, on="cell_id", how="left")
    df["till_evidence"] = df["till_evidence"].fillna(0.3)         # cells with no till nearby -> weak, not zero
    df["mag_1vd_score"] = df["mag_1vd_score"].fillna(0.0)
    df["magnetic_break_score"] = df["magnetic_break_score"].fillna(0.0)
    return df

def iterate(rng, df, cfg):
    n=len(df)
    gw  = v1.sample_dirichlet(rng, V2W, cfg.group_weight_concentration)
    sw  = v1.sample_dirichlet(rng, cfg.structure_sub_weights, cfg.structure_sub_concentration)
    shear=v1.clipped_normal(rng,cfg.major_shear_decay_mean_m,cfg.major_shear_decay_sd_m,cfg.major_shear_decay_min_m,cfg.major_shear_decay_max_m)
    int_=v1.clipped_normal(rng,cfg.fault_int_decay_mean_m,cfg.fault_int_decay_sd_m,cfg.fault_int_decay_min_m,cfg.fault_int_decay_max_m)
    lith=v1.clipped_normal(rng,cfg.lith_contact_decay_mean_m,cfg.lith_contact_decay_sd_m,cfg.lith_contact_decay_min_m,cfg.lith_contact_decay_max_m)
    ev=v1.clipped_normal(rng,cfg.evidence_threshold_mean,cfg.evidence_threshold_sd,cfg.evidence_threshold_min,cfg.evidence_threshold_max)
    # structure
    s_shear=v1.distance_decay(df['dist_major_shear_m'].values,shear)
    s_int=v1.robust_minmax(df['fault_intersection_density'].values)
    s_lith=v1.distance_decay(df['dist_key_lithological_contact_m'].values,lith)
    s_splay=v1.distance_decay(df['dist_splay_or_jog_m'].values,int_)
    structure=np.clip(sw['major_shear_distance']*s_shear+sw['fault_intersection_density']*s_int+sw['lithological_contact']*s_lith+sw['splay_jog_distance']*s_splay,0,1)
    # gravity (gradient is worm proxy)
    gravity=np.clip(v1.robust_minmax(df['gravity_gradient'].values),0,1)
    # lithology
    if 'lithology_signal' in df.columns:
        lith_b=df['lithology_signal'].astype(float).values
        lithology=np.clip(lith_b*0.8+0.1+rng.normal(0,0.05,n),0,1)
    else:
        lithology=np.full(n,0.5)
    # geochemistry = REAL till evidence + uncertainty + pathfinder-incompleteness factor
    pf_incomplete=rng.uniform(0.80,0.95)   # As/Sb/Bi/W absent -> classic pathfinder halo missing
    geochem=np.clip(df['till_evidence'].values*pf_incomplete + rng.normal(0,0.07,n),0,1)
    # magnetics = NUMERIC 1VD + break, perturbed
    magw=rng.uniform(0.4,0.6)
    magnetics=np.clip(magw*df['mag_1vd_score'].values+(1-magw)*df['magnetic_break_score'].values+rng.normal(0,0.05,n),0,1)
    groups={'structure':structure,'gravity':gravity,'lithology_rheology':lithology,'geochemistry':geochem,'magnetics':magnetics}
    # weighted geometric mean
    ls=np.zeros(n);wt=0.0
    for k,gs in groups.items():
        ls+=gw[k]*np.log(np.clip(gs,cfg.eps,1.0)); wt+=gw[k]
    combined=np.exp(ls/max(wt,cfg.eps))
    # penalties
    ecount=sum((gs>=ev).astype(int) for gs in groups.values())
    combined=np.where(ecount<2,combined*cfg.single_signal_penalty,combined)
    has_int=df['fault_intersection_density'].values>0
    near=df['dist_major_shear_m'].values<1000
    combined=np.where(has_int,combined*cfg.intersection_bonus,np.where(near,combined*cfg.no_intersection_penalty,combined))
    # NO missing-group penalty now for geochem/magnetics (present). keep lithology proxy only.
    if 'distance_to_nearest_town_km' in df.columns:
        combined*=1.0+cfg.accessibility_weight*np.clip(1.0-df['distance_to_nearest_town_km'].values/50.0,0,1)
    combined=np.clip(combined,0,1)
    prior=float(np.clip(rng.lognormal(math.log(cfg.prior_2km),cfg.prior_sd_fraction),1e-6,0.25))
    lrmax=float(np.clip(rng.lognormal(math.log(cfg.lr_max),cfg.lr_max_sigma_log),5,250))
    post=v1.posterior_from_score(combined,prior,cfg.lr_min,lrmax)
    return combined,post,groups

def run_seed(df,seed,n_iter=20000):
    cfg=v1.MCConfig(n_iter=n_iter,seed=seed); rng=np.random.default_rng(seed); n=len(df)
    ssum=np.zeros(n);psum=np.zeros(n);psq=np.zeros(n);gsum={g:np.zeros(n) for g in V2W}
    topc={k:np.zeros(n,int) for k in (1,3,5,10)}
    for it in range(n_iter):
        sc,po,gr=iterate(rng,df,cfg)
        ssum+=sc;psum+=po;psq+=po**2
        for g in V2W: gsum[g]+=gr[g]
        for k in topc:
            idx=np.argpartition(-sc,min(k,n)-1)[:min(k,n)]; topc[k][idx]+=1
    out=pd.DataFrame({"cell_id":df.cell_id.values,
        "mc_score_mean":ssum/n_iter,"posterior_mean":psum/n_iter,
        "posterior_sd":np.sqrt(np.maximum(psq/n_iter-(psum/n_iter)**2,0))})
    for k in topc: out[f"top_{k}_freq"]=topc[k]/n_iter
    for g in V2W: out[f"{g}_mean"]=gsum[g]/n_iter
    return out.sort_values("mc_score_mean",ascending=False).reset_index(drop=True)

if __name__=="__main__":
    df=load_v2()
    print("v2 inputs (top-10):")
    print(df[df.cell_id.isin(TOP10)][["cell_id","till_evidence","mag_1vd_score","magnetic_break_score","dist_major_shear_m","gravity_gradient"]].round(3).to_string(index=False))
    seeds=[42,7,99]; res={}
    for s in seeds:
        r=run_seed(df,s); res[s]=r; r.to_csv(OUT/f"monte_carlo_v2_seed{s}.csv",index=False)
        print(f"[seed {s}] done")
    # seed-averaged posterior
    base=res[42][["cell_id"]].copy()
    P=pd.concat([res[s].set_index("cell_id")["posterior_mean"].rename(s) for s in seeds],axis=1)
    base["posterior_v2_mean"]=P.mean(axis=1).reindex(base.cell_id).values
    base["posterior_v2_seed_sd"]=P.std(axis=1).reindex(base.cell_id).values
    base=base.merge(res[42][["cell_id","top_5_freq","top_10_freq","structure_mean","gravity_mean","lithology_rheology_mean","geochemistry_mean","magnetics_mean"]],on="cell_id",how="left")
    base=base.sort_values("posterior_v2_mean",ascending=False).reset_index(drop=True)
    base.insert(0,"v2_rank",range(1,len(base)+1))
    base.to_csv(OUT/"monte_carlo_v2_seedavg.csv",index=False)
    json.dump({"group_weights_v2":V2W,"seeds":seeds,"n_iter":20000},open(OUT/"monte_carlo_v2_config.json","w"),indent=2)
    print("\n=== v2 SEED-AVERAGED posteriors (top-10 cells) ===")
    print(base[base.cell_id.isin(TOP10)][["v2_rank","cell_id","posterior_v2_mean","posterior_v2_seed_sd","top_5_freq","structure_mean","gravity_mean","geochemistry_mean","magnetics_mean"]].round(4).to_string(index=False))
