# Study: co-rally-tax

Wiki page: https://github.com/frankyboots/research-wiki/blob/main/studies/co-rally-tax.md
Claims tested: `rotation-onset-co-rally` (primary); contextualizes `qs-rotation-gfc-divergence`
Status: protocol-only

Data availability (2026-10-12): all sources fetched KEYLESS from this host. Full-history
gold = DAILY LBMA PM fix, 1968-04→current, from two independently validated
public mirrors (fetch-script header: 0.0004% mean dev vs FRED-era dump,
0.06% median vs World Bank Pink Sheet monthly means, 0.36% vs GC=F month-end).
Signals run on month-END FIXES — protocol-consistent. Pink Sheet monthly
averages kept as cross-check only (an average smooths intra-month paths and
shifts crossover dates — it does not generate legit signals).

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
