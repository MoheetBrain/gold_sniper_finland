# Interim Till Au-As-Sb Report

Input till file: `/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/till_geochemistry_supraregional.gpkg`

## Markers Used

- Au: YES (`AU_PPM_519U`)
- As: YES (`AS_PPM_511P`)
- Sb: YES (`SB_PPM_511P`)
- Bi: NULL/optional. No till Bi field was used; stream-sediment Bi was not substituted.

## Transform

- Transform used: CLR
- Reason: Au/As/Sb are positive after half-detection-limit imputation.
- AU: 4 values imputed to half min positive (3e-05)
- AS: 22 values imputed to half min positive (0.05)
- SB: 8 values imputed to half min positive (0.005)

## Up-Ice Ablation

- Scenario columns created for raw, 500 m, 1 km and 2 km up-ice shifts.
- Glacial striae were used within 25 km where available; otherwise nearby lineation orientation was used; otherwise the config default was used.
- Flow direction sources among samples: {'nearest_glacial_stria_25km': 42, 'nearest_glacial_lineation_25km': 8}
- No single shift is treated as correct; these are ablation scenarios.

## Output Coverage

- Till samples processed: 50
- 2 km cells: 3798
- till_au_clr: 1.0% non-null cells
- till_as_clr: 1.0% non-null cells
- till_sb_clr: 1.0% non-null cells

## Limitations

- Au/As/Sb CLR uses the sparse supraregional till table because it contains all three interim markers in the same till samples.
- The denser Au-only till layer was not mixed into CLR because matching As/Sb values are not present for those samples.
- Striae direction semantics and lineation orientation are treated as provisional; validation must compare raw and shifted scenarios rather than trusting one shift.
