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
gate run (2026-10-15): **FAIL — 4 fetch-path (F) defects, 0 (S)**, all in the
SHARED fetch script. All four closed via the §8 data-fix SPEC (DFX-1..4); DFX-5
re-fetched all study data with the fixed script and re-validated: verdict
**PASS — 22/22 checks, 0 open defects** (offline battery on the re-fetched
`data/`, 2026-10-15). The fetch script is shared by the 3 sibling studies; its
post-DFX sha is pinned in DECISIONS.md as the family's new shared reference —
their first post-DFX fetch is a single pass into their empty `data/` (DFX-5
fresh-path fix: daily legs are fetched before their monthly jobs).

Per-file verdicts (re-derived from the DFX-5 re-fetch, 2026-10-15):

| file | verdict | evidence |
|---|---|---|
| lbma_pm_fix_daily.csv | PASS | frozen 1968-04-01→2026-02-25, 14,544 rows, clean (max gap 7d); sha256 pin **MATCH** on live re-download; last fix 5191.55 @ 2026-02-25 |
| lbma_pm_fix_fred_mirror.csv | PASS | mean dev vs primary 0.0004% over 12,776 common days (claim 0.0004% ✓); 494 `.` placeholders = source property; single-day disagreement 1968-05-16 (41.25 vs 42.25) |
| gold_monthly_eco3min.csv | PASS | 801 mo complete 1960-01→2026-09; == Pink Sheet xlsx to 0.000000%; re-download byte-identical |
| CMO-Historical-Data-Monthly.xlsx | PASS | == eco3min over all 801 shared months; re-download byte-identical |
| shiller_ie_data.xls | PASS | P decoded 1871-01→2023-09 (1,833 rows); P = monthly AVERAGE of daily closes (first-gate live check; today's re-download byte-identical); final served row 2023-09 anomalous (+2.42% vs true Sep mean) — drop it; file frozen as served |
| tb3ms_monthly.csv | PASS | complete 1,113 mo 1934-01→2026-09, no gaps; `.` placeholders kept as served, coerced at read |
| gld_daily.csv | PASS | 5,511 rows 2004-11-18→2026-10-15, clean (max gap 5d), no dups |
| gold_daily_gcf.csv | PASS | 6,557 rows 2000-08-30→2026-10-15, clean (max gap 5d), no dups |
| gld_tr_monthly.csv | PASS | 263 mo complete 2004-12→2026-10, one row per month (DFX-1 dup removed); == daily month-ends 0.00000000% over 262 complete mo |
| spy_tr_monthly.csv | PASS | 405 mo complete 1993-02→2026-10, one row per month (DFX-1 dup removed) |
| gold_monthly_gcf.csv | PASS | **314/314 mo complete** 2000-09→2026-10 — 46 payload gaps (incl. composite seam 2026-02/2026-03) backfilled from the complete daily leg, byte-equal to the daily month-end; == daily month-ends 0.00000000% over 313 shared complete mo |
| spx_price_monthly.csv | PASS | 514 rows 1984-01→2026-10, complete over its own span; values == month-end resample of the daily leg, 0 tolerance (513 complete mo); 342 non-quarter months present — the quarterly-downgrade signature is gone |
| spx_daily.csv | PASS | 10,781 rows 1984-01-03→2026-10-15, clean (max gap 7d), no dups |

Defect classes (all in the shared fetch script) — **all closed by DFX-1..4**:
- **F1** (DFX-1) monthly fetcher: no dedupe — Yahoo returns the running month
  twice with different intraday snapshots (mechanism reproduced live:
  GC=F 4107.9/4166.3). Closed: `dedupe_monthly()` keeps exactly one row per
  month, last occurrence wins. Evidence: dup scan 0 on gld/spy/gcf monthlies
  in this run's battery.
- **F2** (DFX-2) monthly fetcher: silent None-close drop, no guard (GC=F lost
  46 months, exactly where the seam needed them). Closed: payload month-gaps
  backfilled from the same symbol's complete daily leg; a month missing from
  BOTH legs aborts the fetch loudly before any write. Evidence:
  gold_monthly_gcf 314/314; the both-legs-gap fixture re-run at DFX-5 still
  aborts (guard strictness unchanged).
- **F3** (DFX-3) no per-file monthly coverage guard — quarterly bars silently
  stored under a monthly name. Closed: per-file guard (gap >2 consecutive
  months OR coverage <80% of the file's own span) aborts before every
  payload-derived monthly-file write.
- **F4** (DFX-4) ^SPX quarterly bar values mislabeled (+2-month window shift).
  Closed: `spx_price_monthly.csv` is the month-end resample of the chunked
  DAILY ^SPX leg (spx_daily.csv); the range=max quarterly payload can no
  longer reach the monthly file on any path (DFX-3 guard is the backstop).

Reproduced claims (all re-derived from the re-fetched stored bytes, DFX-5 run
2026-10-15):
- frozen LBMA sha256 `86057834bd6fca53…` MATCH; span + last fix 5191.55 @ 2026-02-25 ✓
- fix-vs-FRED-dump mean 0.0004% ✓ (12,776 days; 258 differ at all; max 2.37% = 1968-05-16 only)
- fix monthly MEANS vs Pink Sheet: median 0.0649% (claim 0.06% ✓; max 10.58% @ 1980-12)
- GC=F-vs-fix month-end basis: **304 mo complete** (monthly file and daily leg
  now agree), median 0.3463%, p90 1.1789%, max 4.7522% @ 2026-01
  (claim 0.36%/1.21%/4.75% ✓). The old "260" = the gappy monthly file's own
  coverage (F2); the complete daily-leg basis is 304 mo.
- eco3min == xlsx 0.000000% ✓; GLD monthly == daily ME 0.00000000% ✓; GC=F
  monthly == daily ME 0.00000000% ✓
- SPX monthly == daily-leg month-end resample: 0.0 exactly over 513 complete
  months (0 tolerance) ✓
- TB3MS: 1,113/1,113 months complete, first = 1934-01-01 (the fetch header's
  "1950 →" was WRONG — corrected in the DFX-5 header)
- all 5 static sources re-downloaded byte-identical in the DFX-5 re-fetch
  (lbma pin MATCH); FRED was reachable again at the re-fetch (the 2026-10-15
  early-morning outage window was transient, as assumed)
- Shiller P = monthly average of dailies ✓ (first-gate live check; today's
  re-download byte-identical); Shiller→Yahoo seam at 2023-09 mixes
  average-vs-close measures (README already mandates level-normalized stitch + returns)
- live: ^SPX quarterly downgrade AND dup-running-month reproduced fresh on the
  first gate; after the DFX-4 rebuild both are gone from the production path
  (the live `decode label+2` check passed at the DFX-4 checkpoint)

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

Record corrections (applied at DFX-5):
- fetch header TB3MS span "1950 →" → actual 1934-01 ✓ applied
- fetch header basis count 260 → 304 mo (complete daily-leg basis: median
  0.3463%, p90 1.1789%, max 4.7522% @ 2026-01) ✓ applied
- README Engine "Python 3.14" → 3.11.16 (pandas 3.0.6 / xlrd 2.0.2 /
  openpyxl 3.1.5 unchanged) ✓ applied

Gate status: **PASS** (22/22 offline checks on the re-fetched `data/`, 0 open
defects; DFX-5 re-fetch + re-validation, 2026-10-15). The gate's green state
unblocks the STUDY SPEC. Next: study spec (analysis caps). (A) hazards above
are for that spec regardless of fix outcome.

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
- **Engine:** Python 3.11.16 + pandas 3.0.6 + xlrd 2.0.2 + openpyxl 3.1.5
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
