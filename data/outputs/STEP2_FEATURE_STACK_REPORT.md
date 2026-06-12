# Step 2 Feature Stack Report

Built the Step 2.2A CLGB feature stack with explicit nulls and provenance.

## Core Feature Availability

| # | feature slot | status | provenance | coverage |
|---|--------------|--------|------------|----------|
| 1 | `dist_major_shear` | REAL | GTK structures (1:1M) | 100.0% |
| 2 | `fault_intersection_density` | REAL | GTK structures (1:1M) | 100.0% |
| 3 | `dist_key_lithological_contact` | REAL | GTK bedrock boundaries (1:1M) | 100.0% |
| 4 | `mag_1vd OR mag_visual_proxy_low_confidence` | NULL | NULL - local GTK aeromagnetic ECW validation/processing produced no defensible values; NULL - local GTK aeromagnetic ECW validation/processing produced no defensible values | 0.0% |
| 5 | `mag_low_in_high_proxy` | NULL | NULL - local GTK aeromagnetic ECW validation/processing produced no defensible values | 0.0% |
| 6 | `gravity_gradient` | REAL | local Bouguer BA_FIN.XYZ gradient sampled to 2 km grid | 100.0% |
| 7 | `till_au_clr OR till_au_log` | REAL | GTK till geochemistry supraregional Au-As-Sb ablation; NULL - GTK till geochemistry supraregional Au-As-Sb ablation produced no defensible values | 1.0% |
| 8 | `till_as_clr OR till_as_log` | REAL | GTK till geochemistry supraregional Au-As-Sb ablation; NULL - GTK till geochemistry supraregional Au-As-Sb ablation produced no defensible values | 1.0% |
| 9 | `till_sb_clr OR till_sb_log` | REAL | GTK till geochemistry supraregional Au-As-Sb ablation; NULL - GTK till geochemistry supraregional Au-As-Sb ablation produced no defensible values | 1.0% |
| 10 | `till_bi_clr (optional)` | OPTIONAL_NULL | NULL - GTK till geochemistry supraregional Au-As-Sb ablation produced no defensible values | 0.0% |

## Counts

- Real features: 7
- Low-confidence proxy features: 0
- Null features: 2
- Optional/null features: 1
- Feature quality sufficient for validation: YES

## Notes

- Bi is no longer required for this interim run and remains optional/null.
- Magnetics is visual-only/unreadable in this environment, so no numeric magnetic features were fabricated.
- Gravity is real but regional: Bouguer XYZ, 2.5 km source grid, sampled to 2 km cells.
- Till Au/As/Sb are real but sparse because CLR uses only till samples containing all three markers.
