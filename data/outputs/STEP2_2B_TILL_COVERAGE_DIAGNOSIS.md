# Step 2.2B Till Coverage Diagnosis

This diagnoses why the strict interim Au-As-Sb till CLR model has sparse coverage.

## Dataset Summary

| dataset | total | full AOI | CLGB | legal/restriction-clear | Au | As | Sb | used/excluded | should include interim? |
|---------|-------|----------|------|-------------------------|----|----|----|---------------|-------------------------|
| `till_geochemistry_almr_511p.gpkg` | 4753 | 4753 | 3594 | 841 | NO | NO | NO | EXCLUDED | NO |
| `till_geochemistry_almr_519u.gpkg` | 4747 | 4747 | 3617 | 845 | YES | NO | NO | EXCLUDED_FROM_STRICT_CLR | NO for strict Au-As-Sb CLR; YES for a future Au-only log ablation if explicitly allowed. |
| `till_geochemistry_supraregional.gpkg` | 50 | 50 | 38 | 10 | YES | YES | YES | USED | YES |

## Field Details

### till_geochemistry_almr_511p.gpkg

- Path: `/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/till_geochemistry_almr_511p.gpkg`
- Medium / fraction: MATERIAL: till=4753 | FRACTION: sieved, <0.06 mm (fine)=4753 | SOIL_HORIZON: C=4753
- Au fields: 
- As fields: 
- Sb fields: 
- Units: 
- Detection / qualifier fields: 
- Decision: EXCLUDED
- Why: No numeric Au/As/Sb marker fields found.

### till_geochemistry_almr_519u.gpkg

- Path: `/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/till_geochemistry_almr_519u.gpkg`
- Medium / fraction: MATERIAL: till=4747 | FRACTION: sieved, <0.06 mm (fine)=4747 | SOIL_HORIZON: C=4747
- Au fields: AU_PPM_519U
- As fields: 
- Sb fields: 
- Units: ppm
- Detection / qualifier fields: AU_519U_T
- Decision: EXCLUDED_FROM_STRICT_CLR
- Why: Contains usable Au but lacks As/Sb, so it cannot support an Au-As-Sb CLR composition without mixing unmatched surveys.

### till_geochemistry_supraregional.gpkg

- Path: `/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/till_geochemistry_supraregional.gpkg`
- Medium / fraction: AINES: moreeni=50 | LAJITE: hieno lajite, <0.06 mm=50
- Au fields: AU_PPM_519U;AU_PPM_900N
- As fields: AS_PPM_312P;AS_PPM_511P;AS_PPM_900N
- Sb fields: SB_PPM_312P;SB_PPM_511P;SB_PPM_900N
- Units: ppm
- Detection / qualifier fields: AU_519U_T;AU_900N_T;AS_312P_T;AS_511P_T;AS_900N_T;SB_312P_T;SB_511P_T;SB_900N_T
- Decision: USED
- Why: Contains numeric Au, As and Sb in the same till sample table; valid for strict three-marker CLR after censoring imputation.

## Diagnosis

- Strict usable Au-As-Sb samples: 50
- Strict usable Au-As-Sb samples inside CLGB: 38
- Strict usable Au-As-Sb samples inside legal/restriction-clear cells: 10
- The dense `almr_519u` table supplies Au but not As/Sb.
- The dense `almr_511p` table does not supply Au/As/Sb pathfinder fields.
- The sparse supraregional table is the only local till dataset with Au, As and Sb together in the same sample records.
- Therefore the 1% 2 km cell coverage is expected for the strict three-marker CLR model and was not caused by accidentally excluding a dense complete Au-As-Sb till table.

## Recommendation

- Keep the current strict Au-As-Sb CLR layer as sparse, high-specificity geochemistry.
- Add a separate future ablation for dense Au-only `almr_519u` as `till_au_log_dense` only if the model explicitly allows unmatched per-element surveys.
- Do not mix stream sediment Bi or unmatched Bi into the till model.
