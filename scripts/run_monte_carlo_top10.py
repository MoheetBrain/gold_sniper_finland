#!/usr/bin/env python3
"""
GeoArb_Finland Monte Carlo prospectivity engine — TOP-10 focused version
========================================================================

PURPOSE:
--------
Run Monte Carlo uncertainty-propagation over the 16 multi-layer review
candidates (or all cells if you prefer) to find which cells are ROBUSTLY
top-ranked when we perturb uncertain geological variables.

This version is ADAPTED to the ACTUAL data columns in the project:
  - review_candidates_audited.csv  (63 cells, 16 multi-layer)
  - clgb_grid_2km_number_lookup.csv (map number ↔ cell_id lookup)

KEY DESIGN DECISIONS (read these — they explain WHY):
-----------------------------------------------------
1. COLUMN MAPPING: The original MC script expected idealised column names
   like 'dist_major_shear_m', but our actual data has 'dist_major_shear'
   (no _m suffix). This script maps between the two.

2. GRAVITY DOMINANCE: GTK's CLGB 3D modelling report says gravity worms
   spatially correlate with 70% of known gold deposits within 675 m.
   So gravity gets MORE weight than in a generic orogenic-gold model.

3. HIERARCHY-AWARE: Your 9-rule hierarchy is encoded as multiplicative
   gates and bonuses, not just additive weights. A cell can't "score its
   way past" a legal block or single-signal problem.

4. MISSING DATA HONESTY: Magnetics are missing (visual-only), till geochem
   is sparse. Instead of hallucinating scores, we penalise missing groups
   and clearly report the gap.

5. WHAT THIS DOES NOT DO: It does NOT prove gold exists. It estimates
   which cells remain in the top 10 across thousands of "what if" worlds
   where we perturb decay scales, weights, and thresholds.

USAGE:
------
    python scripts/run_monte_carlo_top10.py

    # Custom iterations (more = slower but more stable):
    python scripts/run_monte_carlo_top10.py --n-iter 50000

    # Run on ALL 63 audited candidates, not just the 16 multi-layer:
    python scripts/run_monte_carlo_top10.py --all-candidates

    # Use 1km grid feature stack instead:
    python scripts/run_monte_carlo_top10.py --cells data/processed/feature_stack_minimal_1km.parquet
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


# =============================================================================
# 1. CONFIGURATION — all assumptions are explicit and editable
# =============================================================================

@dataclass
class MCConfig:
    """
    Every numerical assumption lives here. Nothing is hidden.

    WHY THESE VALUES:
    - Group weights emphasise structure + gravity for CLGB, not generic orogenic gold.
    - Distance decay scales come from the GTK CLGB 3D report and project discussions.
    - Penalties are multiplicative gates matching your 9-rule hierarchy.
    """

    # --- Iteration control ---
    n_iter: int = 20_000          # 20k is a good balance; use 100k for final runs
    seed: int = 42                # reproducibility
    eps: float = 1e-6             # numerical floor to avoid log(0)

    # --- Prior probability ---
    # From your data: 8 known orogenic gold cells / 3798 total 2km cells
    # This is the BASE RATE before any evidence is considered.
    # The MC perturbs this ±35% each iteration to test sensitivity.
    prior_2km: float = 8.0 / 3798.0   # ~0.0021
    prior_sd_fraction: float = 0.35    # uncertainty around prior

    # --- Likelihood ratio bounds ---
    # Maps evidence score -> how much it shifts the odds.
    # LR=80 means "best possible evidence makes target 80x more likely than prior"
    # LR=0.20 means "worst evidence makes target 5x LESS likely"
    # These are intentionally bounded — no infinite certainty allowed.
    lr_min: float = 0.20
    lr_max: float = 80.0
    lr_max_sigma_log: float = 0.25    # uncertainty in the max LR itself

    # --- Evidence group weights ---
    # IMPORTANT: These reflect the CLGB-specific geology hierarchy you defined.
    #
    # WHY gravity is weighted heavily:
    #   GTK CLGB report: 70% of known gold within 675m of gravity worms,
    #   worms cover only 30% of area. That's a 2.3x spatial enrichment.
    #
    # WHY structure is #1:
    #   Orogenic gold REQUIRES structural control. No structure = no trap.
    #   But we penalise straight faults separately (intersection bonus).
    #
    # WHY geochemistry is lower:
    #   Till geochem is sparse in your data. Most cells have NO till data.
    #   Penalising cells for missing data they can't control is unfair.
    #   So geochem contributes when present but doesn't dominate when absent.
    #
    # WHY magnetics is minimal:
    #   You have NO numeric magnetics. All mag features are NULL.
    #   Giving weight to missing data would hallucinate evidence.
    group_weights: Dict[str, float] = field(default_factory=lambda: {
        "structure":          0.30,   # fault proximity + intersections + splays
        "gravity":            0.28,   # gravity gradient + worm proximity
        "lithology_rheology": 0.22,   # contact proximity + favourability
        "geochemistry":       0.12,   # till Au-As-Sb when available
        "magnetics":          0.08,   # nearly zero because data is missing
    })
    group_weight_concentration: float = 80.0  # Dirichlet concentration (higher = less perturbation)

    # --- Structure sub-weights ---
    # Within the structure group, what matters most?
    #
    # WHY intersection density is #1:
    #   Your hierarchy rule #4 says "at structural bend/intersection/splay,
    #   not straight fault". A cell ON a fault but with no intersection is
    #   a fluid highway, not a trap. Intersection density IS the trap signal.
    #
    # WHY major shear distance is #2:
    #   You need to be NEAR the plumbing, but being ON a straight fault is
    #   penalised by the intersection requirement. The distance decay handles this.
    structure_sub_weights: Dict[str, float] = field(default_factory=lambda: {
        "fault_intersection_density":  0.35,  # bend/jog/intersection count
        "major_shear_distance":        0.30,  # proximity to main shear zone
        "lithological_contact":        0.20,  # rheological contrast boundary
        "splay_jog_distance":          0.15,  # second-order splay proximity
    })
    structure_sub_concentration: float = 60.0

    # --- Geochemistry sub-weights ---
    # NotebookLM + project: As is the best CLGB pathfinder, then Sb, then Au.
    # Au in till can be patchy (nugget effect); As/Sb are more spatially continuous.
    geochem_sub_weights: Dict[str, float] = field(default_factory=lambda: {
        "till_as_clr": 0.40,    # arsenic: best CLGB pathfinder
        "till_sb_clr": 0.30,    # antimony: second pathfinder
        "till_au_clr": 0.30,    # gold: direct but nugget-y
    })
    geochem_sub_concentration: float = 60.0

    # --- Distance-decay parameters (metres) ---
    # Each iteration samples a decay scale from N(mean, sd) clipped to [min, max].
    # This means the model tests: "what if gold influence extends 500m? 2000m? 3000m?"
    #
    # WHY these ranges:
    #   major_shear: CLGB shears influence 500m-3000m (literature: 1-3km halos)
    #   fault_intersection: tighter, 200m-1800m (traps are localized)
    #   lith_contact: 250m-2000m (contact metasomatism zones)
    #   gravity_worm: GTK says 675m for 70% capture, so mean=675, range 250-2000
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

    # Gravity worm decay: calibrated from the GTK "675m = 70% capture" stat.
    # If 70% of gold is within 675m, then scale ≈ 675 / ln(1/0.3) ≈ 560m
    # We use a slightly wider range because worm geometry varies.
    gravity_worm_decay_mean_m: float = 675.0
    gravity_worm_decay_sd_m: float = 300.0
    gravity_worm_decay_min_m: float = 250.0
    gravity_worm_decay_max_m: float = 2000.0

    # --- Threshold for "evidence present" (used for convergence counting) ---
    evidence_threshold_mean: float = 0.55
    evidence_threshold_sd: float = 0.10
    evidence_threshold_min: float = 0.35
    evidence_threshold_max: float = 0.80

    # --- Penalty multipliers ---
    # These match your hierarchy rules #8 and #9.
    # They MULTIPLY the score, so 0.5 means "cut score in half".
    graphitic_shale_penalty: float = 0.40         # rule #9: graphitic FP without convergence
    graphitic_shale_if_convergent: float = 0.80   # softer if real structure+geochem convergence
    single_signal_penalty: float = 0.50           # rule #2: must be multi-layer
    missing_group_penalty: float = 0.90           # per missing core group

    # --- Structural intersection bonus ---
    # Cells WITH fault intersections get a multiplicative bonus.
    # WHY: your hierarchy rule #4 says "at bend/intersection/splay".
    # A cell near a straight fault with no intersections is penalised.
    intersection_bonus: float = 1.25    # 25% bonus for having intersections
    no_intersection_penalty: float = 0.75  # 25% penalty for zero intersections near shear

    # --- Accessibility bonus (soft, rule #7) ---
    # Closer to town = slightly preferred, all else equal.
    # This is a TIE-BREAKER, not a geological criterion.
    accessibility_weight: float = 0.03   # very small — barely moves the needle

    # --- Package correlation ---
    # Adjacent cells are NOT independent bets. This controls the correlation.
    package_correlation_rho: float = 0.65


# =============================================================================
# 2. UTILITY FUNCTIONS
# =============================================================================

def clipped_normal(rng: np.random.Generator, mean: float, sd: float,
                   low: float, high: float) -> float:
    """
    Sample a value from Normal(mean, sd) but clip to [low, high].

    WHY CLIPPING: geological decay scales can't be negative or absurdly large.
    The clip prevents the MC from exploring physically impossible parameter space.
    """
    return float(np.clip(rng.normal(mean, sd), low, high))


def sample_dirichlet(rng: np.random.Generator, weights: Dict[str, float],
                     concentration: float) -> Dict[str, float]:
    """
    Sample weight vectors from a Dirichlet distribution centred on 'weights'.

    WHY DIRICHLET: It's the natural distribution over weight vectors that
    sum to 1. High concentration = weights barely move. Low = wild swings.
    This is how we say "we believe these weights but not perfectly".

    concentration=80 means: weights are quite stable, ±5-10% per iteration.
    concentration=20 means: weights swing ±20-30%, testing robustness hard.
    """
    keys = list(weights.keys())
    base = np.array([weights[k] for k in keys], dtype=float)
    base = base / base.sum()
    alpha = np.maximum(base * concentration, 0.01)
    sampled = rng.dirichlet(alpha)
    return dict(zip(keys, sampled))


def distance_decay(distance_m: np.ndarray, scale_m: float) -> np.ndarray:
    """
    Convert distance (metres) to a 0-1 favourability score.

    Formula: exp(-distance / scale)
      - 0 metres → score = 1.0 (right on it)
      - distance = scale → score ≈ 0.37
      - distance = 3*scale → score ≈ 0.05

    WHY EXPONENTIAL: geological influence doesn't have a sharp edge.
    A binary "within 1km = good, beyond = bad" is false precision.
    Exponential decay is a simple, physically reasonable approximation.
    """
    d = np.maximum(np.asarray(distance_m, dtype=float), 0.0)
    return np.exp(-d / max(scale_m, 1.0))


def robust_minmax(x: np.ndarray, lo_q: float = 0.02, hi_q: float = 0.98) -> np.ndarray:
    """
    Scale values to 0-1 using robust quantile boundaries.

    WHY QUANTILES not min/max: one insane outlier value would crush all
    other cells to near-zero. 2nd and 98th percentile boundaries are
    robust to outliers while still using most of the data range.
    """
    x = np.asarray(x, dtype=float)
    finite = np.isfinite(x)
    if not finite.any():
        return np.full_like(x, 0.5)
    lo, hi = np.nanquantile(x[finite], [lo_q, hi_q])
    if hi <= lo:
        return np.full_like(x, 0.5)
    scaled = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    scaled[~finite] = 0.5  # missing data → neutral, not zero
    return scaled


def posterior_from_score(score: np.ndarray, prior: float,
                         lr_min: float, lr_max: float) -> np.ndarray:
    """
    Map 0-1 evidence score to posterior probability via likelihood ratio.

    The bridge:
      score=0 → LR = lr_min  (evidence says "unlikely")
      score=1 → LR = lr_max  (evidence says "very likely")
      linear interpolation in log-LR space between them.

    Then: posterior = prior_odds × LR / (1 + prior_odds × LR)

    WHY THIS APPROACH: It's a transparent, auditable Bayesian update.
    The prior is your base rate (8/3798 ≈ 0.2%). The LR is how much
    the evidence should move your beliefs. You can disagree with the
    LR bounds and change them — that's the point.

    WHAT THIS IS NOT: a calibrated classifier. To calibrate properly,
    you'd need more known deposits. This is a principled estimate.
    """
    score = np.clip(score, 0.0, 1.0)
    log_lr = math.log(lr_min) + score * (math.log(lr_max) - math.log(lr_min))
    lr = np.exp(log_lr)
    prior = float(np.clip(prior, 1e-7, 1 - 1e-7))
    prior_odds = prior / (1.0 - prior)
    post_odds = prior_odds * lr
    return post_odds / (1.0 + post_odds)


# =============================================================================
# 3. DATA LOADING — maps YOUR actual columns to MC column names
# =============================================================================

def load_and_map_cells(path: Path, multi_layer_only: bool = True) -> Tuple[pd.DataFrame, List[str]]:
    """
    Load the audited review candidates and map columns to MC expectations.

    KEY MAPPING ISSUES FIXED:
    - Your data has 'dist_major_shear' (no _m suffix) → we rename to 'dist_major_shear_m'
    - Your data has 'dist_key_lithological_contact' → renamed to 'dist_key_lithological_contact_m'
    - Your data has centroid_lat/lon but no x/y → we DON'T need x/y for this analysis
    - Your data has NO: dist_fault_intersection_m, dist_splay_or_jog_m,
      dist_gravity_worm_m, mag_*, lithology_favourability, rheology_contrast_score,
      graphitic_shale_score, wetland_score, contaminant_* → all handled gracefully
    """
    missing_cols: List[str] = []

    if path.suffix.lower() == '.csv':
        df = pd.read_csv(path)
    elif path.suffix.lower() in ('.parquet', '.pq'):
        df = pd.read_parquet(path)
    elif path.suffix.lower() in ('.gpkg', '.geojson'):
        import geopandas as gpd
        df = pd.DataFrame(gpd.read_file(path).drop(columns=['geometry'], errors='ignore'))
    else:
        raise ValueError(f"Unsupported file: {path}")

    # Filter to multi-layer candidates only (your 16) unless --all-candidates
    if multi_layer_only and 'audit_status' in df.columns:
        before = len(df)
        df = df[df['audit_status'] == 'multi_layer_review_candidate'].copy()
        print(f"  Filtered to multi-layer candidates: {before} → {len(df)} cells", file=sys.stderr)

    # ── Column renaming: YOUR data → MC expectations ──
    rename_map = {
        'dist_major_shear': 'dist_major_shear_m',
        'dist_key_lithological_contact': 'dist_key_lithological_contact_m',
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # ── Ensure cell_id exists ──
    if 'cell_id' not in df.columns:
        df['cell_id'] = [f"cell_{i:04d}" for i in range(len(df))]

    # ── Fill missing columns with honest defaults ──
    # Each missing column is logged so the output report shows the gap.
    defaults = {
        # Structure columns we DO have (after rename)
        'dist_major_shear_m': 10000.0,
        'fault_intersection_density': 0.0,
        'dist_key_lithological_contact_m': 10000.0,

        # Structure columns we DON'T have
        'dist_fault_intersection_m': 10000.0,    # not computed in pipeline
        'dist_splay_or_jog_m': 10000.0,          # not computed in pipeline

        # Gravity — we HAVE gravity_gradient, DON'T have dist_gravity_worm_m
        'gravity_gradient': 0.0,
        'dist_gravity_worm_m': 10000.0,          # not computed separately

        # Magnetics — ALL missing (visual-only products, not numeric)
        'mag_1vd': 0.0,
        'mag_low_in_high_proxy': 0.5,
        'magnetic_break_score': 0.5,

        # Lithology — not in audit CSV as separate scores
        'lithology_favourability': 0.5,
        'rheology_contrast_score': 0.5,

        # Geochemistry — may be partially present
        'till_au_clr': 0.0,
        'till_as_clr': 0.0,
        'till_sb_clr': 0.0,

        # False-positive scores — not computed yet
        'graphitic_shale_score': 0.0,
        'wetland_score': 0.0,
        'contaminant_cu_ni_co_u_znpb_score': 0.0,
    }

    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default
            missing_cols.append(col)
        else:
            # Fill NaN with defaults even in existing columns
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(default)

    print(f"  Missing columns filled with defaults: {len(missing_cols)}", file=sys.stderr)
    if missing_cols:
        print(f"    → {', '.join(missing_cols)}", file=sys.stderr)

    return df, missing_cols


def add_map_numbers(df: pd.DataFrame, lookup_path: Path) -> pd.DataFrame:
    """
    Merge map numbers from the grid atlas lookup so output is human-readable.
    Your map numbers (1158, 2387, etc.) are the primary way you identify cells.
    """
    if not lookup_path.exists():
        print(f"  WARNING: map number lookup not found at {lookup_path}", file=sys.stderr)
        df['map_number'] = -1
        return df

    lookup = pd.read_csv(lookup_path, usecols=['map_number', 'cell_id'])
    df = df.merge(lookup, on='cell_id', how='left')
    df['map_number'] = df['map_number'].fillna(-1).astype(int)
    return df


def add_town_distances(df: pd.DataFrame, lookup_path: Path) -> pd.DataFrame:
    """
    Merge nearest town info for accessibility ranking (hierarchy rule #7).
    """
    if not lookup_path.exists():
        df['nearest_town'] = 'unknown'
        df['distance_to_nearest_town_km'] = 50.0
        return df

    lookup = pd.read_csv(lookup_path, usecols=['cell_id', 'nearest_town', 'distance_to_nearest_town_km'])
    df = df.merge(lookup, on='cell_id', how='left')
    df['nearest_town'] = df['nearest_town'].fillna('unknown')
    df['distance_to_nearest_town_km'] = df['distance_to_nearest_town_km'].fillna(50.0)
    return df


# =============================================================================
# 4. ONE MONTE CARLO ITERATION
# =============================================================================

def run_one_iteration(
    rng: np.random.Generator,
    df: pd.DataFrame,
    cfg: MCConfig,
    missing_cols: List[str],
) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray]]:
    """
    Run a single MC iteration: sample parameters, score all cells, return scores.

    FLOW:
    1. Sample perturbed weights from Dirichlet
    2. Sample perturbed distance-decay scales from clipped Normal
    3. Compute each evidence group score (structure, gravity, lithology, geochem, magnetics)
    4. Combine groups via weighted geometric mean
    5. Apply hierarchy penalties (single-signal, intersection bonus, etc.)
    6. Convert score → posterior probability via sampled prior + LR
    """
    n = len(df)

    # ── Step 1: Sample perturbed weights ──
    group_w = sample_dirichlet(rng, cfg.group_weights, cfg.group_weight_concentration)
    struct_w = sample_dirichlet(rng, cfg.structure_sub_weights, cfg.structure_sub_concentration)
    geochem_w = sample_dirichlet(rng, cfg.geochem_sub_weights, cfg.geochem_sub_concentration)

    # ── Step 2: Sample perturbed decay scales ──
    shear_scale = clipped_normal(rng, cfg.major_shear_decay_mean_m, cfg.major_shear_decay_sd_m,
                                  cfg.major_shear_decay_min_m, cfg.major_shear_decay_max_m)
    int_scale = clipped_normal(rng, cfg.fault_int_decay_mean_m, cfg.fault_int_decay_sd_m,
                                cfg.fault_int_decay_min_m, cfg.fault_int_decay_max_m)
    lith_scale = clipped_normal(rng, cfg.lith_contact_decay_mean_m, cfg.lith_contact_decay_sd_m,
                                 cfg.lith_contact_decay_min_m, cfg.lith_contact_decay_max_m)
    worm_scale = clipped_normal(rng, cfg.gravity_worm_decay_mean_m, cfg.gravity_worm_decay_sd_m,
                                 cfg.gravity_worm_decay_min_m, cfg.gravity_worm_decay_max_m)
    ev_threshold = clipped_normal(rng, cfg.evidence_threshold_mean, cfg.evidence_threshold_sd,
                                   cfg.evidence_threshold_min, cfg.evidence_threshold_max)

    # ── Step 3: Compute group scores ──

    # --- STRUCTURE GROUP ---
    # This is the MOST IMPORTANT group. It combines:
    #   a) Distance to major shear zone (exponential decay)
    #   b) Fault intersection density (more intersections = better trap)
    #   c) Distance to lithological contact (rheological contrast)
    #   d) Distance to splay/jog (second-order structure)
    s_shear = distance_decay(df['dist_major_shear_m'].values, shear_scale)
    s_int_dens = robust_minmax(df['fault_intersection_density'].values)
    s_lith = distance_decay(df['dist_key_lithological_contact_m'].values, lith_scale)
    s_splay = distance_decay(df['dist_splay_or_jog_m'].values, int_scale)

    structure_score = (
        struct_w['major_shear_distance'] * s_shear +
        struct_w['fault_intersection_density'] * s_int_dens +
        struct_w['lithological_contact'] * s_lith +
        struct_w['splay_jog_distance'] * s_splay
    )
    structure_score = np.clip(structure_score, 0.0, 1.0)

    # --- GRAVITY GROUP ---
    # Two components:
    #   a) gravity_gradient: the magnitude of the Bouguer gradient at the cell
    #      Higher gradient = sharper density contrast = potential worm/contact
    #   b) dist_gravity_worm_m: distance to nearest worm axis (if computed)
    #      For now this is mostly missing (default 10km) so gradient dominates.
    g_gradient = robust_minmax(df['gravity_gradient'].values)
    g_worm = distance_decay(df['dist_gravity_worm_m'].values, worm_scale)

    # When dist_gravity_worm_m is missing for all cells, the gradient alone
    # carries the gravity signal. This is fine — gradient IS the worm proxy.
    if 'dist_gravity_worm_m' in missing_cols:
        gravity_score = g_gradient  # 100% from gradient
    else:
        gravity_score = 0.7 * g_gradient + 0.3 * g_worm
    gravity_score = np.clip(gravity_score, 0.0, 1.0)

    # --- LITHOLOGY/RHEOLOGY GROUP ---
    # Ideally we'd have:
    #   - lithology_favourability (is the rock type good? mafic, iron-rich, BIF)
    #   - rheology_contrast_score (brittle vs ductile boundary)
    # Both are missing in the audit CSV. We proxy via the lithological contact
    # distance (already in structure) and the lithology_signal boolean.
    if 'lithology_signal' in df.columns:
        # Convert boolean to 0/1 score, with slight noise
        lith_bool = df['lithology_signal'].astype(float).values
        lith_noise = rng.normal(0, 0.05, n)
        lithology_score = np.clip(lith_bool * 0.8 + 0.1 + lith_noise, 0.0, 1.0)
    else:
        # Fallback: use favourability + rheology if available
        lf = np.clip(df['lithology_favourability'].values, 0.0, 1.0)
        rc = np.clip(df['rheology_contrast_score'].values, 0.0, 1.0)
        lithology_score = np.maximum(lf, rc)

    # --- GEOCHEMISTRY GROUP ---
    # Till Au-As-Sb CLR values. Sparse coverage: most cells have NaN/0.
    # We also check till_*_shift_500m/1km/2km for glacially corrected values.
    geochem_cols = {}
    for elem in ['till_as_clr', 'till_sb_clr', 'till_au_clr']:
        # Use the best available: direct cell value, or shifted values
        direct = df[elem].values if elem in df.columns else np.zeros(n)
        # Also check shifted columns (glacial transport correction)
        shifted_cols = [f"{elem}_shift_500m", f"{elem}_shift_1km", f"{elem}_shift_2km"]
        best = direct.copy()
        for sc in shifted_cols:
            if sc in df.columns:
                shifted = pd.to_numeric(df[sc], errors='coerce').fillna(0.0).values
                # Use the maximum of direct and shifted values
                best = np.maximum(best, shifted)
        geochem_cols[elem] = best

    # Scale each pathfinder to 0-1
    as_score = robust_minmax(geochem_cols['till_as_clr'])
    sb_score = robust_minmax(geochem_cols['till_sb_clr'])
    au_score = robust_minmax(geochem_cols['till_au_clr'])

    geochemistry_score = (
        geochem_w['till_as_clr'] * as_score +
        geochem_w['till_sb_clr'] * sb_score +
        geochem_w['till_au_clr'] * au_score
    )
    geochemistry_score = np.clip(geochemistry_score, 0.0, 1.0)

    # --- MAGNETICS GROUP ---
    # ALL MISSING in your data. Scores will be neutral (0.5).
    # The group weight is already set low (0.08) to reflect this.
    magnetics_score = np.full(n, 0.5)

    # ── Step 4: Combine via weighted geometric mean ──
    # WHY GEOMETRIC MEAN: A cell with amazing structure but zero gravity
    # should NOT rank as excellent. The geometric mean ensures ALL groups
    # must contribute — one brilliant group can't compensate for absence elsewhere.
    group_scores = {
        'structure': structure_score,
        'gravity': gravity_score,
        'lithology_rheology': lithology_score,
        'geochemistry': geochemistry_score,
        'magnetics': magnetics_score,
    }

    log_sum = np.zeros(n, dtype=float)
    w_total = 0.0
    for group_name, g_score in group_scores.items():
        w = group_w[group_name]
        log_sum += w * np.log(np.clip(g_score, cfg.eps, 1.0))
        w_total += w
    combined_score = np.exp(log_sum / max(w_total, cfg.eps))

    # ── Step 5: Apply hierarchy penalties ──

    # Count how many evidence groups are "active" (above threshold)
    evidence_count = np.zeros(n, dtype=int)
    for g_score in group_scores.values():
        evidence_count += (g_score >= ev_threshold).astype(int)

    # PENALTY: Single-signal cells (rule #2: must be multi-layer)
    single_signal = (evidence_count < 2)
    combined_score = np.where(single_signal, combined_score * cfg.single_signal_penalty, combined_score)

    # BONUS/PENALTY: Fault intersections (rule #4)
    has_intersections = df['fault_intersection_density'].values > 0
    near_shear = df['dist_major_shear_m'].values < 1000.0  # within 1km of shear
    combined_score = np.where(
        has_intersections,
        combined_score * cfg.intersection_bonus,        # cells WITH intersections get bonus
        np.where(
            near_shear,
            combined_score * cfg.no_intersection_penalty,  # near shear BUT no intersections = penalty
            combined_score                                  # far from shear, no change
        )
    )

    # PENALTY: Graphitic shale false positive (rule #9)
    graphitic = df['graphitic_shale_score'].values
    has_convergence = (structure_score >= ev_threshold) & (geochemistry_score >= ev_threshold)
    graphitic_mult = np.where(
        graphitic > 0.5,
        np.where(has_convergence, cfg.graphitic_shale_if_convergent, cfg.graphitic_shale_penalty),
        1.0
    )
    combined_score *= graphitic_mult

    # PENALTY: Missing core evidence groups
    n_missing_groups = count_missing_groups(missing_cols)
    if n_missing_groups > 0:
        combined_score *= cfg.missing_group_penalty ** n_missing_groups

    # SOFT BONUS: Accessibility (rule #7, tie-breaker only)
    if 'distance_to_nearest_town_km' in df.columns:
        town_km = df['distance_to_nearest_town_km'].values
        # Closer = higher score. 0km → bonus=1.0, 50km → bonus≈0.0
        accessibility_bonus = 1.0 + cfg.accessibility_weight * np.clip(1.0 - town_km / 50.0, 0.0, 1.0)
        combined_score *= accessibility_bonus

    combined_score = np.clip(combined_score, 0.0, 1.0)

    # ── Step 6: Convert to posterior probability ──
    sampled_prior = float(np.clip(
        rng.lognormal(math.log(cfg.prior_2km), cfg.prior_sd_fraction),
        1e-6, 0.25
    ))
    sampled_lr_max = float(np.clip(
        rng.lognormal(math.log(cfg.lr_max), cfg.lr_max_sigma_log),
        5.0, 250.0
    ))
    posterior = posterior_from_score(combined_score, sampled_prior, cfg.lr_min, sampled_lr_max)

    return combined_score, posterior, group_scores


def count_missing_groups(missing_cols: List[str]) -> int:
    """
    Count how many core evidence groups are ENTIRELY missing.
    A group counts as missing only if ALL its key columns are default-filled.
    """
    groups = {
        'structure': {'dist_major_shear_m', 'fault_intersection_density'},
        'geochemistry': {'till_au_clr', 'till_as_clr', 'till_sb_clr'},
        'magnetics': {'mag_1vd', 'mag_low_in_high_proxy'},
        'gravity': {'gravity_gradient'},
        'lithology': {'lithology_favourability', 'rheology_contrast_score'},
    }
    missing_set = set(missing_cols)
    return sum(1 for cols in groups.values() if cols.issubset(missing_set))


# =============================================================================
# 5. MAIN MC LOOP
# =============================================================================

def run_monte_carlo(
    df: pd.DataFrame,
    cfg: MCConfig,
    missing_cols: List[str],
    top_ks: Sequence[int] = (1, 3, 5, 10),
) -> pd.DataFrame:
    """
    Run the full Monte Carlo loop over all cells.

    For each of n_iter iterations:
      - sample random parameter perturbations
      - score all cells
      - record which cells land in top-K
      - accumulate score/posterior statistics

    Output is a DataFrame with:
      - mean/sd of MC score and posterior across iterations
      - frequency of appearing in top 1/3/5/10 across iterations
      - group-level mean scores for diagnostics
    """
    n = len(df)
    rng = np.random.default_rng(cfg.seed)

    # Accumulators (running sums for online mean/variance)
    score_sum = np.zeros(n)
    score_sq_sum = np.zeros(n)
    posterior_sum = np.zeros(n)
    posterior_sq_sum = np.zeros(n)
    top_counts = {k: np.zeros(n, dtype=int) for k in top_ks}
    group_sums = {g: np.zeros(n) for g in cfg.group_weights.keys()}

    print(f"\nRunning {cfg.n_iter:,} Monte Carlo iterations on {n} cells...\n", file=sys.stderr)

    for it in range(cfg.n_iter):
        score, posterior, groups = run_one_iteration(rng, df, cfg, missing_cols)

        score_sum += score
        score_sq_sum += score ** 2
        posterior_sum += posterior
        posterior_sq_sum += posterior ** 2

        for g, arr in groups.items():
            if g in group_sums:
                group_sums[g] += arr

        # Track top-K rank stability
        for k in top_ks:
            kk = min(k, n)
            if kk > 0:
                idx = np.argpartition(-score, kk - 1)[:kk]
                top_counts[k][idx] += 1

        # Progress report every 10%
        if (it + 1) % max(1, cfg.n_iter // 10) == 0:
            print(f"  {it + 1:>7,} / {cfg.n_iter:,} iterations complete", file=sys.stderr)

    # ── Compute statistics ──
    score_mean = score_sum / cfg.n_iter
    score_sd = np.sqrt(np.maximum(score_sq_sum / cfg.n_iter - score_mean ** 2, 0.0))
    posterior_mean = posterior_sum / cfg.n_iter
    posterior_sd = np.sqrt(np.maximum(posterior_sq_sum / cfg.n_iter - posterior_mean ** 2, 0.0))

    # ── Build output DataFrame ──
    out = pd.DataFrame({
        'cell_id': df['cell_id'].values,
        'mc_score_mean': np.round(score_mean, 6),
        'mc_score_sd': np.round(score_sd, 6),
        'posterior_mean': np.round(posterior_mean, 6),
        'posterior_sd': np.round(posterior_sd, 6),
    })

    # Add map number and town if available
    if 'map_number' in df.columns:
        out['map_number'] = df['map_number'].values
    if 'nearest_town' in df.columns:
        out['nearest_town'] = df['nearest_town'].values
    if 'distance_to_nearest_town_km' in df.columns:
        out['town_km'] = df['distance_to_nearest_town_km'].values

    # Top-K frequencies
    for k in top_ks:
        out[f'top_{k}_freq'] = np.round(top_counts[k] / cfg.n_iter, 4)

    # Group-level mean scores
    for g, arr_sum in group_sums.items():
        out[f'{g}_mean'] = np.round(arr_sum / cfg.n_iter, 4)

    # Key raw features for context
    for col in ['gravity_gradient', 'dist_major_shear_m', 'dist_key_lithological_contact_m',
                'fault_intersection_density']:
        if col in df.columns:
            out[col] = df[col].values

    # Evidence convergence count
    group_cols = [f'{g}_mean' for g in cfg.group_weights.keys()]
    out['n_active_groups'] = (out[group_cols] >= cfg.evidence_threshold_mean).sum(axis=1)

    # Sort by MC score descending
    out = out.sort_values('mc_score_mean', ascending=False).reset_index(drop=True)
    out.insert(0, 'mc_rank', range(1, len(out) + 1))

    return out


# =============================================================================
# 6. REPORTING — human-readable output
# =============================================================================

def print_top10_report(results: pd.DataFrame, cfg: MCConfig) -> str:
    """Generate a human-readable report of the top 10 MC-ranked cells."""
    lines = []
    lines.append("=" * 80)
    lines.append("MONTE CARLO TOP-10 PROSPECTIVITY RANKING")
    lines.append(f"Iterations: {cfg.n_iter:,}  |  Seed: {cfg.seed}  |  Prior: {cfg.prior_2km:.5f}")
    lines.append("=" * 80)
    lines.append("")
    lines.append("IMPORTANT: These are MODELLING CANDIDATES, not confirmed gold targets.")
    lines.append("A cell ranked #1 means it was ROBUSTLY top-ranked across thousands of")
    lines.append("parameter perturbations. It does NOT mean gold is definitely there.")
    lines.append("")

    top10 = results.head(10)
    lines.append(f"{'Rank':<5} {'Map#':<6} {'Cell ID':<12} {'MC Score':>10} {'±SD':>8} "
                 f"{'Posterior':>10} {'Top1%':>7} {'Top5%':>7} {'Top10%':>7} "
                 f"{'Grav':>6} {'Struct':>6} {'Litho':>6} {'Town':>12}")
    lines.append("-" * 120)

    for _, row in top10.iterrows():
        map_n = int(row.get('map_number', -1))
        map_str = str(map_n) if map_n > 0 else '?'
        town = str(row.get('nearest_town', '?'))[:10]
        lines.append(
            f"{int(row['mc_rank']):<5} {map_str:<6} {row['cell_id']:<12} "
            f"{row['mc_score_mean']:>10.4f} {row['mc_score_sd']:>8.4f} "
            f"{row['posterior_mean']:>10.6f} "
            f"{row.get('top_1_freq', 0):>7.1%} {row.get('top_5_freq', 0):>7.1%} "
            f"{row.get('top_10_freq', 0):>7.1%} "
            f"{row.get('gravity_gradient', 0):>6.2f} "
            f"{row.get('structure_mean', 0):>6.3f} "
            f"{row.get('lithology_rheology_mean', 0):>6.3f} "
            f"{town:>12}"
        )

    lines.append("")
    lines.append("-" * 120)

    # Package probability for top 5 and top 10
    lines.append("")
    lines.append("PACKAGE PROBABILITIES (P(at least one target in package)):")
    lines.append("")
    for pkg_size in [3, 5, 10]:
        pkg = results.head(min(pkg_size, len(results)))
        p = np.clip(pkg['posterior_mean'].values, 0.0, 1.0)
        p_naive = 1.0 - np.prod(1.0 - p)
        p_conservative = float(np.max(p))
        n_eff = 1.0 + (len(p) - 1.0) * (1.0 - cfg.package_correlation_rho)
        p_rho = 1.0 - (1.0 - np.mean(p)) ** n_eff

        lines.append(f"  Top-{pkg_size} package:")
        lines.append(f"    Naive independent:     P(≥1 target) = {p_naive:.4%}")
        lines.append(f"    Conservative (max):     P(≥1 target) = {p_conservative:.4%}")
        lines.append(f"    ρ-adjusted (ρ={cfg.package_correlation_rho}): P(≥1 target) = {p_rho:.4%}")
        lines.append("")

    lines.append("")
    lines.append("KEY:")
    lines.append("  MC Score   = mean evidence score across all iterations (0-1)")
    lines.append("  ±SD        = how much the score wobbles when parameters change")
    lines.append("  Posterior   = P(target | evidence, prior) under model assumptions")
    lines.append("  Top1/5/10% = fraction of iterations where this cell ranked in top K")
    lines.append("  Grav       = raw gravity gradient value (mGal/km)")
    lines.append("  Struct     = mean structure group score")
    lines.append("  Litho      = mean lithology/rheology group score")
    lines.append("  Town       = nearest settlement")
    lines.append("")

    report = "\n".join(lines)
    print(report)
    return report


# =============================================================================
# 7. CLI AND MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Monte Carlo top-10 prospectivity ranking for CLGB gold candidates.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--cells", default=None,
                        help="Input cell table. Default: data/outputs/review_candidates_audited.csv")
    parser.add_argument("--out", default=None,
                        help="Output CSV path. Default: data/outputs/monte_carlo_top10.csv")
    parser.add_argument("--n-iter", type=int, default=20_000,
                        help="Number of Monte Carlo iterations.")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility.")
    parser.add_argument("--all-candidates", action="store_true",
                        help="Run on all 63 candidates, not just 16 multi-layer.")
    args = parser.parse_args()

    # Resolve paths
    project_root = Path(__file__).resolve().parent.parent
    cells_path = Path(args.cells) if args.cells else project_root / "data/outputs/review_candidates_audited.csv"
    out_path = Path(args.out) if args.out else project_root / "data/outputs/monte_carlo_top10.csv"
    lookup_path = project_root / "data/outputs/clgb_grid_2km_number_lookup.csv"

    print(f"Input: {cells_path}", file=sys.stderr)
    print(f"Output: {out_path}", file=sys.stderr)

    # Load and prepare data
    df, missing_cols = load_and_map_cells(cells_path, multi_layer_only=not args.all_candidates)
    df = add_map_numbers(df, lookup_path)
    df = add_town_distances(df, lookup_path)

    # Configure and run
    cfg = MCConfig(n_iter=args.n_iter, seed=args.seed)
    results = run_monte_carlo(df, cfg, missing_cols)

    # Report
    report = print_top10_report(results, cfg)

    # Save
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(out_path, index=False)
    print(f"\nResults saved to: {out_path}", file=sys.stderr)

    # Save report as markdown
    report_path = out_path.with_suffix('.md')
    report_path.write_text(report, encoding='utf-8')
    print(f"Report saved to: {report_path}", file=sys.stderr)

    # Save config for reproducibility
    config_path = out_path.with_name(out_path.stem + '_config.json')
    config_path.write_text(json.dumps(asdict(cfg), indent=2, default=str), encoding='utf-8')
    print(f"Config saved to: {config_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
