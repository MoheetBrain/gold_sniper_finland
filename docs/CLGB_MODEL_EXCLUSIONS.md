# CLGB Model Exclusions — what is NOT a positive label

The Step 2 model targets **Central Lapland Greenstone Belt orogenic (shear-hosted)
gold**. Mixing other gold-bearing deposit types into the positive labels would teach
the model the wrong signatures and produce hallucinated targets. We therefore filter
FODD `GENETIC_TYPE` and keep **only orogenic gold**.

## Included (positive)

- `Orogenic gold (± Cu,Co)` — structurally controlled, shear/fault-hosted gold. The
  CLGB type example: Suurikuusikko/Kittilä, Ikkari, Pahtavaara, Saattopora, Kutuvuoma.

## Excluded (recorded in `excluded_non_clgb_labels.gpkg`, never positives)

| excluded type | why excluded | example |
|---------------|--------------|---------|
| Iron oxide-copper-gold (IOCG) | different mineral system / controls | Lauttaselkä |
| Au-U (Rompas-style) | uranium-associated, atypical chemistry/structure | Rompas |
| Au-Co-U-REE (Kuusamo-style) | polymetallic, different alteration/host | Kuusamo belt |
| Volcanogenic massive sulphide (VMS), gold-rich | syn-volcanic, not orogenic | — |
| Epithermal | shallow, volcanic-hosted | — |
| Porphyry / intrusion-related | intrusion-centred | — |
| Skarn | contact-metasomatic | — |
| Placer / paleoplacer | secondary/detrital gold (incl. gold-panning) | Lapland placers |
| Untyped / unknown genetic type | cannot confirm it is orogenic | Mäkärärova |

## Reliability ranking of positives (FODD `STATUS`)

1. **mine** (active/closed) — highest confidence.
2. **deposit / prospect** (not exploited).
3. *(occurrence / showing — lower; none typed-in this AOI.)*
4. **Till-anomaly-only occurrences are NOT positives** unless bedrock-confirmed.

## Why this matters

Unknown ground is **unlabelled, not negative** (see background sampling). And positives
must be a clean, single-system set. If later we want to model IOCG or Kuusamo-type
systems, that is a **separate model with its own labels**, not a contaminant here.
