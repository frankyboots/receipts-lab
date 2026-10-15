# Study: co-rally-tax

Wiki page: https://github.com/receiptsandregimes/research-wiki/blob/main/studies/co-rally-tax.md
Claims tested: `rotation-onset-co-rally` (primary); contextualizes `qs-rotation-gfc-divergence`
Status: protocol-only

Data availability (2026-10-12): all sources fetched KEYLESS from this host. Full-history
gold = DAILY LBMA PM fix, 1968-04→current, from two independently validated
public mirrors (fetch-script header: 0.0004% mean dev vs FRED-era dump,
0.06% median vs World Bank Pink Sheet monthly means, 0.36% vs GC=F month-end).
Signals run on month-END FIXES — protocol-consistent. Pink Sheet monthly
averages kept as cross-check only (an average smooths intra-month paths and
shifts crossover dates — it does not generate legit signals).


## 2026-10-12 DATA AMENDMENT (supersedes gold-source text below)

The LBMA daily-fix mirror this study was seeded on FROZE at 2026-02-25 — its
upstream (prices.lbma.org.uk/json) is bot-walled and every public mirror died
with it; free live fix data no longer exists. Gold leg is now a COMPOSITE per
wiki entities/lbma-gold-price.md: frozen fix history 1968-04->2026-02 (sha256
86057834bd6fca53…) + seam-normalized GLD total-return live extension, GC=F
month-ends second opinion, Pink Sheet monthly-average cross-check. Signals on
within-series returns only — no level splicing (measured GC=F-vs-fix month-end
basis: median 0.36%, max 4.75% @ 2026-01). Fetch script updated (adds GLD +
daily legs; chunked Yahoo daily to dodge a silent monthly-downgrade bug).
## Data validation 2026-10-15 (receipts-lab-data-validation gate)

Battery: `code/verify_data.py` (read-only on `data/`; offline by default,
`--live` re-fetches every source; exit 1 while open defects exist). First full
gate run. Verdict: **FAIL — 4 fetch-path (F) defects, 0 (S)**. The fetch script
is SHARED by the 3 sibling studies (identical sha `854664c0…`, their `data/`
still empty) — fix once via §8 data-fix SPEC, re-fetch all, revalidate; do not
fetch siblings until the DFX fix lands.

Per-file verdicts:

