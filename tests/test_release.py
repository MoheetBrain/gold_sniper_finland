import sys,json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from _common import import_script
import _evaluation as ev


def sample():
    return pd.DataFrame({'cell_id':[str(i) for i in range(12)],'role':['positive','background','background']*4,
        'spatial_block_id':np.repeat(['a','b','c','d'],3),'x':[1.,np.nan,3.,10.,np.nan,30.,100.,np.nan,300.,1000.,np.nan,3000.]})

def test_imputation_and_class_weights_are_training_only(monkeypatch):
    seen=[]
    class Fake:
        def __init__(self,**kw):self.kw=kw;self.feature_importances_=np.array([1.])
        def fit(self,X,y):seen.append((X.copy(),np.array(y),self.kw));return self
        def predict_proba(self,X):return np.tile([.6,.4],(len(X),1))
    monkeypatch.setattr(ev,'XGBClassifier',Fake)
    d=sample();o,_,_,folds=ev.fit_grouped(d,['x'])
    assert np.isfinite(o).all()
    for (X,y,params),f in zip(seen,folds):
        tr=f['train_indices'];te=f['test_indices']
        assert not set(f['train_groups'])&set(f['test_groups'])
        median=d.iloc[tr].x.median()
        assert f['medians']['x']==median
        np.testing.assert_allclose(X.x,d.iloc[tr].x.fillna(median))
        assert params['scale_pos_weight']==max(1,(y==0).sum()/y.sum())
        assert not set(tr)&set(te)
    assert sorted(i for f in folds for i in f['test_indices'])==list(range(12))


def test_single_class_fold_refuses_partial_evaluation():
    d=sample();d['role']='background';d.loc[:2,'role']='positive'
    with pytest.raises(ValueError,match='Training fold'):ev.fit_grouped(d,['x'])

@pytest.mark.parametrize('change',['duplicates','group_missing','infinite','one_group'])
def test_bad_inputs_rejected(change):
    d=sample()
    if change=='duplicates':d['cell_id']='duplicate'
    elif change=='group_missing':d.loc[0,'spatial_block_id']=None
    elif change=='infinite':d.loc[0,'x']=np.inf
    else:d['spatial_block_id']='one'
    with pytest.raises(ValueError):ev.fit_grouped(d,['x'])


def test_empty_rest_training_regression():
    scores,_,n,folds=import_script('11_train_baseline_xgboost_or_pu.py').train_oof(sample(),['x'])
    assert len(scores)==12 and n==4 and folds==4
    assert scores.in_cv.all() and scores.model_score.notna().all()


def test_topk_ties_and_counts():
    assert ev.topk_capture([.8,.7,.1,.0],[1,0,0,1],25)==.5
    b=ev.capture_tie_bounds([1,1,1,1],[1,0,0,0],25)
    assert b=={'minimum':0.,'maximum':1.,'boundary_tie_cells':4}

@pytest.mark.parametrize('scores,y,k',[([],[],5),([np.nan,1],[1,0],5),([0,1],[0,0],5),([1,0],[1,0],0),([1,0],[1,0],101)])
def test_invalid_capture(scores,y,k):
    with pytest.raises(ValueError):ev.topk_capture(scores,y,k)


def test_gravity_gradient_units():
    g=import_script('06d_process_gravity.py')
    # 2 mGal/km east and 3 mGal/km north => sqrt(13) mGal/km.
    y,x=np.mgrid[:4,:4];a=2*x+3*y
    np.testing.assert_allclose(g.filled_gradient_mgal_per_km(a.astype(float),1000,1000),np.sqrt(13))


def test_crs_public_location_roundtrip():
    from pyproj import Transformer
    forward=Transformer.from_crs(4326,3067,always_xy=True)
    back=Transformer.from_crs(3067,4326,always_xy=True)
    np.testing.assert_allclose(back.transform(*forward.transform(25,60)),[25,60],atol=1e-8)


