#!/usr/bin/env python3
"""
fetch_gold_spx_bills.py — shared monthly-universe fetch for the gold/SPX study
family (gold-spx-ratio-rotation-replication, gold-spx-switching-replication,
co-rally-tax, filtered-levered-gold-vs-bnh). Each study directory ships an
identical copy; rebuild the universe with:

    python3 code/fetch_gold_spx_bills.py          # writes ./data/ (gitignored)
    python3 code/fetch_gold_spx_bills.py --report # reachability probe only

GOLD LEG — composite architecture (adopted 2026-10-12; canonical record:
research-wiki entities/lbma-gold-price.md). FREE LIVE LBMA FIX FEEDS ARE DEAD:
the official JSON (prices.lbma.org.uk) is Incapsula-walled; FRED retired the
IBA series 2022-01-31; Nasdaq Data Link delisted LBMA; every public mirror
pulled the walled JSON and froze. Our primary mirror froze at 2026-02-25
(frozen copy pin: sha256 86057834bd6fca539749f150a42255e28c4cf0fac2935b265b1c13e826fb24d9).
Composition rule for analysis:
  1968-04 -> 2026-02  frozen LBMA PM-fix mirror (immutable history)
  2026-03 ->          GLD total-return monthly as LIVE EXTENSION (primary);
                      GC=F month-end as second opinion
  splice = ratio-normalized at seam; run signals on WITHIN-SERIES RETURNS,
  never raw spliced levels. Measured month-end GC=F-vs-fix basis
  (2000-10..2026-01, 260 mo): median 0.36%, p90 1.21%, MAX 4.75% @ 2026-01 —
  level-splicing across the seam is banned; cross-check every live month vs
  Pink Sheet monthly average (flag |dev| > 1%).
  Fix-grade paid continuation (metals-api / MetalPriceAPI / EODHD XAU.USD,
  ~$20-50/mo) deferred until a verdict hinges on fix-vs-proxy fidelity.

Sources (verified reachable 2026-10-12 unless noted):
  1. FRED  TB3MS          -> tb3ms_monthly.csv       3-mo T-bill discount rate, monthly, 1950 ->
  2. Yahoo ^SPX           -> spx_price_monthly.csv   S&P 500 price index, monthly close, 1984-12 ->
  3. Yahoo SPY            -> spy_tr_monthly.csv      adj close = dividend total-return proxy, 1993 ->
  4. Yahoo GC=F           -> gold_monthly_gcf.csv    COMEX front-month close, monthly, 2000-09 ->
     + GC=F daily        -> gold_daily_gcf.csv      daily basis/seam diagnostics
  4b. Yahoo GLD           -> gld_tr_monthly.csv      adj close NAV total-return proxy, 2004-12 ->
     + GLD daily         -> gld_daily.csv           LIVE EXTENSION leg of gold composite
  5. LBMA PM fix DAILY   -> lbma_pm_fix_daily.csv    FROZEN HISTORY 1968-04 -> 2026-02-25
     (forex-centuries mirror; upstream dead since Feb-2026; file re-fetched is
     expected-unchanged — verify sha256 above; month-end extraction = signals)
  5b. LBMA fix (FRED-    -> lbma_pm_fix_fred_mirror.csv  cross-check mirror, 1968-04 -> 2019-02
      era dump)                                        (agrees with #5 at 0.0004% mean dev)
  6. World Bank Pink     -> CMO-Historical-Data-Monthly.xlsx  monthly avg gold USD/oz, 1960M1 ->
     Sheet (CC BY 4.0)                                   CROSS-CHECK series (not for signals —
     eco3min.fr mirror   -> gold_monthly_eco3min.csv    monthly AVERAGES); CSV mirror, 0.0% dev
  7. Shiller ie_data.xls -> shiller_ie_data.xls     raw monthly S&P price + dividends 1871 -> 2023-09
                                                      (as served; extend SPX price/TR pre-1984/1993;
                                                      stitch to Yahoo at analysis time, normalize seam)

Retired / blocked sources (verified 2026-10-12, do not chase):
  - LBMA gold fixes are GONE from every OFFICIAL feed: FRED dropped the IBA
    series 2022-01-31; Nasdaq Data Link DELISTED the LBMA datasets entirely
    (dataset page 404; catalog 'metals' empty; API key useless; NDLC's WAF
    separately blocks /api/v3/datasets/ from datacenter IPs for all
    publishers). Paid successor LBMTD = OTC volumes, not price.
  - The public daily-fix mirror era ENDED 2026-02: forex-centuries' weekly CI
    pulls prices.lbma.org.uk/json/gold_pm.json (their scripts/update_sources.py
    update_lbma); the wall killed it — last row 2026-02-25, last commit
    2026-02-26. No maintained free daily-fix feed exists anywhere (datahub's
    core/gold-prices likewise fell back to Pink Sheet monthly averages).
  - WORKING daily fixes = ONLY the frozen mirror snapshot (see #5, sha-pinned).
    Post-2026-02 gold price = GLD/GC=F per composite rule above.
  - prices.lbma.org.uk/json/*: Incapsula JS wall (403, incl. from a real browser).
  - stooq.com CSVs: JS proof-of-work challenge (curl); "Access denied" from datacenter IPs.

Stdlib only (urllib/json/csv) — pandas/xlrd are analysis-time deps (see requirements.txt).
"""
import argparse
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) receipts-lab fetch/1.0"}
TIMEOUT = 40


