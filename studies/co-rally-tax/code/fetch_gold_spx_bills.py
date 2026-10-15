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
  2. Yahoo ^SPX           -> spx_price_monthly.csv   S&P 500 price index, month-END close, 1984-01 ->
     (DFX-4: BUILT FROM THE CHUNKED DAILY LEG BELOW — the range=max 1mo payload
     is silently quarterly-downgraded and its bars are +2-mo window-start
     mislabeled; it is NEVER written to the monthly file, DFX-3 guard backstop)
     + ^SPX daily        -> spx_daily.csv            DFX-4 daily leg, chunked 5-year, 1984-01 ->
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


class MonthlyCoverageAbort(Exception):
    """DFX-2 loud abort: a month of the monthly file's own span is missing
    from BOTH the monthly payload and the same symbol's daily leg. The fetch
    refuses to write a holed monthly file (never a hole, never an
    interpolated guess); main() reports it as a failed job and exits
    non-zero, and no partial/holed file is written."""

    def __init__(self, symbol, fname, missing):
        self.symbol = symbol
        self.fname = fname
        self.missing = list(missing)
        shown = ", ".join(self.missing[:10]) + ("…" if len(self.missing) > 10 else "")
        super().__init__(
            f"{symbol} -> {fname}: {len(self.missing)} month(s) in the file's own span "
            f"missing from BOTH the monthly payload and the daily leg ({shown}) — "
            f"aborting; refusing to write a holed monthly file")


def month_end_map(daily_rows):
    """DFX-2: {'YYYY-MM': close of the LAST daily row in that month}.

    daily_rows: (YYYY-MM-DD, close) pairs; the last calendar day present in
    the month wins (max date), so row order need not be chronological.
    `close` may be a float (in-memory leg) or the raw stored string (disk
    leg) — it passes through untouched so backfilled month-ends stay
    byte-equal to the daily file's own month-end rows."""
    last = {}
    for d, v in daily_rows:
        m = d[:7]
        if m not in last or d > last[m][0]:
            last[m] = (d, v)
    return {m: v for m, (d, v) in last.items()}


def load_daily_leg(data_dir, fname):
    """DFX-2 backfill source: the SAME symbol's stored daily-leg CSV
    (header `date,close`). Closes are kept as the raw stored strings so a
    backfilled month-end is byte-equal to the daily file's month-end row.
    Returns [(date, close_str), ...] in file order, or None when the file
    does not exist yet — with no daily leg on disk, every month the payload
    lacks is a both-legs-gap MonthlyCoverageAbort."""
    import csv as _csv
    path = os.path.join(data_dir, fname)
    if not os.path.exists(path):
        return None
    with open(path, newline="") as f:
        return [(r["date"], r["close"]) for r in _csv.DictReader(f)]


def backfill_monthly(monthly_rows, daily_month_ends, symbol, fname):
    """DFX-2: emit a monthly file with no missing months.

    Months the deduped monthly payload lacks a valid close for (GC=F
    holidays/suspensions — the silent None-close drop, F2) are backfilled
    from the same symbol's complete daily-leg month-end, byte-equal to the
    daily month-end. The file's own span is [first payload month, last
    payload month]; a month of that span missing from BOTH the payload and
    the daily leg raises MonthlyCoverageAbort BEFORE anything is written —
    never a hole, never an interpolated guess.

    `monthly_rows`: (YYYY-MM-01, close), deduped, chronological.
    `daily_month_ends`: month_end_map of the daily leg ({} when absent).
    Payload-present months are kept verbatim (payload wins; the running
    month's MTD row is retained — analysis-time drop stays the consumer's
    rule); daily-leg months outside the payload span are ignored. An empty
    payload has no span to cover and is returned as-is (empty-file
    guarding is the DFX-3 per-file coverage guard, not this cap).
    """
    if not monthly_rows:
        return []
    have = {}
    for k, v in monthly_rows:
        have[k[:7]] = v
    start, end = monthly_rows[0][0][:7], monthly_rows[-1][0][:7]
    y, m = int(start[:4]), int(start[5:7])
    out, backfilled, missing = [], [], []
    while True:
        key = f"{y:04d}-{m:02d}"
        if key in have:
            out.append((key + "-01", have[key]))
        elif key in daily_month_ends:
            out.append((key + "-01", daily_month_ends[key]))
            backfilled.append(key)
        else:
            missing.append(key)
        if key == end:
            break
        m += 1
        if m == 13:
            y, m = y + 1, 1
    if missing:
        raise MonthlyCoverageAbort(symbol, fname, missing)
    if backfilled:
        shown = ", ".join(backfilled[:6]) + ("…" if len(backfilled) > 6 else "")
        print(f"  backfilled {len(backfilled)} month-end(s) from daily leg "
              f"({symbol} {fname}): {shown}")
    return out


