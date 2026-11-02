"""Offline synthetic demonstration using the retained research implementations."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box,LineString
from sklearn.metrics import roc_auc_score,average_precision_score
from _common import import_script
from _evaluation import fit_grouped,topk_capture,capture_tie_bounds

SEED=42
FEATURES=['dist_major_shear','fault_intersection_density','dist_key_lithological_contact','gravity_gradient','till_au_clr']
LOCAL_CRS='+proj=aeqd +lat_0=0 +lon_0=0 +datum=WGS84 +units=m +no_defs'

def build_fixture(seed=SEED):
    rng=np.random.default_rng(seed)
    grid=import_script('01_make_aoi_grid.py').build_grid([0,0,60000,60000],2000,LOCAL_CRS)
    grid['cell_id']=[f'synthetic_{i:04d}' for i in range(len(grid))]
    grid=import_script('09_make_spatial_blocks.py').assign_blocks(grid,20000)
    lines=gpd.GeoDataFrame(geometry=[LineString([(0,4000),(60000,52000)]),
        LineString([(6000,60000),(50000,0)]),LineString([(0,33000),(60000,33000)])],crs=LOCAL_CRS)
    bed=gpd.GeoDataFrame(geometry=[box(0,0,24000,60000),box(24000,0,60000,60000)],crs=LOCAL_CRS)
    f=import_script('06_build_minimal_feature_stack.py').build_base_features(grid,lines,bed)
    # Artificial physical field, not sampled Finnish geophysics.
    f['gravity_gradient']=np.abs(np.sin(grid.centroid_x/9000)*np.cos(grid.centroid_y/13000))
    f['till_au_clr']=rng.normal(size=len(grid))
    f.loc[rng.random(len(grid))<.85,'till_au_clr']=np.nan
    propensity=np.exp(-f.dist_major_shear/5000)*(0.3+f.gravity_gradient)
    positive_indices=[]
    for _,idx in grid.groupby('spatial_block_id').groups.items():
        ii=np.array(list(idx));weights=propensity.iloc[ii].to_numpy()+.01
        positive_indices.append(int(rng.choice(ii,p=weights/weights.sum())))
    pos=gpd.GeoDataFrame(geometry=grid.loc[positive_indices].geometry.centroid,crs=LOCAL_CRS)
    roles=import_script('08_build_unlabelled_background.py').assign_roles(grid,pos,2500)
    f['role']=roles.role;f['spatial_block_id']=grid.spatial_block_id
    f['area_km2']=grid.area_km2
    rights=gpd.GeoDataFrame({'source_layer':['synthetic_permit']},geometry=[box(10000,10000,22000,21000)],crs=LOCAL_CRS)
    status=import_script('02_mask_taken_areas.py').compute_cell_status(grid,rights,
                {'legal_status':{'open_max_pct':1.,'partly_taken_max_pct':10.}})
    f['taken_overlap_pct']=status.taken_overlap_pct
    return f,grid,lines,bed

def run(out:Path,iterations=500):
    out.mkdir(parents=True,exist_ok=True)
    f,grid,lines,bed=build_fixture()
    f.to_csv(out/'synthetic_features.csv',index=False)
    lab=f[f.role.isin(['positive','background'])].reset_index(drop=True)
    oof,_,_,folds=fit_grouped(lab,FEATURES)
    y=(lab.role=='positive').astype(int).to_numpy()
    methods={'xgboost':oof,'distance_to_fault':1/(1+lab.dist_major_shear.to_numpy()/1000),
             'random_seed_42':np.random.default_rng(SEED).random(len(lab))}
    metrics={name:{'roc_auc':float(roc_auc_score(y,s)),
                   'average_precision':float(average_precision_score(y,s)),
                   'capture':{str(k):topk_capture(s,y,k) for k in (1,5,10)},
                   'capture_tie_bounds':{str(k):capture_tie_bounds(s,y,k) for k in (1,5,10)}}
             for name,s in methods.items()}
    # Same cells and folds for predeclared ablations. Not a hyperparameter search.
    ablations={}
    for name,cols in {'structure_only':FEATURES[:3], 'gravity_only':['gravity_gradient']}.items():
        s,_,_,_=fit_grouped(lab,cols)
        ablations[name]={'roc_auc':float(roc_auc_score(y,s)), 'top5_capture':topk_capture(s,y,5)}
    # Random draws quantify baseline variation, not uncertainty of the real model.
    rng=np.random.default_rng(SEED);random_auc=[];random_top5=[]
    for _ in range(200):
        s=rng.random(len(y));random_auc.append(roc_auc_score(y,s));random_top5.append(topk_capture(s,y,5))
    lab.assign(y=y,model_score=oof).to_csv(out/'synthetic_oof.csv',index=False)
    (out/'folds.json').write_text(json.dumps(folds,indent=2)+'\n')
    mc=import_script('run_monte_carlo_top10.py')
    # A declared synthetic pool, not the top-ranked Finnish cells.
    pool=f.sample(16,random_state=SEED)[['cell_id']+FEATURES].copy()
    pool.to_csv(out/'synthetic_mc_inputs.csv',index=False)
    mapped,missing=mc.load_and_map_cells(out/'synthetic_mc_inputs.csv',multi_layer_only=False)
    config=mc.MCConfig(n_iter=iterations,seed=SEED)
    result=mc.run_monte_carlo(mapped,config,missing)
    # Public demo reports rank sensitivity only; do not promote the subjective odds transform.
    result.drop(columns=['posterior_mean','posterior_sd']).to_csv(out/'synthetic_mc.csv',index=False)
    summary={'kind':'SYNTHETIC SOFTWARE DEMONSTRATION — not Finland validation',
             'seed':SEED,'grid_cells':len(f),'evaluation_cells':len(lab),'positives':int(y.sum()),
             'spatial_block_m':20000,'folds':len(folds),'all_oof_finite':bool(np.isfinite(oof).all()),
             'metrics':metrics,'ablations':ablations,'mc_iterations':iterations,'mc_candidates':16,
             'random_auc_5_50_95pct':np.quantile(random_auc,[.05,.5,.95]).tolist(),
             'random_top5_5_50_95pct':np.quantile(random_top5,[.05,.5,.95]).tolist()}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('runs/demo'))
    p.add_argument('--iterations',type=int,default=500)
    a=p.parse_args();s=run(a.output,a.iterations)
    print(json.dumps(s,indent=2))