def get(url, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def dedupe_monthly(rows):
    """Keep exactly one row per month: LAST occurrence wins.

    DFX-1 (F1): Yahoo monthly payloads return the running month twice with
    different intraday snapshots (reproduced live 2026-10-15: GC=F 4107.9 vs
    4166.3). The surviving row may be an MTD snapshot for the running month —
    it stays in the file; dropping it is the CONSUMER's analysis-time rule,
    never the fetch's. Input rows are (YYYY-MM-01, close) in payload order
    (chronological); output preserves that order.
    """
    last = {}
    for k, v in rows:
        last[k] = v
    return list(last.items())


def yahoo_monthly(symbol, field="adjclose"):
    """Return list of (YYYY-MM-01, close) month-end rows from Yahoo chart API.

    Exactly one row per month (dedupe_monthly, last occurrence wins) — DFX-1."""
    import time
    time.sleep(2)  # Yahoo 429-throttles bursts from datacenter IPs
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.request.quote(symbol)}?range=max&interval=1mo"
    )
    data = json.loads(get(url).decode("utf-8"))
    result = data["chart"]["result"][0]
    ts = result["timestamp"]
    if field == "adjclose":
        # Yahoo nests adjusted closes as adjclose[0]['adjclose']
        vals = result["indicators"]["adjclose"][0]["adjclose"]
    else:
        vals = result["indicators"]["quote"][0][field]
    import datetime as _dt

    rows = []
    for t, v in zip(ts, vals):
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue  # Yahoo occasionally mixes non-numeric junk into arrays
        d = _dt.datetime.fromtimestamp(t, _dt.timezone.utc)
        rows.append((d.strftime("%Y-%m-01"), round(v, 6)))
    return dedupe_monthly(rows)


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote {path} ({len(rows)} rows)")


def fetch_fred_tb3ms(data_dir):
    raw = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS").decode("utf-8")
    rows = []
    for r in csv.DictReader(io.StringIO(raw)):
        v = r.get("TB3MS", "")
        if v and v != ".":
            rows.append((r["observation_date"], v))
    write_csv(os.path.join(data_dir, "tb3ms_monthly.csv"),
              ["date", "tb3ms_pct"], rows)
    return len(rows)


def fetch_yahoo(symbol, fname, field, data_dir):
    rows = yahoo_monthly(symbol, field=field)
    write_csv(os.path.join(data_dir, fname), ["date", "close"], rows)
    return len(rows)


