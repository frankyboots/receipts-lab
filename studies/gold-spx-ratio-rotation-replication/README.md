# Study: gold-spx-ratio-rotation-replication

Wiki page: https://github.com/frankyboots/research-wiki/blob/main/studies/gold-spx-ratio-rotation-replication.md
Claims tested: `qs-rotation-beats-both-buyhold`, `qs-rotation-gfc-divergence`, `qs-rotation-asset-contributions-equal`
Status: protocol-only

Data availability (2026-10-12): all free sources reachable from this host via the fetch
script; full-history gold (pre-2000) requires a free Nasdaq Data Link key
(`NDATALINK_API_KEY`) — LBMA pull is skipped without it (see Disclosure block).

## Disclosure block (required before any number is published)

- **Universe:** S&P 500 price index (primary, matches source) AND a
  total-return variant (SPY adjusted close 1993→; Shiller dividend-reinvestment
  reconstruction 1985–1992); gold monthly spot (LBMA PM fix, full history) with
  GC=F futures month-end as a keyless proxy fallback 2000→.
- **Period:** 1985-01 → present, monthly bars. Extends the source's Jul-2020
  cutoff to test robustness through gold's 2024–25 run.
- **Data:** fetched by `code/fetch_gold_spx_bills.py` (download date stated in
  its header; re-run to rebuild — `data/` is gitignored by design). Sources:
  Yahoo chart API (`^SPX`, `SPY`, `GC=F`), FRED `TB3MS`, Shiller `ie_data.xls`,
  Nasdaq Data Link `LBMA/GOLD` (env `NDATALINK_API_KEY`). Dividend treatment:
  price-index leg is Yahoo `^SPX` (no dividends); TR leg is dividend-adjusted
  by construction (SPY adj close / Shiller dividends reinvested at month-end).
  **Divergence from wiki protocol:** the wiki names FRED `GOLDPMGBD228NL` —
  FRED retired it (LBMA licensing; HTTP 404 verified 2026-10-12). Substitutes
  as listed; direct LBMA/Stooq endpoints are bot-walled (documented in the
  fetch script header). Keyless runs are restricted to 2000→; the full
  1985→ backtest needs the free Nasdaq Data Link key.
- **Costs:** base run costless (matches source); sensitivity 10 bps per switch.
  No leverage, fully invested.
- **Engine:** Python 3.14 + pandas 3.0.6 + xlrd 2.0.2 (`requirements.txt`);
  fetch script is stdlib-only. Analysis scripts land in `code/`.

## Protocol

Source: QuantifiedStrategies fully-disclosed gold/SPX ratio rotation
(20-month SMA of SPX/gold ratio; ratio above SMA → long SPX, else long gold).

1. Pin down ratio direction (body: SPX/gold above SMA → long SPX; verify
   against the published ratio chart peak ≈5.5 in 2000 → confirms SPX/gold).
2. Replicate the 20-month SMA rule; report CAGR, max DD, Sharpe vs SPX price
   B&H, SPX total-return B&H, gold B&H.
3. Grid SMA length ∈ {10, 15, 20, 30, 40} months — parameter sensitivity the
   author never tested.
4. Per-leg return decomposition (summed and log-accumulated) across start
   dates 1985/1990/1995/2000 — tests the "equal contributions" claim.
5. GFC facts: strategy equity high vs SPX low Mar-2009; rolling 5-yr relative
   performance.
6. Cross-check against `gold-spx-switching-replication` variants (does the
   Returnstream cash leg add anything over this simpler signal?).

Question targets from the wiki page: `dividend-exclusion-edge-hole` (step 2
answers directly), `does-the-cash-leg-earn-its-keep` (step 6),
`both-assets-down-regimes` (add a both-down months table to results).

**No signal-peeking:** positions form on prior month-end data and are executed
the following month. No same-bar look-ahead anywhere; SMA uses closes through
t−1 when forming the position held in month t.

## Results

(pending — no code run yet)

## Verdict → wiki

(update the wiki study page: Results, Verdict, claim status/confidence changes,
new questions spawned; log.md entry; pin the producing commit hash here and there)
