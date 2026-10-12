# Study: gold-spx-ratio-rotation-replication

Wiki page: https://github.com/receiptsandregimes/research-wiki/blob/main/studies/gold-spx-ratio-rotation-replication.md
Claims tested: `qs-rotation-beats-both-buyhold`, `qs-rotation-gfc-divergence`, `qs-rotation-asset-contributions-equal`
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
## Disclosure block (required before any number is published)

- **Universe:** S&P 500 price index (primary, matches source) AND a
  total-return variant (SPY adjusted close 1993→; Shiller dividend-reinvestment
  reconstruction 1985–1992); gold monthly LBMA PM fix extracted from daily
  (full history 1968→), GC=F futures month-end 2000→ as robustness check.
- **Period:** 1985-01 → present, monthly bars. Extends the source's Jul-2020
  cutoff to test robustness through gold's 2024–25 run.
- **Data:** fetched by `code/fetch_gold_spx_bills.py` (download date stated in
  its header; re-run to rebuild — `data/` is gitignored by design). Sources:
  Yahoo chart API (`^SPX`, `SPY`, `GC=F`), FRED `TB3MS`, Shiller `ie_data.xls`,
  World Bank Pink Sheet `CMO-Historical-Data-Monthly.xlsx` (CC BY 4.0) +
  eco3min CSV mirror. Dividend treatment:
  price-index leg is Yahoo `^SPX` (no dividends); TR leg is dividend-adjusted
  by construction (SPY adj close / Shiller dividends reinvested at month-end).
  **Divergences from wiki protocol:** (1) the wiki names FRED
  `GOLDPMGBD228NL`; its official feeds are all dead (FRED dropped the IBA
  series 2022-01-31; Nasdaq Data Link delisted the LBMA datasets — verified
  2026-10-12) but the same fix series is restored via triple-validated public
  mirrors (fetch-script header) — protocol intact: month-end PM fixes.
  (2) GC=F month-end (2000→) retained as a robustness check only.
- **Costs:** base run costless (matches source); sensitivity 10 bps per switch.
  No leverage, fully invested.
- **Engine:** Python 3.14 + pandas 3.0.6 + xlrd 2.0.2 + openpyxl 3.1.5
  (`requirements.txt`);
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