def fetch_yahoo_daily(symbol, fname, data_dir):
    """Daily closes, fetched in 5-year chunks — Yahoo silently DOWNGRADES
    range=max&interval=1d to monthly bars for some symbols (observed
    2026-10-12), so chunk with period1/period2 and stitch. Gold LIVE
    EXTENSION legs (GLD) and GC=F basis diagnostics."""
    import datetime as _dt
    import time
    base = "https://query1.finance.yahoo.com/v8/finance/chart/" + \
        urllib.request.quote(symbol)
    rows, seen = [], set()
    start = 2000
    this = _dt.datetime.now(_dt.timezone.utc).year + 1
    for y0 in range(start, this, 5):
        p1 = int(_dt.datetime(y0, 1, 1, tzinfo=_dt.timezone.utc).timestamp())
        p2 = int(_dt.datetime(min(y0 + 5, this), 1, 1, tzinfo=_dt.timezone.utc).timestamp())
        time.sleep(2)
        data = json.loads(get(f"{base}?period1={p1}&period2={p2}&interval=1d")
                          .decode("utf-8"))
        r = data["chart"]["result"][0]
        res = r.get("timestamp")
        if not res:
            continue
        cl = r["indicators"]["quote"][0]["close"]
        # guard against a silent interval downgrade: reject chunks whose
        # median spacing is > 5 days (monthly bars would be ~30)
        span = [b - a for a, b in zip(res, res[1:])] or [1]
        span.sort()
        if span[len(span) // 2] > 5 * 86400:
            raise ValueError(f"{symbol} {y0}: Yahoo returned non-daily bars")
        for t, v in zip(r["timestamp"], cl):
            if v is None:
                continue
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            d = _dt.datetime.fromtimestamp(t, _dt.timezone.utc).strftime("%Y-%m-%d")
            if d not in seen:
                seen.add(d)
                rows.append((d, round(v, 6)))
    rows.sort()
    write_csv(os.path.join(data_dir, fname), ["date", "close"], rows)
    return len(rows)


PINK_SHEET_URL = ("https://thedocs.worldbank.org/en/doc/"
                  "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
                  "CMO-Historical-Data-Monthly.xlsx")
ECO3MIN_GOLD_URL = "https://eco3min.fr/dataset/gold-price.csv"
LBMA_MIRROR_URL = ("https://raw.githubusercontent.com/unbalancedparentheses/"
                   "forex-centuries/main/data/sources/lbma/lbma_gold_daily.csv")
LBMA_FRED_MIRROR_URL = ("https://raw.githubusercontent.com/Prerna11071997/"
                        "Recession_prediction/master/venv/dataset/"
                        "GOLDPMGBD228NLBM.csv")


def fetch_lbma_mirror(data_dir):
    """FROZEN HISTORY gold: daily LBMA PM fix USD (col `gold_pm_usd`),
    1968-04-01 -> 2026-02-25 ONLY (upstream walled; mirror repo dead since
    Feb-2026). Re-fetch must reproduce sha256 86057834bd6fca539749f150a42255e2
    8c4cf0fac2935b265b1c13e826fb24d9 — if it differs, STOP: the frozen history
    changed under us. Post-2026-02 gold comes from GLD/GC=F per the composite
    rule in this file's header (canonical: wiki entities/lbma-gold-price.md)."""
    import hashlib
    raw = get(LBMA_MIRROR_URL).decode("utf-8", "replace")
    path = os.path.join(data_dir, "lbma_pm_fix_daily.csv")
    with open(path, "w") as f:
        f.write(raw)
    sha = hashlib.sha256(raw.encode()).hexdigest()
    n = raw.strip().count("\n")
    expect = "86057834bd6fca539749f150a42255e28c4cf0fac2935b265b1c13e826fb24d9"
    if sha != expect:
        print(f"  WARNING: frozen-history sha mismatch: {sha} (expected {expect[:16]}…)")
    print(f"  wrote {path} ({n} rows, sha256={sha[:16]})")
    return n


def fetch_lbma_fred_mirror(data_dir):
    """Cross-check gold: FRED-era GOLDPMGBD228NLBM dump (daily PM fix,
    1968-04 -> 2019-02). Independent mirror; agreement with the primary is
    the integrity test (0.0004% mean dev verified 2026-10-12)."""
    raw = get(LBMA_FRED_MIRROR_URL).decode("utf-8", "replace")
    path = os.path.join(data_dir, "lbma_pm_fix_fred_mirror.csv")
    with open(path, "w") as f:
        f.write(raw)
    n = raw.strip().count("\n")
    print(f"  wrote {path} ({n} rows)")
    return n


def fetch_pink_sheet(data_dir):
    """World Bank Pink Sheet monthly workbook (raw, CC BY 4.0). Parse at
    analysis time: sheet 'Monthly Prices', header row index 4, column 'Gold'
    = monthly average USD/oz since 1960M1; dates labeled '1960M01'. The doc
    URL embeds a per-release slug — if this 404s, re-grab the
    CMO-Historical-Data-Monthly.xlsx link from
    https://www.worldbank.org/en/research/commodity-markets"""
    import hashlib
    raw = get(PINK_SHEET_URL)
    path = os.path.join(data_dir, "CMO-Historical-Data-Monthly.xlsx")
    with open(path, "wb") as f:
        f.write(raw)
    print(f"  wrote {path} ({len(raw)} bytes, "
          f"sha256={hashlib.sha256(raw).hexdigest()[:16]})")
    return len(raw)


def fetch_eco3min_gold(data_dir):
    """eco3min.fr mirror of the Pink Sheet monthly gold series, clean CSV
    (date, gold_price_usd). Verified 0.0% deviation vs the primary xlsx on
    2026-10-12. Fallback when the WB doc slug rotates. Cite the World Bank."""
    raw = get(ECO3MIN_GOLD_URL).decode("utf-8", "replace")
    path = os.path.join(data_dir, "gold_monthly_eco3min.csv")
    with open(path, "w") as f:
        f.write(raw)
    n = raw.strip().count("\n")
    print(f"  wrote {path} ({n} rows)")
    return n


def fetch_shiller(data_dir):
    last_err = None
    for url in (
        "https://www.econ.yale.edu/~shiller/data/ie_data.xls",
        "http://www.econ.yale.edu/~shiller/data/ie_data.xls",
    ):
        try:
            raw = get(url)
            if len(raw) < 100_000:
                raise ValueError(f"suspiciously small payload: {len(raw)} bytes")
            path = os.path.join(data_dir, "shiller_ie_data.xls")
            with open(path, "wb") as f:
                f.write(raw)
            print(f"  wrote {path} ({len(raw)} bytes)")
            return len(raw)
        except Exception as e:  # noqa: BLE001 - report and try next
            last_err = e
    raise last_err


def probe(url, label):
    try:
        raw = get(url)
        ok = len(raw) > 100 and not raw.lstrip().startswith(b"<!DOCTYPE")
        print(f"  [{'OK  ' if ok else 'FAIL'}] {label} ({len(raw)} bytes)")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"  [FAIL] {label}: {type(e).__name__}: {e}")
        return False


