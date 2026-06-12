# Step 2.2B Review Candidate Audit

These are review candidates only. They are not targets and no target memos are allowed from this audit.

## Thresholds Used

- Gravity support: `gravity_gradient >= 1.815` (75th percentile of all 2 km cells).
- Structure/lithology support: within 2 km of major structure, nonzero structure intersection density, or within 1 km of a lithological contact.
- Till support: any available Au/As/Sb CLR value above its 75th percentile among non-null till cells: {'till_au_clr': -3.560406703535466, 'till_as_clr': 3.1538146739790065, 'till_sb_clr': 3.7439858087529343}.
- Single-signal hallucination: top approximate feature contribution >= 75%.

## Status Counts

| audit_status | cells |
|--------------|-------|
| structure_only_candidate | 47 |
| multi_layer_review_candidate | 16 |

## Summary

- Review candidates audited: 63
- Multi-layer review candidates: 16
- Gravity-only candidates: 0
- Till-only candidates: 0
- Structure-only candidates: 47
- Single-signal hallucinations: 0
- Allowed for target memo: NO.

## Top Rows by Geology Composite / Existing Review Order

| cell_id | lat | lon | audit_status | model | baseline | gravity_gradient | till present | top contributing features | flags |
|---------|-----|-----|--------------|-------|----------|------------------|--------------|---------------------------|-------|
| g2k_00730 | 67.65164 | 24.05322 | structure_only_candidate | 0.0025 | 0.6441 | 1.336 | False | dist_major_shear:0.3474;dist_key_lithological_contact:0.2222;gravity_gradient:0.0824 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb;no_structural_intersection |
| g2k_00779 | 67.67707 | 26.36300 | multi_layer_review_candidate | 0.0002 | 0.3599 | 2.931 | False | dist_major_shear:0.3272;dist_key_lithological_contact:0.2192;gravity_gradient:0.1837 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_00780 | 67.67725 | 26.41018 | multi_layer_review_candidate | 0.0002 | 0.2755 | 2.975 | False | dist_major_shear:0.3131;dist_key_lithological_contact:0.2176;gravity_gradient:0.1865 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_00802 | 67.67040 | 24.09809 | structure_only_candidate | 0.0003 | 0.8387 | 1.268 | False | dist_major_shear:0.3533;dist_key_lithological_contact:0.2201;gravity_gradient:0.0780 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb;no_structural_intersection |
| g2k_01314 | 67.80695 | 24.79335 | multi_layer_review_candidate | 0.0102 | 0.4824 | 3.112 | False | dist_major_shear:0.3388;dist_key_lithological_contact:0.2065;gravity_gradient:0.1951 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01383 | 67.82357 | 24.69677 | structure_only_candidate | 0.0006 | 0.7315 | 1.485 | False | dist_major_shear:0.3505;dist_key_lithological_contact:0.2174;gravity_gradient:0.0919 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01384 | 67.82423 | 24.74422 | multi_layer_review_candidate | 0.005 | 0.92 | 1.884 | False | dist_major_shear:0.3551;dist_key_lithological_contact:0.2217;gravity_gradient:0.1172 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01385 | 67.82488 | 24.79166 | multi_layer_review_candidate | 0.0001 | 0.8909 | 2.713 | False | dist_major_shear:0.3545;dist_key_lithological_contact:0.2211;gravity_gradient:0.1698 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01386 | 67.82551 | 24.83911 | multi_layer_review_candidate | 0.0011 | 0.6564 | 2.764 | False | dist_major_shear:0.3479;dist_key_lithological_contact:0.2150;gravity_gradient:0.1730 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb;no_structural_intersection |
| g2k_01455 | 67.84216 | 24.74248 | structure_only_candidate | 0.0025 | 0.8537 | 1.347 | False | dist_major_shear:0.3537;dist_key_lithological_contact:0.1929;gravity_gradient:0.0830 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01511 | 67.84871 | 24.02835 | structure_only_candidate | 0.0003 | 0.77 | 1.083 | False | dist_major_shear:0.3516;dist_key_lithological_contact:0.2211;gravity_gradient:0.0663 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb;no_structural_intersection |
| g2k_01547 | 67.87080 | 25.73916 | structure_only_candidate | 0.016 | 0.4213 | 1.534 | False | dist_major_shear:0.3338;dist_key_lithological_contact:0.2057;gravity_gradient:0.0949 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01548 | 67.87116 | 25.78672 | structure_only_candidate | 0.0015 | 0.6685 | 1.529 | False | dist_major_shear:0.3483;dist_key_lithological_contact:0.1987;gravity_gradient:0.0946 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01582 | 67.86662 | 24.02606 | structure_only_candidate | 0.0003 | 0.9646 | 0.8539 | False | dist_major_shear:0.3559;dist_key_lithological_contact:0.2205;gravity_gradient:0.0518 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb;no_structural_intersection |
| g2k_01618 | 67.88873 | 25.73819 | structure_only_candidate | 0.0002 | 0.8211 | 1.312 | False | dist_major_shear:0.3529;dist_key_lithological_contact:0.2197;fault_intersection_density:0.0821 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01619 | 67.88909 | 25.78579 | structure_only_candidate | 0.0019 | 0.5556 | 1.255 | False | dist_major_shear:0.3433;dist_key_lithological_contact:0.2107;fault_intersection_density:0.0821 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01620 | 67.88944 | 25.83339 | structure_only_candidate | 0.0002 | 0.7567 | 1.2 | False | dist_major_shear:0.3512;dist_key_lithological_contact:0.2181;fault_intersection_density:0.0821 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01688 | 67.90630 | 25.68958 | structure_only_candidate | 0.0037 | 0.6651 | 1.226 | False | dist_major_shear:0.3482;dist_key_lithological_contact:0.2019;fault_intersection_density:0.0821 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01689 | 67.90667 | 25.73721 | structure_only_candidate | 0.0019 | 0.5886 | 1.071 | False | dist_major_shear:0.3450;dist_key_lithological_contact:0.2123;fault_intersection_density:0.0821 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01690 | 67.90703 | 25.78485 | structure_only_candidate | 0.0007 | 0.6794 | 1.012 | False | dist_major_shear:0.3487;dist_key_lithological_contact:0.2158;fault_intersection_density:0.0821 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01691 | 67.90737 | 25.83249 | structure_only_candidate | 0.0 | 0.3322 | 1.138 | False | dist_major_shear:0.3233;dist_key_lithological_contact:0.2201;fault_intersection_density:0.0821 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01759 | 67.92423 | 25.68857 | structure_only_candidate | 0.0007 | 0.6578 | 1.286 | False | dist_major_shear:0.3479;dist_key_lithological_contact:0.2150;fault_intersection_density:0.0821 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01760 | 67.92460 | 25.73624 | structure_only_candidate | 0.0002 | 0.8125 | 0.9957 | False | dist_major_shear:0.3527;dist_key_lithological_contact:0.2195;fault_intersection_density:0.0821 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01830 | 67.94216 | 25.68755 | structure_only_candidate | 0.0003 | 0.9624 | 1.339 | False | dist_major_shear:0.3559;dist_key_lithological_contact:0.2224;gravity_gradient:0.0825 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |
| g2k_01831 | 67.94254 | 25.73526 | structure_only_candidate | 0.0002 | 0.776 | 1.153 | False | dist_major_shear:0.3518;dist_key_lithological_contact:0.2186;fault_intersection_density:0.0821 | magnetics_low_confidence;no_numeric_mag_1vd;no_defensible_mag_low_in_high;no_cell_till_au_as_sb |

## Interpretation

- Most review cells have no till value because till coverage is sparse; absence of till support is not evidence against a cell, but it prevents multi-layer geochemical convergence.
- Numeric magnetics are still missing, so no candidate has magnetic support.
- Candidate statuses should not be upgraded until ablation and top-k validation are stronger.
