#!/usr/bin/env python3
"""
fetch_gold_spx_bills.py — shared monthly-universe fetch for the gold/SPX study
family (gold-spx-ratio-rotation-replication, gold-spx-switching-replication,
co-rally-tax, filtered-levered-gold-vs-bnh). Each study directory ships an
identical copy; rebuild the universe with:

    python3 code/fetch_gold_spx_bills.py          # writes ./data/ (gitignored)
    python3 code/fetch_gold_spx_bills.py --report # reachability probe only

Sources (verified reachable 2026-10-12 unless noted):
  1. FRED  TB3MS          -> tb3ms_monthly.csv       3-mo T-bill discount rate, monthly, 1950 ->
  2. Yahoo ^SPX           -> spx_price_monthly.csv   S&P 500 price index, monthly close, 1984-12 ->
  3. Yahoo SPY            -> spy_tr_monthly.csv      adj close = dividend total-return proxy, 1993 ->
  4. Yahoo GC=F           -> gold_monthly_gcf.csv    COMEX front-month gold futures close, 2000-09 ->
  5. LBMA PM fix DAILY   -> lbma_pm_fix_daily.csv    PRIMARY gold, 1968-04 -> current;
     (two independent public mirrors; month-end extraction = legit signals)
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
  - WORKING daily fixes = third-party public mirrors (see source #5):
    https://github.com/unbalancedparentheses/forex-centuries (data/sources/
    lbma/lbma_gold_daily.csv, USD PM column) and a FRED-era GOLDPMGBD228NLBM
    dump. Triple-validated 2026-10-12: mirrors agree 0.0004% mean dev over
    12,776 shared days (1 outlier: 1968-05-16, 41.25 vs 42.25); daily->
    monthly means vs Pink Sheet median 0.06% (>1% only in the known
    fix-distortion months Dec-1980/Jul-1983/Mar-1985); month-end vs GC=F
    median 0.36% (spot-vs-futures basis, to 5% in the Jan-2026 vol regime).
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


def yahoo_monthly(symbol, field="adjclose"):
    """Return list of (YYYY-MM-01, close) month-end rows from Yahoo chart API."""
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
    return rows


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
    """PRIMARY gold: daily LBMA PM fix USD (col `gold_pm_usd`), 1968-04-01 ->
    current, from the forex-centuries repo mirror. Month-end extraction =
    last row of each month. Validation vs FRED dump / Pink Sheet / GC=F is in
    this file's header (triple-checked 2026-10-12). If the URL 404s, re-grab
    from the repo tree; cross-check against lbma_pm_fix_fred_mirror.csv and
    the Pink Sheet monthly means before trusting any replacement."""
    raw = get(LBMA_MIRROR_URL).decode("utf-8", "replace")
    path = os.path.join(data_dir, "lbma_pm_fix_daily.csv")
    with open(path, "w") as f:
        f.write(raw)
    n = raw.strip().count("\n")
    print(f"  wrote {path} ({n} rows)")
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