class MonthlyCoverageGuardAbort(Exception):
    """DFX-3 loud abort: a monthly-named file does not cover its own
    [first_date, PARTIAL] period range at the density a genuine monthly
    series has — a gap > 2 consecutive months, or coverage < 80% of the
    file's own span. The recorded instance (F3): Yahoo range=max&interval=1mo
    silently DOWNGRADED ^SPX to quarter-end bars (169 rows over a 503-month
    span) stored under a monthly name. The fetch refuses to persist a sparse
    monthly file; main() maps this to a failed job and exits non-zero, and no
    partial file lands in `data/` (the guard runs BEFORE write_csv). It is
    PER-FILE, not per-fetch-run: each monthly file is judged on its OWN span,
    so a downgraded ^SPX trips even while the ETF/futures monthlies stay
    complete."""

    def __init__(self, symbol, fname, span_months, present, max_gap, reason):
        self.symbol = symbol
        self.fname = fname
        self.span_months = span_months
        self.present = present
        self.max_gap = max_gap
        self.reason = reason
        super().__init__(
            f"{symbol} -> {fname}: DFX-3 per-file coverage guard tripped "
            f"({reason}): {present}/{span_months} months of the file's own "
            f"[first_date, last] span present, max consecutive gap = "
            f"{max_gap} month(s) — aborting; refusing to persist a sparse "
            f"monthly file")


def _span_months(start, end):
    """DFX-3 helper: inclusive list of 'YYYY-MM' strings from `start` to
    `end` (both 'YYYY-MM')."""
    y, m = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def check_monthly_coverage(rows, symbol, fname):
    """DFX-3 per-file monthly coverage guard.

    `rows`: the monthly file's final rows (YYYY-MM-01, value) in write order
    (deduped, chronological; a running-month MTD snapshot is included).
    Asserts the file covers its OWN period range [first row's month, last
    row's month] at the density a genuine monthly series has. Per DECISIONS
    DFX-3 a SHORTFALL is either:
      - any gap > 2 consecutive months (>= 3 missing months in a row), or
      - coverage < 80% of the file's own span (present/total months).
    Either one trips the guard and raises MonthlyCoverageGuardAbort.

    A complete file (every month of its span present) passes; a
    quarterly-downgraded payload (~1 bar / 3 months -> ~33% coverage) trips.
    An empty file (no rows) trips: a monthly-named file with no months covers
    nothing (empty-file guarding deferred from DFX-2 to this cap). The guard
    is PER-FILE — each file is judged on its own span, not the whole fetch
    run. Returns None when the file's coverage is sound.
    """
    if not rows:
        raise MonthlyCoverageGuardAbort(symbol, fname, 0, 0, 0,
                                        "empty monthly file (no months)")
    present = sorted({r[0][:7] for r in rows})
    span = _span_months(present[0], present[-1])
    total = len(span)
    present_set = set(present)
    n_present = len(present_set)
    max_gap = run = 0
    for key in span:
        if key in present_set:
            run = 0
        else:
            run += 1
            if run > max_gap:
                max_gap = run
    if max_gap > 2:
        raise MonthlyCoverageGuardAbort(
            symbol, fname, total, n_present, max_gap,
            f"gap of {max_gap} consecutive months (> 2)")
    # coverage < 80% of the file's own span; integer compare (exact, no float)
    if n_present * 10 < total * 8:
        raise MonthlyCoverageGuardAbort(
            symbol, fname, total, n_present, max_gap,
            f"coverage {n_present}/{total} = {n_present * 100 / total:.0f}% "
            f"of own span (< 80%)")
    return None


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