def test_mc_reproducible_and_topk_conserved(tmp_path):
    m=import_script('run_monte_carlo_top10.py')
    p=tmp_path/'synthetic.csv';pd.DataFrame({'cell_id':['synthetic_a','synthetic_b','synthetic_c'],'dist_major_shear':[1.,100.,2000.],'gravity_gradient':[.1,1,2]}).to_csv(p,index=False)
    d,missing=m.load_and_map_cells(p,False);cfg=m.MCConfig(n_iter=30,seed=7)
    a=m.run_monte_carlo(d,cfg,missing,top_ks=(1,3));b=m.run_monte_carlo(d,cfg,missing,top_ks=(1,3))
    pd.testing.assert_frame_equal(a,b)
    assert a.top_1_freq.sum()==pytest.approx(1,abs=.0002)
    assert (a.top_3_freq==1).all()
    with pytest.raises(ValueError):m.run_monte_carlo(d,m.MCConfig(n_iter=0),missing)


def test_original_aggregate_consistency():
    r=Path(__file__).resolve().parents[1]
    v=json.loads((r/'data/historical/STEP2_VALIDATION.json').read_text())
    a=pd.read_csv(r/'data/historical/STEP2_2B_FEATURE_ABLATION.csv')
    full=a[a.group=='full_current_model'].iloc[0]
    assert full.n_eval_cells==v['n_eval_cells']==3649
    assert full.n_positives==v['n_positives']==8
    assert round(full.roc_auc,3)==v['roc_auc']['model_xgb_oof']==.798
    assert full.top5pct*8==1
    assert v['capture']['baseline_distfault']['top10pct']*8==2


def test_synthetic_features_preserve_missingness_and_geometry():
    from demo import build_fixture
    f,g,lines,bed=build_fixture()
    assert len(f)==900 and (f.role=='positive').sum()==9
    assert f.till_au_clr.isna().mean()>.8
    assert (f.dist_major_shear>=0).all() and f.cell_id.str.startswith('synthetic_').all()
    assert g.geometry.is_valid.all() and f.taken_overlap_pct.between(0,100).all()


def test_archive_traversal_is_rejected(tmp_path):
    import zipfile
    m=import_script('00_download_tukes_map_files.py')
    p=tmp_path/'bad.zip'
    with zipfile.ZipFile(p,'w') as z:z.writestr('../../escape.txt','not written')
    with pytest.raises(ValueError,match='Unsafe'):m.extract_zip(p,tmp_path/'extract')
    assert not (tmp_path/'escape.txt').exists()


def test_missing_source_crs_is_not_guessed(monkeypatch,tmp_path):
    import geopandas as gpd
    from shapely.geometry import box
    m=import_script('02_mask_taken_areas.py')
    monkeypatch.setattr(gpd,'read_file',lambda p:gpd.GeoDataFrame(geometry=[box(0,0,1,1)]))
    with pytest.raises(ValueError,match='CRS missing'):m.load_and_clean(tmp_path/'x.shp',tmp_path,'EPSG:3067')


def test_overlapping_rights_are_union_not_double_counted():
    import geopandas as gpd
    from shapely.geometry import box
    grid=import_script('01_make_aoi_grid.py').build_grid([0,0,1000,1000],1000,'EPSG:3067')
    rights=gpd.GeoDataFrame({'source_layer':['one','two']},geometry=[box(0,0,500,1000),box(0,0,500,1000)],crs='EPSG:3067')
    out=import_script('02_mask_taken_areas.py').compute_cell_status(grid,rights,{'legal_status':{'open_max_pct':1,'partly_taken_max_pct':10}})
    assert out.taken_overlap_pct.iloc[0]==pytest.approx(50)


def test_up_ice_direction_is_opposite_transport():
    m=import_script('19_build_interim_till_features_au_as_sb.py')
    np.testing.assert_allclose(m.up_ice_offset(1000,90),[-1000,0],atol=1e-9)
    np.testing.assert_allclose(m.up_ice_offset(1000,180),[0,1000],atol=1e-9)


def test_all_null_mc_columns_are_marked_missing(tmp_path):
    m=import_script('run_monte_carlo_top10.py');p=tmp_path/'null.csv'
    pd.DataFrame({'cell_id':['synthetic_a'],'gravity_gradient':[np.nan]}).to_csv(p,index=False)
    _,missing=m.load_and_map_cells(p,False)
    assert 'gravity_gradient' in missing