def report():
    print("Source reachability report (no files written):")
    results = {
        "fred_tb3ms": probe("https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS", "FRED TB3MS"),
        "yahoo_spx": probe(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5ESPX?range=max&interval=1mo",
            "Yahoo ^SPX"),
        "yahoo_spy": probe(
            "https://query1.finance.yahoo.com/v8/finance/chart/SPY?range=max&interval=1mo",
            "Yahoo SPY"),
        "yahoo_gcf": probe(
            "https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?range=max&interval=1mo",
            "Yahoo GC=F"),
        "yahoo_gld": probe(
            "https://query1.finance.yahoo.com/v8/finance/chart/GLD?range=max&interval=1mo",
            "Yahoo GLD"),
        "shiller": probe("http://www.econ.yale.edu/~shiller/data/ie_data.xls",
                         "Shiller ie_data.xls"),
        "pink_sheet": probe(PINK_SHEET_URL, "World Bank Pink Sheet (monthly)"),
        "eco3min_gold": probe(ECO3MIN_GOLD_URL, "eco3min gold CSV mirror"),
        "lbma_mirror": probe(LBMA_MIRROR_URL, "LBMA PM fix daily (mirror)"),
        "lbma_fred": probe(LBMA_FRED_MIRROR_URL, "LBMA fix FRED-era dump"),
    }
    return 0 if all(results.values()) else 1


def main():
    ap = argparse.ArgumentParser(description="shared gold/SPX/bills universe fetch")
    ap.add_argument("--report", action="store_true", help="reachability probe only")
    ap.add_argument("--outdir", default="data", help="output dir (default ./data, gitignored)")
    args = ap.parse_args()

    if args.report:
        sys.exit(report())

    os.makedirs(args.outdir, exist_ok=True)
    d = args.outdir
    failures = []
    jobs = [
        ("TB3MS", lambda: fetch_fred_tb3ms(d)),
        ("^SPX", lambda: fetch_yahoo("^SPX", "spx_price_monthly.csv", "close", d)),
        ("SPY", lambda: fetch_yahoo("SPY", "spy_tr_monthly.csv", "adjclose", d)),
        ("GC=F", lambda: fetch_yahoo("GC=F", "gold_monthly_gcf.csv", "close", d)),
        ("GC=F daily", lambda: fetch_yahoo_daily("GC=F", "gold_daily_gcf.csv", d)),
        ("GLD", lambda: fetch_yahoo("GLD", "gld_tr_monthly.csv", "adjclose", d)),
        ("GLD daily", lambda: fetch_yahoo_daily("GLD", "gld_daily.csv", d)),
        ("Shiller", lambda: fetch_shiller(d)),
        ("LBMA PM fix", lambda: fetch_lbma_mirror(d)),
        ("LBMA FRED mirror", lambda: fetch_lbma_fred_mirror(d)),
        ("Pink Sheet", lambda: fetch_pink_sheet(d)),
        ("eco3min gold", lambda: fetch_eco3min_gold(d)),
    ]
    for name, fn in jobs:
        print(f"[fetch] {name}")
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {type(e).__name__}: {e}")
            failures.append(name)
    print("\nDone." + (f" FAILURES: {', '.join(failures)}" if failures else ""))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