def fetch_yahoo(symbol, fname, field, data_dir, daily_fname=None):
    """Monthly close/adjclose file for `symbol`. When `daily_fname` is
    given (the same symbol's stored daily leg), DFX-2 backfills payload
    month-gaps from that leg and aborts (MonthlyCoverageAbort) on any month
    missing from both legs. DFX-3 then runs the per-file coverage
    guard on the final rows: a sparse monthly file (any gap > 2 consecutive
    months, or coverage < 80% of the file's own span — e.g. a Yahoo range=max
    monthly request silently downgraded to quarter-end bars, F3) trips the
    guard and ABORTS BEFORE the file is written, so nothing partial lands in
    `data_dir`. Both the backfill and the guard run before write_csv."""
    rows = yahoo_monthly(symbol, field=field)
    if daily_fname is not None:
        leg = load_daily_leg(data_dir, daily_fname)
        rows = backfill_monthly(rows, month_end_map(leg) if leg else {},
                                symbol, fname)
    check_monthly_coverage(rows, symbol, fname)  # DFX-3 per-file guard
    write_csv(os.path.join(data_dir, fname), ["date", "close"], rows)
    return len(rows)


def yahoo_daily_rows(symbol, start_year):
    """Daily closes for `symbol`, fetched in 5-year chunks — Yahoo silently
    DOWNGRADES range=max&interval=1d to monthly bars for some symbols
    (observed 2026-10-12), so chunk with period1/period2 and stitch.
    Downgrade guard: reject chunks whose median spacing is > 5 days
    (monthly bars would be ~30). Returns [(YYYY-MM-DD, close), ...],
    sorted and de-duped."""
    import datetime as _dt
    import time
    base = "https://query1.finance.yahoo.com/v8/finance/chart/" + \
        urllib.request.quote(symbol)
    rows, seen = [], set()
    this = _dt.datetime.now(_dt.timezone.utc).year + 1
    for y0 in range(start_year, this, 5):
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
    return rows


def fetch_yahoo_daily(symbol, fname, data_dir, start_year=2000):
    """Daily closes, chunked (see yahoo_daily_rows). Gold LIVE EXTENSION legs
    (GLD) and GC=F basis diagnostics start at 2000; the DFX-4 ^SPX leg starts
    at 1984 (its full Yahoo daily history)."""
    rows = yahoo_daily_rows(symbol, start_year)
    write_csv(os.path.join(data_dir, fname), ["date", "close"], rows)
    return len(rows)


def fetch_spx_monthly(data_dir):
    """DFX-4: spx_price_monthly.csv as true month-END closes, immune to
    Yahoo's silent quarterly downgrade and its +2-month window-start
    mislabeling. The range=max&interval=1mo payload silently DOWNGRADES ^SPX
    to QUARTER-end bars (F3: 169 rows over a 503-month span) and its values
    are mislabeled — bar = close of the 3-month window STARTING at the label
    (F4, verified 167/168 vs dailies 2026-10-15). That payload is therefore
    NEVER written to the monthly file: the daily leg is fetched chunked
    (downgrade-proof; verified 2026-10-15: 10,780 rows, no downgrades),
    stored as spx_daily.csv, and the monthly file is its month-end resample
    (one row per month, last close of the month wins — DFX-1 semantics; the
    running month's row is an MTD snapshot and stays in the file). The DFX-3
    per-file coverage guard still runs as a backstop before the write."""
    daily = yahoo_daily_rows("^SPX", 1984)
    write_csv(os.path.join(data_dir, "spx_daily.csv"), ["date", "close"], daily)
    rows = [(m + "-01", v) for m, v in sorted(month_end_map(daily).items())]
    check_monthly_coverage(rows, "^SPX", "spx_price_monthly.csv")  # DFX-3 backstop
    write_csv(os.path.join(data_dir, "spx_price_monthly.csv"),
              ["date", "close"], rows)
    print(f"  spx_price_monthly rebuilt from chunked dailies: "
          f"{len(daily)} daily bars -> {len(rows)} month-end rows")
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
        ("^SPX", lambda: fetch_spx_monthly(d)),
        ("SPY", lambda: fetch_yahoo("SPY", "spy_tr_monthly.csv", "adjclose", d)),
        ("GC=F", lambda: fetch_yahoo("GC=F", "gold_monthly_gcf.csv", "close", d,
                                     daily_fname="gold_daily_gcf.csv")),
        ("GC=F daily", lambda: fetch_yahoo_daily("GC=F", "gold_daily_gcf.csv", d)),
        ("GLD", lambda: fetch_yahoo("GLD", "gld_tr_monthly.csv", "adjclose", d,
                                    daily_fname="gld_daily.csv")),
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