| file | verdict | evidence |
|---|---|---|
| lbma_pm_fix_daily.csv | PASS | frozen 1968-04-01→2026-02-25, 14,544 rows, clean (max gap 7d); sha256 pin **MATCH** on live re-download |
| lbma_pm_fix_fred_mirror.csv | PASS | mean dev vs primary 0.0004% over 12,776 common days (claim 0.0004% ✓); 494 `.` placeholders = source property; single-day disagreement 1968-05-16 (41.25 vs 42.25) |
| gold_monthly_eco3min.csv | PASS | 801 mo complete 1960-01→2026-09; == Pink Sheet xlsx to 0.000000%; live re-download byte-identical |
| CMO-Historical-Data-Monthly.xlsx | PASS | == eco3min over all 801 shared months; live re-download byte-identical |
| shiller_ie_data.xls | PASS | P decoded 1871-01→2023-09; P = monthly AVERAGE of daily closes, exact 12/12 mo (2022-09→2023-08); final served row 2023-09 anomalous (+2.42% vs true Sep mean) — drop it; file frozen as served |
| tb3ms_monthly.csv | PASS | complete 1934-01→2026-09, no gaps (fetch header's "1950 →" is WRONG — fix with DFX); live re-fetch: fresh FRED pull value-identical on all 1,113 shared months (0 mismatches, max dev 0.0, both end 2026-09; bytes differ only in the renamed header), pulled during the pre-outage window after which FRED's edge went dark from this host |
| gld_daily.csv | PASS | clean, max gap 5d, no dups |
| gold_daily_gcf.csv | PASS | clean, max gap 5d, no dups |
| gld_tr_monthly.csv | (F1) | dup running month (2026-10 ×2, both intraday snapshots); values otherwise == daily month-ends 0.00000000% over 262 mo |
| spy_tr_monthly.csv | (F1) | dup running month ×2; otherwise complete 405 mo |
| gold_monthly_gcf.csv | (F1)+(F2) | **46/314 months MISSING** (silent None-close drop) incl. composite seam months 2026-02, 2026-03; dup running month; stored values == daily month-ends 0.00000000% (267 shared mo) — values fine, coverage broken |
| spx_price_monthly.csv | (F3)+(F4) | **169 rows over 503-month span**: Yahoo serves `^SPX` as QUARTER-end bars only via `range=max` monthly (reproduced live twice on 2026-10-15) stored under a monthly name; values = close of the 3-month window STARTING at the label (167/168 exact vs daily closes) — mislabeled AND sparse, unusable as monthly closes |

Defect classes (all in the shared fetch script → §8 data-fix SPEC, DFX-1..4):
- **F1** monthly fetcher: no dedupe — Yahoo returns the running month twice with
  different intraday snapshots (mechanism reproduced live: GC=F 4107.9/4166.3).
- **F2** monthly fetcher: silent None-close drop, no guard (GC=F lost 46 months,
  exactly where the seam needed them). Month-ends reconstructable from the
  complete daily leg; fix = backfill-from-daily or loud guard.
- **F3** no per-file monthly coverage guard — quarterly bars silently stored
  under a monthly name. Guard must be per-file, not per-fetch-run (ETF/futures
  monthly bars were complete).
- **F4** ^SPX quarterly bar values mislabeled (+2-month window shift). Verified
  fix route: chunked daily fetch (10,780 rows, no downgrades) → month-end resample.

Reproduced claims (all re-derived from stored bytes + live pulls, 2026-10-15):
- frozen LBMA sha256 `86057834bd6fca53…` MATCH; span + last fix 5191.55 @ 2026-02-25 ✓
- fix-vs-FRED-dump mean 0.0004% ✓ (12,776 days; 258 differ at all; max 2.37% = 1968-05-16 only)
- fix monthly MEANS vs Pink Sheet: median 0.0649% (claim 0.06% ✓; max 10.58% @ 1980-12)
- GC=F-vs-fix month-end basis, monthly-file leg: 260 mo, median 0.3579%, p90
  1.2013%, max 4.7522% @ 2026-01 (claim 0.36%/1.21%/4.75% ✓). The "260" = the
  gappy monthly file's coverage (itself F2); complete daily-leg basis = 304 mo,
  median 0.3463%, p90 1.1789%, same max @ 2026-01.
- eco3min == xlsx 0.000000% ✓; GLD monthly == daily ME 0.00000000% ✓; GC=F
  monthly == daily ME 0.00000000% ✓
- TB3MS vs fresh FRED pull: 1,113/1,113 months value-identical (0 mismatches);
  all 5 static sources re-downloaded byte-identical (fan-out run 05:15 + parent
  re-run — two independent confirmations each; FRED unreachable from this host
  after ~05:17, timing out 0 bytes — transient, re-attempt via `--live`)
- Shiller P = monthly average of dailies ✓; Shiller→Yahoo seam at 2023-09 mixes
  average-vs-close measures (README already mandates level-normalized stitch + returns)
- live: ^SPX quarterly downgrade AND dup-running-month both reproduced fresh;
  GC=F/GLD monthly + daily interiors byte-stable; SPY interior shows only
  ppm-scale adjclose anchor drift (max 0.000120% over 404 mo)

**(A) hazards for the SPEC (Constraints + I/O matrix):**
1. GLD leg is NAV-per-share — 2026-02 ME 483.75 vs fix 5191.55 (−90.7% level
   gap). Composite = within-series RETURNS only (ratio-normalized at the
   2026-02/03 seam; GLD covers both months); never level-splice.
2. Shiller P is a monthly AVERAGE vs Yahoo month-END closes — 2023-09 stitch
   mixes measures; EXCLUDE Shiller's final served row (2023-09, anomalous +2.42%).
3. GC=F is a second opinion (basis median 0.36%, p90 1.20%, max 4.75% @ 2026-01;
   @ seam 2026-02: +1.085%) — no level splicing vs the fix leg.
4. Running month's row is an MTD snapshot, never a month-end — drop at analysis
   time (its dup is F1).
5. Pink Sheet = monthly AVERAGE: cross-check only, never signal-generating
   (confirmed: diverges from fix means in fast markets, max 10.58% @ 1980-12).
6. LBMA eur column zero before 1999-01 (pre-euro; unused by signals).
7. SPY adjclose anchor drift between snapshots is ppm-scale (≤0.000120%) —
   immaterial at signal precision.

Record corrections surfaced by the gate: fetch header TB3MS span "1950 →" →
actual 1934-01; README Engine "Python 3.14" → study venv is 3.11.16 (pandas
3.0.6 / xlrd 2.0.2 / openpyxl 3.1.5 unchanged). Fix both with the DFX edit.

Gate status: **FAIL** (open F1–F4). Next: §8 data-fix SPEC (DFX-1..4) → build →
re-fetch → re-run this battery green → study spec. (A) hazards above are for
that spec regardless of fix outcome.

## Disclosure block (required before any number is published)

- **Universe:** gold + S&P 500 (price AND total-return variants), 3-month
  T-bills for the dual-momentum-with-cash leg. Strategies compared: hold-both
  50/50, ratio-rotation (`gold-spx-rs-ratio-rotation`), dual momentum with
  per-asset absolute filters.
- **Period:** 1971-08 → present, monthly. The 1968 LBMA-peg episode is
  discussed qualitatively only — no reliable monthly SPX-vs-peg series, and
  Frank's Pool collapse-date citation is pending verification (wiki caveat
  carried forward; do not quote it until checked).
