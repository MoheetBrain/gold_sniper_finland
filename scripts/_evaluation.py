"""Shared release evaluation: grouped holdouts, fold-local imputation and weights."""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from xgboost import XGBClassifier

PARAMS = dict(n_estimators=200, max_depth=3, learning_rate=0.08,
              subsample=0.9, colsample_bytree=0.9, eval_metric="logloss",
              random_state=42, n_jobs=2)

def fit_grouped(lab, features):
    if not features or not lab["cell_id"].is_unique:
        raise ValueError("Need features and unique cell IDs")
    if lab["spatial_block_id"].isna().any():
        raise ValueError("Spatial block IDs must be present")
    X = lab[features].astype(float)
    if np.isinf(X.to_numpy()).any():
        raise ValueError("Infinite feature values are invalid; use NaN for missing")
    y = (lab["role"] == "positive").astype(int).to_numpy()
    groups = lab["spatial_block_id"].to_numpy()
    n_splits = min(5, len(np.unique(groups)), max(2, int(y.sum())))
    if n_splits < 2 or len(np.unique(y)) != 2:
        raise ValueError("Need at least two spatial groups and both classes")
    oof = np.full(len(lab), np.nan)
    folds = []
    for fold, (tr, te) in enumerate(GroupKFold(n_splits).split(X, y, groups)):
        if len(np.unique(y[tr])) != 2:
            raise ValueError("Training fold has only one class; no partial-denominator evaluation")
        med = X.iloc[tr].median().fillna(0.0)
        weight = max(1.0, float((y[tr] == 0).sum() / y[tr].sum()))
        model = XGBClassifier(**PARAMS, scale_pos_weight=weight)
        model.fit(X.iloc[tr].fillna(med), y[tr])
        oof[te] = model.predict_proba(X.iloc[te].fillna(med))[:, 1]
        folds.append(dict(fold=fold, train_indices=tr.tolist(), test_indices=te.tolist(),
                          train_groups=sorted(set(groups[tr])), test_groups=sorted(set(groups[te])),
                          train_positives=int(y[tr].sum()), test_positives=int(y[te].sum()),
                          medians=med.to_dict(), scale_pos_weight=weight))
    med = X.median().fillna(0.0)
    final = XGBClassifier(**PARAMS, scale_pos_weight=max(1.0,float((y==0).sum()/y.sum())))
    final.fit(X.fillna(med), y)
    return oof, final, med, folds


def topk_capture(scores, y, k_pct):
    scores, y = np.asarray(scores,float), np.asarray(y)
    if scores.ndim != 1 or y.shape != scores.shape or len(y)==0:
        raise ValueError("Scores and labels must be matching non-empty vectors")
    if not np.isfinite(scores).all() or not np.isin(y,[0,1]).all() or y.sum()==0:
        raise ValueError("Need finite scores, binary labels and at least one positive")
    if not 0 < k_pct <= 100:
        raise ValueError("k_pct must be in (0,100]")
    n = max(1,int(np.ceil(len(scores)*k_pct/100)))
    # Stable input order breaks ties; call capture_tie_bounds to expose sensitivity.
    return float(y[np.argsort(-scores,kind="stable")[:n]].sum()/y.sum())


def capture_tie_bounds(scores, y, k_pct):
    topk_capture(scores,y,k_pct) # validate
    scores,y=np.asarray(scores,float),np.asarray(y,int)
    n=max(1,int(np.ceil(len(scores)*k_pct/100)))
    threshold=np.sort(scores)[-n]
    above=scores>threshold; tied=scores==threshold
    slots=n-int(above.sum()); positives=int(y[tied].sum()); negatives=int(tied.sum())-positives
    base=int(y[above].sum()); total=int(y.sum())
    return {"minimum":(base+max(0,slots-negatives))/total,
            "maximum":(base+min(slots,positives))/total,
            "boundary_tie_cells":int(tied.sum())}
