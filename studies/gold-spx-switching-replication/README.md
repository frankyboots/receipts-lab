# Study: gold-spx-switching-replication

Wiki page: https://github.com/frankyboots/research-wiki/blob/main/studies/gold-spx-switching-replication.md
Claims tested: `gold-spx-switching-outperforms-both-assets`, `switching-positive-in-dotcom-subprime`, `gold-trend-filter-underperforms-bnh`
Status: protocol-only

Data availability (2026-10-12): all sources fetched KEYLESS from this host. Full-history
gold = DAILY LBMA PM fix, 1968-04→current, from two independently validated
public mirrors (fetch-script header: 0.0004% mean dev vs FRED-era dump,
0.06% median vs World Bank Pink Sheet monthly means, 0.36% vs GC=F month-end).
Signals run on month-END FIXES — protocol-consistent. Pink Sheet monthly
averages kept as cross-check only (an average smooths intra-month paths and
shifts crossover dates — it does not generate legit signals).

## Disclosure block (required before any number is published)

- **Universe:** gold (month-end LBMA PM fix 1968→, extracted from the daily
  mirror; GC=F month-end 2000→ as robustness proxy), S&P 500 total
  return (SPY adj close 1993→; Shiller dividend-reinvestment reconstruction
  1977–1992) and price index (Yahoo `^SPX` 1984→; Shiller pre-1984, seam
  normalized at stitch month), 3-month T-bill (FRED `TB3MS`).
- **Period:** 1977-01 → present, monthly bars.
- **Data:** `code/fetch_gold_spx_bills.py` (source + download date in its
  header; `data/` gitignored). **Divergences from wiki protocol:** (1) wiki
  names FRED `GOLDPMGBD228NL` — its official feeds are all dead (FRED dropped
  the IBA series 2022-01-31; Nasdaq Data Link delisted the LBMA datasets,
  verified 2026-10-12) but the same fix series is restored via
  triple-validated public mirrors (fetch-script header): month-end signals
  are real fixes, protocol intact. (2) The 1977–1984 SPX leg exists
  in no free live endpoint; Shiller's file (ends 2023-09 as served) is stitched
  to Yahoo with level normalization at the seam — stitching rule will be
  committed in the analysis script. (3) GC=F month-end (2000→) is a
  robustness leg; the dot-com stress window's gold leg runs on fixes.
- **Costs:** base run costless (matches vendor style); sensitivity run 10 bps
  per switch; no leverage, fully invested.
- **Engine:** Python 3.14 + pandas 3.0.6 + xlrd 2.0.2 + openpyxl 3.1.5
  (`requirements.txt`);
  fetch script stdlib-only. Analysis scripts land in `code/`.

## Protocol

The vendor's exact rules are paywalled, so grid a family of reconstructions
(pre-registered here, no hindsight cherry-picking — report the whole grid):

1. Relative-strength lookback L ∈ {3, 6, 9, 12} months; hold the asset with
   the higher trailing return.
2. Risk-free filter variants: (a) both trailing returns < T-bill trailing
   return → cash; (b) both < 0.
3. Baselines: gold B&H, SPX B&H, gold-only 1-yr trend filter (tests claim 3).

Report CAGR, max DD, Sharpe per variant; stress-window returns Mar-2000–Oct-2002
and Nov-2007–Mar-2009; CAGR/DD heatmap across L × filter to expose parameter
sensitivity. Compare best/median variant against the vendor's ≈12.7% CAGR /
≈31% max DD (1977–2026).

Question targets: `gold-trend-filter-post-2023` (baseline leg, gold half),
`does-the-cash-leg-earn-its-keep` (cash variants vs no-cash baseline),
`both-assets-down-regimes` (measure it on the cash variants).

**No signal-peeking:** positions form on prior month-end data, executed the
following month.

## Results

(pending — no code run yet)

## Verdict → wiki

(update the wiki study page: Results, Verdict, claim status/confidence changes,
new questions spawned; log.md entry; pin the producing commit hash here and there)