- **Data:** `code/fetch_gold_spx_bills.py` (source + download date in header;
  `data/` gitignored). Gold: DAILY LBMA PM fix (1968-04→, two
  triple-validated public mirrors — fetch-script header). **Status:** wiki
  named FRED `GOLDPMGBD228NL`; its official feeds are all dead (FRED dropped
  the IBA series 2022-01-31; Nasdaq Data Link delisted the LBMA datasets,
  verified 2026-10-12) but the fix is RESTORED — the onset analysis 1971→
  uses real month-end fixes (protocol intact; Pink Sheet monthly averages are
  a cross-check only — averages do not generate legit signals).
  SPX price: Shiller 1871→2023 + Yahoo `^SPX` stitch
  (level-normalized at seam); TR: Shiller dividends pre-1993, SPY adj close
  after; bills: FRED `TB3MS`.
- **Costs:** 10 bps per switch on all rotation legs. No leverage.
- **Engine:** Python 3.14 + pandas 3.0.6 + xlrd 2.0.2 + openpyxl 3.1.5
  (`requirements.txt`);
  fetch script stdlib-only. Analysis scripts land in `code/`.

## Protocol

Onset definition — PRE-REGISTERED, no hindsight labels: month t is a
rotation onset if BOTH assets make a new trailing-12-month high at t AND at
least one had been >10% below its 24-month high at t−6. The 10%/6mo knobs may
be varied in a sensitivity grid, but the base definition is fixed before
looking at results.

1. Enumerate onsets 1971+; for each, forward 6/12-mo returns of gold, SPX,
   50/50, ratio-rotation, and dual-momentum-with-cash on the same pair.
2. Co-rally months table: % of onset-window months where both rise together;
   rotation's realized position (the faster riser) vs 50/50 — the tax.
3. Post-onset divergence: after how many months does one-asset dominance
   reassert? Measure both sides (where rotation loses AND where it earns).
4. Report the full distribution of onsets, not a cherry-picked episode list.

Question targets: `both-assets-down-regimes` (mirror image, same correlation
machinery), `does-the-cash-leg-earn-its-keep` (per-asset vs shared absolute
filter).

**No signal-peeking:** positions form on prior month-end data, executed the
following month. Onset detection at t may only inform the position held from
t+1.

## Results

(pending — no code run yet)

## Verdict → wiki

(update the wiki study page: Results, Verdict, claim status/confidence changes,
new questions spawned; log.md entry; pin the producing commit hash here and there)
