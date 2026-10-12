# Study: filtered-levered-gold-vs-bnh

Wiki page: https://github.com/frankyboots/research-wiki/blob/main/studies/filtered-levered-gold-vs-bnh.md
Claims tested: `gold-call-option-filtered-levered` (primary), `gold-trend-filter-underperforms-bnh` (same baseline leg)
Status: protocol-only

Data availability (2026-10-12): all sources fetched KEYLESS from this host. Full-history
gold = World Bank Pink Sheet monthly average (1960->, CC BY 4.0). The LBMA
fix no longer exists on any free feed (FRED dropped it 2022-01-31; Nasdaq
Data Link delisted the LBMA datasets — verified 2026-10-12), so monthly
averages replace month-end fixes (disclosed divergence; see below).

## Disclosure block (required before any number is published)

- **Universe:** gold (monthly primary; daily for the 200-day-MA whipsaw
  variant), T-bills, and benchmarks gold B&H, T-bills, 60/40 (60% SPX total
  return / 40% bills, monthly rebalanced — the honest "what else would you
  hold" comparator for a levered sleeve).
- **Period:** 1971-08 → present (post-Bretton-Woods gold), monthly. Daily
  variant limited to 2000→ (COMEX GC=F is the only free daily gold feed —
  see divergences).
- **Data:** `code/fetch_gold_spx_bills.py` (source + download date in header;
  `data/` gitignored). Gold: World Bank Pink Sheet monthly average
  (CC BY 4.0), 1960→ — **divergences:** (1) wiki named FRED
  `GOLDPMGBD228NL`; the LBMA fix is gone from every free feed (FRED dropped
  the IBA series 2022-01-31; Nasdaq Data Link delisted the LBMA datasets,
  verified 2026-10-12) and no free daily LBMA feed is reachable
  (prices.lbma.org.uk bot-walled; Stooq denies datacenter IPs), so the
  200-day-MA daily variant runs 2000→ on GC=F futures; (2) the headline
  monthly test (1971→) uses Pink Sheet monthly AVERAGES, not month-end fixes
  (disclosed; GC=F month-end 2000→ is the robustness check).
  Bills: FRED `TB3MS`. SPX legs (for 60/40): Shiller + Yahoo stitch as in the
  sibling studies.
- **Costs:** 10 bps per unit of exposure change. Leverage L ∈ {1, 2, 3} with
  two financing models reported — bill-financed (borrow at TB3MS) and a
  margin-rate proxy (TB3MS + 200 bps base, 150 bps sensitivity). Financing
  cost IS the premium in this trade; the +200 bps spread is a stated
  convention, not a quoted rate.
- **Engine:** Python 3.14 + pandas 3.0.6 + xlrd 2.0.2 + openpyxl 3.1.5
  (`requirements.txt`);
  fetch script stdlib-only. Analysis scripts land in `code/`.

## Protocol

Frank's heuristic on trial: does a trend-filtered gold position, levered
2–3×, beat gold B&H on CAGR while never producing a rolling-5-year loss worse
than B&H's — i.e. does the gold-as-call-option shape survive net of whipsaw
and carry?

Filters: 12-mo total return > 0; 200-day MA (daily variant); 20-mo MA
(monthly). Filter ON → target exposure L ∈ {1, 2, 3}; filter OFF → cash.
Position from prior month-end data; costs 10 bps per unit exposure change.

1. Unfiltered vs filtered 1× (reproduces/updates the Returnstream chart —
   answers `gold-trend-filter-post-2023`).
2. Leverage sweep: CAGR, max DD, Sharpe, worst rolling-5-year total return per
   L × financing model. The claim survives only if worst-5yr is never worse
   than B&H while CAGR ≥ ~2× B&H at L=2.
3. Regime decomposition: 1980–2000 (the bleed), 2001–11, 2013–19, 2024–26
   separately — where does leverage help vs where does it compound a whipsaw?
4. Sensitivity: filter family × lookback × rebalance frequency; report the
   heatmap so we see whether the surviving region is wide or one lucky cell.
5. Rate-regime check per the wiki: run 1977–81 (double-digit bills) as its own
   window — the likely falsifier of naive leverage.

Question targets: `gold-trend-filter-post-2023`,
`does-the-cash-leg-earn-its-keep` (absolute momentum in its purest
single-asset form).

**No signal-peeking:** positions form on prior month-end (or prior day-end for
the daily variant) data, executed the following period.

## Results

(pending — no code run yet)

## Verdict → wiki

(update the wiki study page: Results, Verdict, claim status/confidence changes,
new questions spawned; log.md entry; pin the producing commit hash here and there)
