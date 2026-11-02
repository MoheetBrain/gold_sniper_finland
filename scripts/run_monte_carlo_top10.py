"""Historical Monte Carlo scoring engine, preserved mathematics.

Heuristic parameter sensitivity, NOT calibrated mineral-discovery probabilities.
Default prior, likelihood ratios and penalties are subjective assumptions.
See METHODOLOGY.md and docs/SCIENTIFIC_AUDIT.md. No target data is distributed.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import sys
import warnings
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import numpy as np
import pandas as pd

@dataclass
class MCConfig:
    n_iter: int = 20000
    seed: int = 42
    eps: float = 1e-06
    prior_2km: float = 8.0 / 3798.0
    prior_sd_fraction: float = 0.35
    lr_min: float = 0.2
    lr_max: float = 80.0
    lr_max_sigma_log: float = 0.25
    group_weights: Dict[str, float] = field(default_factory=lambda : {'structure': 0.3, 'gravity': 0.28, 'lithology_rheology': 0.22, 'geochemistry': 0.12, 'magnetics': 0.08})
    group_weight_concentration: float = 80.0
    structure_sub_weights: Dict[str, float] = field(default_factory=lambda : {'fault_intersection_density': 0.35, 'major_shear_distance': 0.3, 'lithological_contact': 0.2, 'splay_jog_distance': 0.15})
    structure_sub_concentration: float = 60.0
    geochem_sub_weights: Dict[str, float] = field(default_factory=lambda : {'till_as_clr': 0.4, 'till_sb_clr': 0.3, 'till_au_clr': 0.3})
    geochem_sub_concentration: float = 60.0
    major_shear_decay_mean_m: float = 1500.0
    major_shear_decay_sd_m: float = 500.0
    major_shear_decay_min_m: float = 500.0
    major_shear_decay_max_m: float = 3000.0
    fault_int_decay_mean_m: float = 750.0
    fault_int_decay_sd_m: float = 300.0
    fault_int_decay_min_m: float = 200.0
    fault_int_decay_max_m: float = 1800.0
    lith_contact_decay_mean_m: float = 900.0
    lith_contact_decay_sd_m: float = 350.0
    lith_contact_decay_min_m: float = 250.0
    lith_contact_decay_max_m: float = 2000.0
    gravity_worm_decay_mean_m: float = 675.0
    gravity_worm_decay_sd_m: float = 300.0
    gravity_worm_decay_min_m: float = 250.0
    gravity_worm_decay_max_m: float = 2000.0
    evidence_threshold_mean: float = 0.55
    evidence_threshold_sd: float = 0.1
    evidence_threshold_min: float = 0.35
    evidence_threshold_max: float = 0.8
    graphitic_shale_penalty: float = 0.4
    graphitic_shale_if_convergent: float = 0.8
    single_signal_penalty: float = 0.5
    missing_group_penalty: float = 0.9
    intersection_bonus: float = 1.25
    no_intersection_penalty: float = 0.75
    accessibility_weight: float = 0.03
    package_correlation_rho: float = 0.65

def clipped_normal(rng: np.random.Generator, mean: float, sd: float, low: float, high: float) -> float:
    return float(np.clip(rng.normal(mean, sd), low, high))

def sample_dirichlet(rng: np.random.Generator, weights: Dict[str, float], concentration: float) -> Dict[str, float]:
    keys = list(weights.keys())
    base = np.array([weights[k] for k in keys], dtype=float)
    base = base / base.sum()
    alpha = np.maximum(base * concentration, 0.01)
    sampled = rng.dirichlet(alpha)
    return dict(zip(keys, sampled))

def distance_decay(distance_m: np.ndarray, scale_m: float) -> np.ndarray:
    d = np.maximum(np.asarray(distance_m, dtype=float), 0.0)
    return np.exp(-d / max(scale_m, 1.0))

def robust_minmax(x: np.ndarray, lo_q: float=0.02, hi_q: float=0.98) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    finite = np.isfinite(x)
    if not finite.any():
        return np.full_like(x, 0.5)
    (lo, hi) = np.nanquantile(x[finite], [lo_q, hi_q])
    if hi <= lo:
        return np.full_like(x, 0.5)
    scaled = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    scaled[~finite] = 0.5
    return scaled

def posterior_from_score(score: np.ndarray, prior: float, lr_min: float, lr_max: float) -> np.ndarray:
    score = np.clip(score, 0.0, 1.0)
    log_lr = math.log(lr_min) + score * (math.log(lr_max) - math.log(lr_min))
    lr = np.exp(log_lr)
    prior = float(np.clip(prior, 1e-07, 1 - 1e-07))
    prior_odds = prior / (1.0 - prior)
    post_odds = prior_odds * lr
    return post_odds / (1.0 + post_odds)

def load_and_map_cells(path: Path, multi_layer_only: bool=True) -> Tuple[pd.DataFrame, List[str]]:
    missing_cols: List[str] = []
    if path.suffix.lower() == '.csv':
        df = pd.read_csv(path)
    elif path.suffix.lower() in ('.parquet', '.pq'):
        df = pd.read_parquet(path)
    elif path.suffix.lower() in ('.gpkg', '.geojson'):
        import geopandas as gpd
        df = pd.DataFrame(gpd.read_file(path).drop(columns=['geometry'], errors='ignore'))
    else:
        raise ValueError(f'Unsupported file: {path}')
    if multi_layer_only and 'audit_status' in df.columns:
        before = len(df)
        df = df[df['audit_status'] == 'multi_layer_review_candidate'].copy()
        print(f'  Filtered to multi-layer candidates: {before} → {len(df)} cells', file=sys.stderr)
    rename_map = {'dist_major_shear': 'dist_major_shear_m', 'dist_key_lithological_contact': 'dist_key_lithological_contact_m'}
    df = df.rename(columns={k: v for (k, v) in rename_map.items() if k in df.columns})
    if 'cell_id' not in df.columns:
        df['cell_id'] = [f'cell_{i:04d}' for i in range(len(df))]
    defaults = {'dist_major_shear_m': 10000.0, 'fault_intersection_density': 0.0, 'dist_key_lithological_contact_m': 10000.0, 'dist_fault_intersection_m': 10000.0, 'dist_splay_or_jog_m': 10000.0, 'gravity_gradient': 0.0, 'dist_gravity_worm_m': 10000.0, 'mag_1vd': 0.0, 'mag_low_in_high_proxy': 0.5, 'magnetic_break_score': 0.5, 'lithology_favourability': 0.5, 'rheology_contrast_score': 0.5, 'till_au_clr': 0.0, 'till_as_clr': 0.0, 'till_sb_clr': 0.0, 'graphitic_shale_score': 0.0, 'wetland_score': 0.0, 'contaminant_cu_ni_co_u_znpb_score': 0.0}
    for (col, default) in defaults.items():
        if col not in df.columns:
            df[col] = default
            missing_cols.append(col)
        else:
            numeric = pd.to_numeric(df[col], errors='coerce')
            if numeric.isna().all():
                missing_cols.append(col)
            df[col] = numeric.fillna(default)
    print(f'  Missing columns filled with defaults: {len(missing_cols)}', file=sys.stderr)
    if missing_cols:
        print(f"    → {', '.join(missing_cols)}", file=sys.stderr)
    return (df, missing_cols)

def add_map_numbers(df: pd.DataFrame, lookup_path: Path) -> pd.DataFrame:
    if not lookup_path.exists():
        print(f'  WARNING: map number lookup not found at {lookup_path}', file=sys.stderr)
        df['map_number'] = -1
        return df
    lookup = pd.read_csv(lookup_path, usecols=['map_number', 'cell_id'])
    df = df.merge(lookup, on='cell_id', how='left')
    df['map_number'] = df['map_number'].fillna(-1).astype(int)
    return df

def add_town_distances(df: pd.DataFrame, lookup_path: Path) -> pd.DataFrame:
    if not lookup_path.exists():
        df['nearest_town'] = 'unknown'
        df['distance_to_nearest_town_km'] = 50.0
        return df
    lookup = pd.read_csv(lookup_path, usecols=['cell_id', 'nearest_town', 'distance_to_nearest_town_km'])
    df = df.merge(lookup, on='cell_id', how='left')
    df['nearest_town'] = df['nearest_town'].fillna('unknown')
    df['distance_to_nearest_town_km'] = df['distance_to_nearest_town_km'].fillna(50.0)
    return df

def run_one_iteration(rng: np.random.Generator, df: pd.DataFrame, cfg: MCConfig, missing_cols: List[str]) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray]]:
    n = len(df)
    group_w = sample_dirichlet(rng, cfg.group_weights, cfg.group_weight_concentration)
    struct_w = sample_dirichlet(rng, cfg.structure_sub_weights, cfg.structure_sub_concentration)
    geochem_w = sample_dirichlet(rng, cfg.geochem_sub_weights, cfg.geochem_sub_concentration)
    shear_scale = clipped_normal(rng, cfg.major_shear_decay_mean_m, cfg.major_shear_decay_sd_m, cfg.major_shear_decay_min_m, cfg.major_shear_decay_max_m)
    int_scale = clipped_normal(rng, cfg.fault_int_decay_mean_m, cfg.fault_int_decay_sd_m, cfg.fault_int_decay_min_m, cfg.fault_int_decay_max_m)
    lith_scale = clipped_normal(rng, cfg.lith_contact_decay_mean_m, cfg.lith_contact_decay_sd_m, cfg.lith_contact_decay_min_m, cfg.lith_contact_decay_max_m)
    worm_scale = clipped_normal(rng, cfg.gravity_worm_decay_mean_m, cfg.gravity_worm_decay_sd_m, cfg.gravity_worm_decay_min_m, cfg.gravity_worm_decay_max_m)
    ev_threshold = clipped_normal(rng, cfg.evidence_threshold_mean, cfg.evidence_threshold_sd, cfg.evidence_threshold_min, cfg.evidence_threshold_max)
    s_shear = distance_decay(df['dist_major_shear_m'].values, shear_scale)
    s_int_dens = robust_minmax(df['fault_intersection_density'].values)
    s_lith = distance_decay(df['dist_key_lithological_contact_m'].values, lith_scale)
    s_splay = distance_decay(df['dist_splay_or_jog_m'].values, int_scale)
    structure_score = struct_w['major_shear_distance'] * s_shear + struct_w['fault_intersection_density'] * s_int_dens + struct_w['lithological_contact'] * s_lith + struct_w['splay_jog_distance'] * s_splay
    structure_score = np.clip(structure_score, 0.0, 1.0)
    g_gradient = robust_minmax(df['gravity_gradient'].values)
    g_worm = distance_decay(df['dist_gravity_worm_m'].values, worm_scale)
    if 'dist_gravity_worm_m' in missing_cols:
        gravity_score = g_gradient
    else:
        gravity_score = 0.7 * g_gradient + 0.3 * g_worm
    gravity_score = np.clip(gravity_score, 0.0, 1.0)
    if 'lithology_signal' in df.columns:
        lith_bool = df['lithology_signal'].astype(float).values
        lith_noise = rng.normal(0, 0.05, n)
        lithology_score = np.clip(lith_bool * 0.8 + 0.1 + lith_noise, 0.0, 1.0)
    else:
        lf = np.clip(df['lithology_favourability'].values, 0.0, 1.0)
        rc = np.clip(df['rheology_contrast_score'].values, 0.0, 1.0)
        lithology_score = np.maximum(lf, rc)
    geochem_cols = {}
    for elem in ['till_as_clr', 'till_sb_clr', 'till_au_clr']:
        direct = df[elem].values if elem in df.columns else np.zeros(n)
        shifted_cols = [f'{elem}_shift_500m', f'{elem}_shift_1km', f'{elem}_shift_2km']
        best = direct.copy()
        for sc in shifted_cols:
            if sc in df.columns:
                shifted = pd.to_numeric(df[sc], errors='coerce').fillna(0.0).values
                best = np.maximum(best, shifted)
        geochem_cols[elem] = best
    as_score = robust_minmax(geochem_cols['till_as_clr'])
    sb_score = robust_minmax(geochem_cols['till_sb_clr'])
    au_score = robust_minmax(geochem_cols['till_au_clr'])
    geochemistry_score = geochem_w['till_as_clr'] * as_score + geochem_w['till_sb_clr'] * sb_score + geochem_w['till_au_clr'] * au_score
    geochemistry_score = np.clip(geochemistry_score, 0.0, 1.0)
    magnetics_score = np.full(n, 0.5)
    group_scores = {'structure': structure_score, 'gravity': gravity_score, 'lithology_rheology': lithology_score, 'geochemistry': geochemistry_score, 'magnetics': magnetics_score}
    log_sum = np.zeros(n, dtype=float)
    w_total = 0.0
    for (group_name, g_score) in group_scores.items():
        w = group_w[group_name]
        log_sum += w * np.log(np.clip(g_score, cfg.eps, 1.0))
        w_total += w
    combined_score = np.exp(log_sum / max(w_total, cfg.eps))
    evidence_count = np.zeros(n, dtype=int)
    for g_score in group_scores.values():
        evidence_count += (g_score >= ev_threshold).astype(int)
    single_signal = evidence_count < 2
    combined_score = np.where(single_signal, combined_score * cfg.single_signal_penalty, combined_score)
    has_intersections = df['fault_intersection_density'].values > 0
    near_shear = df['dist_major_shear_m'].values < 1000.0
    combined_score = np.where(has_intersections, combined_score * cfg.intersection_bonus, np.where(near_shear, combined_score * cfg.no_intersection_penalty, combined_score))
    graphitic = df['graphitic_shale_score'].values
    has_convergence = (structure_score >= ev_threshold) & (geochemistry_score >= ev_threshold)
    graphitic_mult = np.where(graphitic > 0.5, np.where(has_convergence, cfg.graphitic_shale_if_convergent, cfg.graphitic_shale_penalty), 1.0)
    combined_score *= graphitic_mult
    n_missing_groups = count_missing_groups(missing_cols)
    if n_missing_groups > 0:
        combined_score *= cfg.missing_group_penalty ** n_missing_groups
    if 'distance_to_nearest_town_km' in df.columns:
        town_km = df['distance_to_nearest_town_km'].values
        accessibility_bonus = 1.0 + cfg.accessibility_weight * np.clip(1.0 - town_km / 50.0, 0.0, 1.0)
        combined_score *= accessibility_bonus
    combined_score = np.clip(combined_score, 0.0, 1.0)
    sampled_prior = float(np.clip(rng.lognormal(math.log(cfg.prior_2km), cfg.prior_sd_fraction), 1e-06, 0.25))
    sampled_lr_max = float(np.clip(rng.lognormal(math.log(cfg.lr_max), cfg.lr_max_sigma_log), 5.0, 250.0))
    posterior = posterior_from_score(combined_score, sampled_prior, cfg.lr_min, sampled_lr_max)
    return (combined_score, posterior, group_scores)

def count_missing_groups(missing_cols: List[str]) -> int:
    groups = {'structure': {'dist_major_shear_m', 'fault_intersection_density'}, 'geochemistry': {'till_au_clr', 'till_as_clr', 'till_sb_clr'}, 'magnetics': {'mag_1vd', 'mag_low_in_high_proxy'}, 'gravity': {'gravity_gradient'}, 'lithology': {'lithology_favourability', 'rheology_contrast_score'}}
    missing_set = set(missing_cols)
    return sum((1 for cols in groups.values() if cols.issubset(missing_set)))

def run_monte_carlo(df: pd.DataFrame, cfg: MCConfig, missing_cols: List[str], top_ks: Sequence[int]=(1, 3, 5, 10)) -> pd.DataFrame:
    n = len(df)
    if n == 0 or cfg.n_iter <= 0:
        raise ValueError("Need cells and positive iteration count")
    rng = np.random.default_rng(cfg.seed)
    score_sum = np.zeros(n)
    score_sq_sum = np.zeros(n)
    posterior_sum = np.zeros(n)
    posterior_sq_sum = np.zeros(n)
    top_counts = {k: np.zeros(n, dtype=int) for k in top_ks}
    group_sums = {g: np.zeros(n) for g in cfg.group_weights.keys()}
    print(f'\nRunning {cfg.n_iter:,} Monte Carlo iterations on {n} cells...\n', file=sys.stderr)
    for it in range(cfg.n_iter):
        (score, posterior, groups) = run_one_iteration(rng, df, cfg, missing_cols)
        score_sum += score
        score_sq_sum += score ** 2
        posterior_sum += posterior
        posterior_sq_sum += posterior ** 2
        for (g, arr) in groups.items():
            if g in group_sums:
                group_sums[g] += arr
        for k in top_ks:
            kk = min(k, n)
            if kk > 0:
                idx = np.argsort(-score, kind="stable")[:kk]
                top_counts[k][idx] += 1
        if (it + 1) % max(1, cfg.n_iter // 10) == 0:
            print(f'  {it + 1:>7,} / {cfg.n_iter:,} iterations complete', file=sys.stderr)
    score_mean = score_sum / cfg.n_iter
    score_sd = np.sqrt(np.maximum(score_sq_sum / cfg.n_iter - score_mean ** 2, 0.0))
    posterior_mean = posterior_sum / cfg.n_iter
    posterior_sd = np.sqrt(np.maximum(posterior_sq_sum / cfg.n_iter - posterior_mean ** 2, 0.0))
    out = pd.DataFrame({'cell_id': df['cell_id'].values, 'mc_score_mean': np.round(score_mean, 6), 'mc_score_sd': np.round(score_sd, 6), 'posterior_mean': np.round(posterior_mean, 6), 'posterior_sd': np.round(posterior_sd, 6)})
    if 'map_number' in df.columns:
        out['map_number'] = df['map_number'].values
    if 'nearest_town' in df.columns:
        out['nearest_town'] = df['nearest_town'].values
    if 'distance_to_nearest_town_km' in df.columns:
        out['town_km'] = df['distance_to_nearest_town_km'].values
    for k in top_ks:
        out[f'top_{k}_freq'] = np.round(top_counts[k] / cfg.n_iter, 4)
    for (g, arr_sum) in group_sums.items():
        out[f'{g}_mean'] = np.round(arr_sum / cfg.n_iter, 4)
    for col in ['gravity_gradient', 'dist_major_shear_m', 'dist_key_lithological_contact_m', 'fault_intersection_density']:
        if col in df.columns:
            out[col] = df[col].values
    group_cols = [f'{g}_mean' for g in cfg.group_weights.keys()]
    out['n_active_groups'] = (out[group_cols] >= cfg.evidence_threshold_mean).sum(axis=1)
    out = out.sort_values('mc_score_mean', ascending=False).reset_index(drop=True)
    out.insert(0, 'mc_rank', range(1, len(out) + 1))
    return out

def print_top10_report(results: pd.DataFrame, cfg: MCConfig) -> str:
    lines = []
    lines.append('=' * 80)
    lines.append('MONTE CARLO TOP-10 PROSPECTIVITY RANKING')
    lines.append(f'Iterations: {cfg.n_iter:,}  |  Seed: {cfg.seed}  |  Prior: {cfg.prior_2km:.5f}')
    lines.append('=' * 80)
    lines.append('')
    lines.append('IMPORTANT: These are MODELLING CANDIDATES, not confirmed gold targets.')
    lines.append('A cell ranked #1 means it was ROBUSTLY top-ranked across thousands of')
    lines.append('parameter perturbations. It does NOT mean gold is definitely there.')
    lines.append('')
    top10 = results.head(10)
    lines.append(f"{'Rank':<5} {'Map#':<6} {'Cell ID':<12} {'MC Score':>10} {'±SD':>8} {'Posterior':>10} {'Top1%':>7} {'Top5%':>7} {'Top10%':>7} {'Grav':>6} {'Struct':>6} {'Litho':>6} {'Town':>12}")
    lines.append('-' * 120)
    for (_, row) in top10.iterrows():
        map_n = int(row.get('map_number', -1))
        map_str = str(map_n) if map_n > 0 else '?'
        town = str(row.get('nearest_town', '?'))[:10]
        lines.append(f"{int(row['mc_rank']):<5} {map_str:<6} {row['cell_id']:<12} {row['mc_score_mean']:>10.4f} {row['mc_score_sd']:>8.4f} {row['posterior_mean']:>10.6f} {row.get('top_1_freq', 0):>7.1%} {row.get('top_5_freq', 0):>7.1%} {row.get('top_10_freq', 0):>7.1%} {row.get('gravity_gradient', 0):>6.2f} {row.get('structure_mean', 0):>6.3f} {row.get('lithology_rheology_mean', 0):>6.3f} {town:>12}")
    lines.append('')
    lines.append('-' * 120)
    lines.append('')
    lines.append('PACKAGE PROBABILITIES (P(at least one target in package)):')
    lines.append('')
    for pkg_size in [3, 5, 10]:
        pkg = results.head(min(pkg_size, len(results)))
        p = np.clip(pkg['posterior_mean'].values, 0.0, 1.0)
        p_naive = 1.0 - np.prod(1.0 - p)
        p_conservative = float(np.max(p))
        n_eff = 1.0 + (len(p) - 1.0) * (1.0 - cfg.package_correlation_rho)
        p_rho = 1.0 - (1.0 - np.mean(p)) ** n_eff
        lines.append(f'  Top-{pkg_size} package:')
        lines.append(f'    Naive independent:     P(≥1 target) = {p_naive:.4%}')
        lines.append(f'    Conservative (max):     P(≥1 target) = {p_conservative:.4%}')
        lines.append(f'    ρ-adjusted (ρ={cfg.package_correlation_rho}): P(≥1 target) = {p_rho:.4%}')
        lines.append('')
    lines.append('')
    lines.append('KEY:')
    lines.append('  MC Score   = mean evidence score across all iterations (0-1)')
    lines.append('  ±SD        = how much the score wobbles when parameters change')
    lines.append('  Posterior = uncalibrated odds-transform under subjective assumptions; NOT discovery probability')
    lines.append('  Top1/5/10 cells = fraction of iterations where this cell ranked in top K')
    lines.append('  Grav       = raw gravity gradient value (mGal/km)')
    lines.append('  Struct     = mean structure group score')
    lines.append('  Litho      = mean lithology/rheology group score')
    lines.append('  Town       = nearest settlement')
    lines.append('')
    report = '\n'.join(lines)
    print(report)
    return report

def main():
    parser = argparse.ArgumentParser(description='Monte Carlo top-10 prospectivity ranking for CLGB gold candidates.', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--cells', default=None, help='Input cell table. Default: data/outputs/review_candidates_audited.csv')
    parser.add_argument('--out', default=None, help='Output CSV path. Default: data/outputs/monte_carlo_top10.csv')
    parser.add_argument('--n-iter', type=int, default=20000, help='Number of Monte Carlo iterations.')
    parser.add_argument('--seed', type=int, default=42, help='Random seed for reproducibility.')
    parser.add_argument('--all-candidates', action='store_true', help='Run on all 63 candidates, not just 16 multi-layer.')
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent
    cells_path = Path(args.cells) if args.cells else project_root / 'data/outputs/review_candidates_audited.csv'
    out_path = Path(args.out) if args.out else project_root / 'data/outputs/monte_carlo_top10.csv'
    lookup_path = project_root / 'data/outputs/clgb_grid_2km_number_lookup.csv'
    print(f'Input: {cells_path}', file=sys.stderr)
    print(f'Output: {out_path}', file=sys.stderr)
    (df, missing_cols) = load_and_map_cells(cells_path, multi_layer_only=not args.all_candidates)
    df = add_map_numbers(df, lookup_path)
    df = add_town_distances(df, lookup_path)
    cfg = MCConfig(n_iter=args.n_iter, seed=args.seed)
    results = run_monte_carlo(df, cfg, missing_cols)
    report = print_top10_report(results, cfg)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(out_path, index=False)
    print(f'\nResults saved to: {out_path}', file=sys.stderr)
    report_path = out_path.with_suffix('.md')
    report_path.write_text(report, encoding='utf-8')
    print(f'Report saved to: {report_path}', file=sys.stderr)
    config_path = out_path.with_name(out_path.stem + '_config.json')
    config_path.write_text(json.dumps(asdict(cfg), indent=2, default=str), encoding='utf-8')
    print(f'Config saved to: {config_path}', file=sys.stderr)
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
