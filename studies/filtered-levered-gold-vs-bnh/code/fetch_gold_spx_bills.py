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
  5. Nasdaq Data Link     -> lbma_gold_raw.csv       LBMA PM fix USD daily, 1968 ->
     LBMA/GOLD                                        REQUIRES a free key in env NDATALINK_API_KEY;
                                                      skipped with a NOTICE without one.
  6. Shiller ie_data.xls  -> shiller_ie_data.xls     raw monthly S&P price + dividends 1871 -> 2023-09
                                                      (as served; extend SPX price/TR pre-1984/1993;
                                                      stitch to Yahoo at analysis time, normalize seam)

Retired / blocked sources (verified 2026-10-12, do not chase):
  - FRED GOLDPMGBD228NL: retired (LBMA licensing); fredgraph.csv returns HTTP 404.
  - prices.lbma.org.uk/json/*: Incapsula JS wall (403, incl. from a real browser).
  - stooq.com CSVs: JS proof-of-work challenge (curl); "Access denied" from datacenter IPs.
  - data.nasdaq.com API: may be Incapsula-blocked from datacenter hosts; report will show FAIL.
    Verified 2026-10-12 (key set; keyless requests to the same URL are blocked
    identically, so the WAF never reaches key validation — the block is not an
    auth failure, and the key itself remains untested by Nasdaq):
    this host's egress IP is WAF-blocked outright
    (curl, python, browser-impersonating TLS, and a real browser all get the Incapsula 403).
    Run this fetch once from an unblocked network (e.g. residential) and place
    lbma_gold_raw.csv under data/ if you land on a blocked host.

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


def fetch_lbma(data_dir):
    key = os.environ.get("NDATALINK_API_KEY", "").strip()
    if not key:
        print("  NOTICE: NDATALINK_API_KEY not set — skipping LBMA/GOLD. "
              "Full-history gold (pre-2000) is unavailable without it; "
              "keyless runs are restricted to 2000 -> via GC=F.")
        return 0
    url = ("https://data.nasdaq.com/api/v3/datasets/LBMA/GOLD.csv"
           f"?api_key={urllib.parse.quote(key)}&start_date=1968-01-01&order=asc")
    raw = get(url)
    path = os.path.join(data_dir, "lbma_gold_raw.csv")
    with open(path, "wb") as f:
        f.write(raw)
    n = raw.decode("utf-8", "replace").count("\n") - 1
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
    key = os.environ.get("NDATALINK_API_KEY", "").strip()
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
    }
    if key:
        results["nasdaq_lbma"] = probe(
            "https://data.nasdaq.com/api/v3/datasets/LBMA/GOLD.csv"
            f"?api_key={urllib.parse.quote(key)}&rows=5",
            "Nasdaq Data Link LBMA/GOLD")
    else:
        print("  [SKIP] Nasdaq Data Link LBMA/GOLD (no NDATALINK_API_KEY in env)")
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
        ("LBMA/GOLD", lambda: fetch_lbma(d)),  # returns 0 (notice) without key
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
