# StatMind Design Tokens — one-page reference (Session 4)

Single source of truth: the `:root` block in `static/index.html`
(mirrored values in `static/landing.html`). Every rule below is enforced by
what exists in that block — if you need a value, use a token, never a raw hex.

## Semantic color contract (regulated-industry rule)
| Token | Value | Reserved meaning — NEVER decorative |
|---|---|---|
| `--alarm` / `--red` | #f47272 | Out-of-spec, SPC alarm, Critical severity |
| `--warn` / `--amber` | #f0b429 | Marginal, Major severity, caution |
| `--ok` / `--green` | #34d980 | Pass, in-control, capable |
| `--info` / `--blue` | #60a5fa | Neutral information |

If red appears anywhere in the UI, something is statistically wrong. That is
the contract with a quality engineer. Prefer the semantic aliases in new code.

## Accessibility
All text tokens meet WCAG 2.1 AA (≥4.5:1) against every surface `--bg`..`--bg4`,
verified programmatically (2026-07-07). Worst cases: `--text3` 5.03, `--red` 4.86.
If you add a token or surface, re-run the contrast check before merging.

## Chart series palette — colorblind-safe (Okabe-Ito)
`--chart-1`..`--chart-8` and `window.SM_CHART_PALETTE` (keep in sync).
Use IN ORDER for multi-series charts. ~8% of male engineers are red-green
colorblind; verdict semantics still use `--ok/--warn/--alarm`, but series
identity must never depend on red-vs-green alone.

## Type scale (5 sizes — do not invent a 6th)
`--fs-xs` 12 · `--fs-sm` 13 · `--fs-md` 16 · `--fs-lg` 20 · `--fs-xl` 28
UI face: `--font`. Numbers: `--mono` with `font-variant-numeric:tabular-nums`
(already applied to `.mv` metric values and `.data-table td`) so columns of
Cpk values align digit-for-digit.

## Spacing — 4px grid
`--sp-1` 4 · `--sp-2` 8 · `--sp-3` 12 · `--sp-4` 16 · `--sp-5` 24 · `--sp-6` 32
Cards: radius `--card-r` (12px), border `--border`/`--border2`.

## Rules for new UI work (Session 5+)
1. No raw hex in new code — tokens only.
2. Semantic colors carry meaning; use the aliases.
3. One primary action per screen; verdict first, statistics second.
4. Numbers right-aligned, tabular; labels `--text3`; values `--text`.
