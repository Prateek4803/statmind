# Multistage Dataset Schema (Session M1)

Foundation for multistage / dependency-aware monitoring (Prof. Paynabar
feedback): model a production line as K dependent stages where an upstream
change propagates downstream with lag and attenuation, so a downstream alarm
can be traced to its true upstream origin.

## Canonical format — LONG (one row per unit × stage)
| column | type | meaning |
|---|---|---|
| `unit_id` | int | the unit/wafer/part flowing through the line (1..N), in process order |
| `stage_index` | int | stage position in the line (1..K), 1 = first |
| `stage_name` | str | human name, e.g. `S3_Deposition` |
| `value` | float | the quality characteristic measured at that stage for that unit |
| `timestamp` | ISO 8601 | when the unit was measured at that stage |

## Convenience format — WIDE (one row per unit, one column per stage)
`unit_id, S1_Incoming, S2_Clean, S3_Deposition, …` — produced by `to_wide()`.
Wide is what correlation/lag analysis consumes; long is the ingestion contract
(and what a streaming source would emit per event).

## Causal model
`x[k,u] = base[k] + Σ_j coupling[j→k]·(x[j, u−lag[j→k]] − base[j]) + fault + noise`

Default coupling graph (chain + two skip links so a stage-1 change surfaces at
stage 3 AND stages 7-8 — the professor's exact example):
`1→2→3→4→5→6→7→8`, plus `1⇢3` (lag 2) and `3⇢7` (lag 3).

## Ground truth (for testing M2)
`generate_multistage_dataset()` returns `(long_df, ground_truth)`. The
`ground_truth.faults[*].downstream_arrivals` records, for each injected fault,
which downstream stages it reaches, at what cumulative lag and gain — so the M2
attribution engine can be scored: "given the stage-7 excursion, did it name
stage 1 at lag 5?"

## Demo datasets (static/samples/)
- `multistage_line_stage1_fault.csv` — wide; stage-1 step fault, units 150+.
- `multistage_line_stage4_fault.csv` — wide; mid-line (stage-4) fault, a
  different origin to attribute (must NOT be blamed on stages 1-3).
- `multistage_line_long_format.csv` — long; canonical ingestion schema.

## Not in scope for M1 (gated behind the Paynabar meeting)
Attribution engine (M2), CAPA integration (M3), streaming ingestion (M4). M1 is
data + schema + verified ground truth only.
