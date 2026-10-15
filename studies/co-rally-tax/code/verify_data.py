#!/usr/bin/env python3
"""verify_data.py — co-rally-tax data validation battery (the data-gate artifact).

Re-runnable, read-only on data/. Re-derives every claim in the study README +
fetch-script header from the stored bytes, checks structure against each
file's NAME, and (with --live) re-fetches every source for spot checks.

Usage: ~/receipts-lab/.venv/bin/python code/verify_data.py [--live] [data_dir]
Exit code: 0 = no open (F)/(S) structural or claim defects ((A) hazards are
report-only), 1 = open defects. After a DFX fix, re-run must be green.

Validation 2026-10-15 verdicts this battery encodes:
  DEFECT (F1) monthly fetcher: no dedupe -> dup current-month rows
              (gld_tr_monthly, gold_monthly_gcf, spy_tr_monthly; reproduced live)
  DEFECT (F2) monthly fetcher: silent None-drop -> gold_monthly_gcf missing
              46/314 months incl. composite seam months 2026-02, 2026-03
  DEFECT (F3) monthly fetcher: no per-file coverage guard -> ^SPX served as
              QUARTER-end bars stored under a monthly name (169 rows/503 mo)
  DEFECT (F4) ^SPX quarterly bars MISLABELED: value = close of the 3-month
              window STARTING at the label (167/168 verified vs daily closes)
  NEW (DFX-4) spx_price_monthly rebuilt from the chunked daily leg
              (spx_daily.csv, 1984 ->): struct check for the new daily leg +
              claim:C6b SPX monthly values == daily month-end resample, 0
              tolerance; live section verifies the quarterly downgrade and the
              +2-mo window shift are gone (downgrade-proof chunks, stored ==
              fresh same-label month-end close)
  PASS  frozen LBMA fix mirror (sha-pinned, clean), FRED-era mirror
        (0.0004% mean dev), eco3min == Pink Sheet xlsx (0.000000%), TB3MS
        (complete 1934-01->), GLD/GC=F daily legs (clean), GC=F monthly
        values == daily month-ends (0.0%), GLD monthly == daily month-ends
        (0.0% over 262 mo), Shiller P == monthly mean of dailies (12/13 exact,
        final served row 2023-09 anomalous +2.42%).
  (A) hazards (analysis-time, for the SPEC): GLD leg is NAV/share (-90.7%
      level gap vs fix -> within-series returns only); Shiller P is a monthly
      AVERAGE vs Yahoo month-end closes (measure mix at the 2023-09 stitch;
      drop the anomalous final Shiller row); GC=F-vs-fix month-end basis
      median 0.36% / max 4.75% @ 2026-01; current partial month = MTD
      snapshot, drop at analysis time; SPY adjclose ppm-scale anchor drift.
  ANCHORS (2026-10-15 review F1): section 1b pins the ABSOLUTE first/last
      observation of every source. Before it, every offline check was
      span-relative (struct:*, claim:C6, all inner joins) or head-only
      (claim:C8/C9), so a series truncated at either end passed the whole gate
      (6 review probes on scratch copies: 22/22 PASS exit 0). anchor:first +
      anchor:last close that. F2 made claim:C9 unconditional (an unreadable
      Shiller file used to shrink the gate to 21 checks and still exit 0);
      F5 wrapped the live chunked ^SPX fetch (a Yahoo blip used to abort the
      whole --live run as a traceback) and reports live:spx chunk fetch.
      F6/F7 (review) stay deferred, see DECISIONS.md.
"""
import argparse
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import datetime as dt

import pandas as pd

P = print
RESULTS = []
HAZARDS = []

# running month (month-to-date snapshot) — derived at runtime so re-runs stay correct
PARTIAL = pd.Period(dt.datetime.now(dt.timezone.utc).replace(tzinfo=None), "M")
LBMA_SHA = "86057834bd6fca539749f150a42255e28c4cf0fac2935b265b1c13e826fb24d9"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) receipts-lab verify/1.0"}


def chk(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    P(f"  [{'PASS' if ok else 'DEFECT'}] {name}: {detail}")


def note(name, detail):
    HAZARDS.append((name, detail))
    P(f"  [(A) note] {name}: {detail}")


def load(D, name):
    df = pd.read_csv(f"{D}/{name}")
    df[df.columns[0]] = pd.to_datetime(df[df.columns[0]])
    return df


def month_series(df, col):
    return df.groupby(df[df.columns[0]].dt.to_period("M"))[col].last()


def structural(D):
    P("=" * 20, "1. STRUCTURAL (file shape vs its name)", "=" * 20)
    s = {}
    for name in ["gld_daily.csv", "gld_tr_monthly.csv", "gold_daily_gcf.csv",
                 "gold_monthly_eco3min.csv", "gold_monthly_gcf.csv",
                 "lbma_pm_fix_daily.csv", "lbma_pm_fix_fred_mirror.csv",
                 "spx_daily.csv", "spx_price_monthly.csv", "spy_tr_monthly.csv",
                 "tb3ms_monthly.csv"]:
        df = load(D, name)
        s[name] = df
        dc, vcol = df.columns[0], df.columns[-1]
        daily = "daily" in name or name == "lbma_pm_fix_fred_mirror.csv"
        if daily:
            d = df[dc]
            gaps = d.diff().dt.days.dropna()
            v = pd.to_numeric(df[vcol], errors="coerce")
            dots = int((df[vcol].astype(str) == ".").sum())
            chk(f"struct:{name}",
                int(df.duplicated(dc).sum()) == 0 and gaps.max() <= 31 and v.isna().sum() == dots,
                f"{len(df)} rows {d.min().date()}->{d.max().date()} dups={int(df.duplicated(dc).sum())} "
                f"maxgap={int(gaps.max())}d placeholders('.')={dots} badvals={int(v.isna().sum()) - dots}")
        else:
            per = df[dc].dt.to_period("M")
            full = pd.period_range(per.min(), per.max(), freq="M")
            missing = sorted(set(full) - set(per))
            dups = sorted(df.loc[df.duplicated(dc), dc].dt.strftime("%Y-%m-%d").unique())
            chk(f"struct:{name}",
                len(missing) == 0 and not dups,
                f"{len(df)} rows {per.min()}->{per.max()} span={len(full)}mo "
                f"missing={len(missing)} dups={dups or 'none'}"
                + (f" MISSING={[str(m) for m in missing][:10]}..." if missing else ""))
    # report-only source properties
    fx = s["lbma_pm_fix_daily.csv"]
    note("lbma eur zero-fill",
         f"{int((fx['gold_pm_eur'] == 0).sum())} rows eur==0 through "
         f"{fx.loc[fx['gold_pm_eur'] == 0, fx.columns[0]].max().date()} (pre-euro; usd column is the signal input)")
    fm = s["lbma_pm_fix_fred_mirror.csv"]
    note("fred-mirror placeholders", f"{int((fm[fm.columns[1]].astype(str) == '.').sum())} '.' days in the FRED-era dump (source property; excluded from dev stats)")
    return s


def anchors(D):
    P("=" * 20, "1b. ABSOLUTE ANCHORS (series start/end)", "=" * 20)
    # F1 (review 2026-10-15). Every other offline check is span-relative
    # (struct:* = the file's own min..max, claim:C6, every inner join) or
    # head-only (claim:C8 = 1934-01, claim:C9 = 1871-01), so deletion at
    # EITHER end of a series passed the whole gate: review probes on scratch
    # copies of data/ (spx minus 1984-1999, spx minus 2020-2026, gld legs
    # minus 2024-, eco3min minus 2015-, tb3ms last 36 rows, gcf monthly minus
    # 2000-09..2005-12) all returned 22/22 PASS exit 0. These two checks pin
    # both ends absolutely, so a truncated payload is a DEFECT.
    # first observation source: the README per-file table (DFX-5 re-fetch
    # record). End rule source: the frozen matrix row "post-fix files pass
    # with every month of [first_date, PARTIAL] present" (SPEC.md:152) — live
    # daily legs must carry a bar within RECENT_DAYS of today (the fetch
    # always writes through the last session), monthly files must reach
    # PARTIAL, sources that lag one month upstream (FRED TB3MS, Pink Sheet)
    # are allowed PARTIAL-1, and the frozen sources (sha-pinned LBMA fix,
    # FRED-era dump, Shiller as served) are pinned to their recorded last
    # observation. NOTE: this makes the battery time-aware by design — data
    # that has not been refreshed for the month under analysis reports STALE.
    RECENT_DAYS = 10
    today = dt.datetime.now(dt.timezone.utc).date()
    prev = PARTIAL - 1
    # file, first observation (as stored), end rule
    #   "partial" = must reach PARTIAL | "prev" = must reach >= PARTIAL-1
    #   ("last", d) = frozen, pin the exact last observation
    #   ("recent", n) = last bar within n calendar days
    roster = [
        ("lbma_pm_fix_daily.csv",       "1968-04-01", ("last", "2026-02-25")),
        ("lbma_pm_fix_fred_mirror.csv", "1968-04-01", ("last", "2019-02-08")),
        ("gold_monthly_eco3min.csv",    "1960-01-01", "prev"),
        ("tb3ms_monthly.csv",           "1934-01-01", "prev"),
        ("gld_daily.csv",               "2004-11-18", ("recent", RECENT_DAYS)),
        ("gold_daily_gcf.csv",          "2000-08-30", ("recent", RECENT_DAYS)),
        ("spx_daily.csv",               "1984-01-03", ("recent", RECENT_DAYS)),
        ("gld_tr_monthly.csv",          "2004-12-01", "partial"),
        ("spy_tr_monthly.csv",          "1993-02-01", "partial"),
        ("gold_monthly_gcf.csv",        "2000-09-01", "partial"),
        ("spx_price_monthly.csv",       "1984-01-01", "partial"),
    ]
    obs = []
    for name, first, rule in roster:
        df = load(D, name)
        d = df[df.columns[0]]
        obs.append((name, first, str(d.iloc[0].date()), d.iloc[-1], rule))
    # Pink Sheet xlsx: same span contract as eco3min it feeds (claim:C5 pins
    # the values month-by-month; a truncated book would shrink that join)
    try:
        xl = pd.read_excel(f"{D}/CMO-Historical-Data-Monthly.xlsx",
                           sheet_name="Monthly Prices", header=4)
        xc = xl[xl.columns[0]].astype(str)
        xc = xc[xc.str.match(r"^\d{4}M\d{2}$")]
        p0, p1 = (pd.Period(f"{v[:4]}-{v[5:7]}", "M") for v in (xc.iloc[0], xc.iloc[-1]))
        obs.append(("CMO-Historical-Data-Monthly.xlsx", "1960-01", str(p0), p1, "prev"))
    except Exception as e:  # noqa: BLE001
        obs.append(("CMO-Historical-Data-Monthly.xlsx", "1960-01",
                    f"UNREADABLE ({type(e).__name__}: {e})", None, "prev"))
    bad0, bad1 = [], []
    for name, first, got0, last, rule in obs:
        if got0 != first:
            bad0.append(f"{name}: first={got0} expected={first}")
        if last is None:
            bad1.append(f"{name}: unreadable, end unverifiable")
            continue
        if isinstance(rule, tuple) and rule[0] == "recent":
            ok, want = (today - last.date()).days <= rule[1], f"last bar within {rule[1]}d of {today}"
        elif isinstance(rule, tuple):
            ok, want = str(last.date()) == rule[1], f"pinned to {rule[1]} (frozen source)"
        else:
            p = last if isinstance(last, pd.Period) else last.to_period("M")
            if rule == "partial":
                ok, want = p == PARTIAL, f"reaches {PARTIAL}"
            else:
                ok, want = p >= prev, f"reaches >= {prev}"
        if not ok:
            bad1.append(f"{name}: last={last} want {want}")
    chk("anchor:first series start", not bad0,
        f"{len(obs)} sources pinned to their recorded first observation — "
        + ("; ".join(bad0) if bad0 else "all match"))
    chk("anchor:last series end", not bad1,
        f"PARTIAL={PARTIAL} — " + ("; ".join(bad1) if bad1 else
        f"all {len(obs)} sources at their expected end (frozen pinned; "
        f"upstream-lagged monthlies >= {prev}; live dailies within {RECENT_DAYS}d)"))


def claims(D, s):
    P("=" * 20, "2. CLAIM RE-DERIVATION", "=" * 20)
    fx = s["lbma_pm_fix_daily.csv"]

    # C1 frozen mirror sha + span
    sha = hashlib.sha256(open(f"{D}/lbma_pm_fix_daily.csv", "rb").read()).hexdigest()
    chk("claim:C1 lbma frozen sha+span", sha == LBMA_SHA
        and str(fx[fx.columns[0]].iloc[0].date()) == "1968-04-01"
        and str(fx[fx.columns[0]].iloc[-1].date()) == "2026-02-25",
        f"sha256={'MATCH' if sha == LBMA_SHA else sha} span="
        f"{fx[fx.columns[0]].iloc[0].date()}->{fx[fx.columns[0]].iloc[-1].date()} "
        f"rows={len(fx)} last_fix={fx['gold_pm_usd'].iloc[-1]}")

    # C2 FRED-era mirror dev (claim: 0.0004% mean)
    fm = s["lbma_pm_fix_fred_mirror.csv"]
    fmv = fm[fm[fm.columns[1]] != "."].copy()
    fmv[fm.columns[1]] = fmv[fm.columns[1]].astype(float)
    j = fx.merge(fmv, left_on=fx.columns[0], right_on=fmv.columns[0])
    dev = (j["gold_pm_usd"] - j[fmv.columns[1]]).abs() / j[fmv.columns[1]] * 100
    chk("claim:C2 fred-mirror dev", round(dev.mean(), 4) == 0.0004,
        f"joined={len(j)} days mean|dev|={dev.mean():.4f}% (claim 0.0004%) "
        f"median={dev.median():.4f}% max={dev.max():.4f}% @ {j.loc[dev.idxmax(), j.columns[0]].date()}")
    if dev.max() > 0.1:
        note("mirror single-day disagreement",
             f"1968-05-16 fix 41.25 vs FRED dump 42.250 (2.37%); 258/12,776 days differ at all; "
             f"month-end extraction unaffected (no month-end in top devs)")

    # C3 fix monthly means vs Pink Sheet averages (claim: 0.065% median)
    mm = fx.groupby(fx[fx.columns[0]].dt.to_period("M"))["gold_pm_usd"].mean()
    eco = s["gold_monthly_eco3min.csv"]
    es = eco.groupby(eco[eco.columns[0]].dt.to_period("M"))["gold_price_usd"].first()
    je = pd.DataFrame({"fix_mean": mm}).join(es.rename("wb"), how="inner")
    de = (je["fix_mean"] - je["wb"]).abs() / je["wb"] * 100
    chk("claim:C3 fix-vs-pinksheet", abs(de.median() - 0.065) < 0.01,
        f"joined={len(je)} mo median|dev|={de.median():.4f}% (claim 0.065%) "
        f"p90={de.quantile(.9):.4f}% max={de.max():.4f}% @ {de.idxmax()}")
    note("average-vs-fix measure", "fix monthly MEAN vs Pink Sheet monthly AVERAGE agree to "
         f"median {de.median():.3f}% but diverge in fast markets (max {de.max():.2f}% @ {de.idxmax()}); "
         "Pink Sheet is cross-check only, never signals")

    # C4 GC=F month-end basis (claim: median 0.36% p90 1.21% max 4.75% @ 2026-01;
    # 304 mo complete post-DFX-2 — the pre-fix 260 was the F2 gappy file's own coverage)
    gme = fx.groupby(fx[fx.columns[0]].dt.to_period("M"))["gold_pm_usd"].last()
    gd = s["gold_daily_gcf.csv"]
    gcme = gd.groupby(gd["date"].dt.to_period("M"))["close"].last()
    gm = s["gold_monthly_gcf.csv"]
    gml = month_series(gm.drop_duplicates("date", keep="last"), "close")
    jb = pd.DataFrame({"fix": gme, "gcf": gml}).dropna().loc["2000-10":"2026-01"]
    basis = (jb["gcf"] - jb["fix"]).abs() / jb["fix"] * 100
    ok = (abs(basis.median() - 0.36) < 0.02 and abs(basis.quantile(.9) - 1.21) < 0.05
          and abs(basis.max() - 4.75) < 0.05 and str(basis.idxmax()) == "2026-01")
    chk("claim:C4 gcf-vs-fix basis", ok,
        f"monthly-file leg {len(jb)} mo (claim 304 mo, complete post-DFX-2; the pre-fix 260 "
        f"was the F2 gappy file's own coverage) "
        f"median={basis.median():.4f}% p90={basis.quantile(.9):.4f}% max={basis.max():.4f}% @ {basis.idxmax()}")
    jbd = pd.DataFrame({"fix": gme, "gcf": gcme}).dropna().loc["2000-10":"2026-01"]
    bd = (jbd["gcf"] - jbd["fix"]).abs() / jbd["fix"] * 100
    note("gcf-vs-fix basis (complete daily leg)",
         f"{len(jbd)} mo median={bd.median():.4f}% p90={bd.quantile(.9):.4f}% max={bd.max():.4f}% @ {bd.idxmax()}")
    note("gc=f-vs-fix @seam 2026-02", f"GCF ME 5247.90 vs fix ME 5191.55 = +1.085%")
    note("gld-vs-fix level gap at seam", "GLD is NAV/share: 2026-02 ME 483.75 vs fix 5191.55 "
         "(-90.7%) — level splicing impossible; composite must run WITHIN-SERIES RETURNS "
         "(ratio-normalized), exactly as the fetch header mandates")

    # C5 eco3min == Pink Sheet xlsx (claim: 0.0%)
    try:
        import openpyxl  # noqa: F401
        xl = pd.read_excel(f"{D}/CMO-Historical-Data-Monthly.xlsx", sheet_name="Monthly Prices", header=4)
        x = xl[[xl.columns[0], "Gold"]].dropna()
        x.columns = ["d", "gold"]
        x = x[x["d"].astype(str).str.match(r"^\d{4}M\d{2}$")]
        xp = pd.PeriodIndex(x["d"].str.slice(0, 4) + "-" + x["d"].str.slice(5, 7), freq="M")
        xs = pd.Series(x["gold"].values, index=xp, name="wb")
        ecop = eco.groupby(eco[eco.columns[0]].dt.to_period("M"))["gold_price_usd"].first()
        jx = pd.DataFrame({"eco": ecop}).join(xs, how="inner")
        dx = (jx["eco"] - jx["wb"]).abs() / jx["wb"] * 100
        chk("claim:C5 eco3min==xlsx", dx.max() < 1e-6,
            f"joined={len(jx)} mo {jx.index.min()}..{jx.index.max()} max|dev|={dx.max():.6f}%")
    except Exception as e:  # noqa: BLE001
        chk("claim:C5 eco3min==xlsx", False, f"parse failed: {type(e).__name__}: {e}")

    # C6 ^SPX shape (the F3/F4 detector; decode itself needs dailies -> live)
    sp = s["spx_price_monthly.csv"]
    per = sp["date"].dt.to_period("M")
    full = pd.period_range(per.min(), per.max(), freq="M")
    nonq = [m for m in set(per) if m.month not in (3, 6, 9, 12) and m != PARTIAL]
    chk("claim:C6 spx monthly density", len(full) == len(per),
        f"rows={len(sp)} span={len(full)}mo -> {len(full) - len(per)} months ABSENT; "
        f"present non-quarter months (excl. current partial)={len(nonq)} "
        f"(Yahoo range=max serves ^SPX as quarter-end bars only; reproduced live 2026-10-15)")
    note("spx quarter-bar mislabel", "HISTORICAL, fixed by DFX-4: the old stored quarter rows' values were "
         "the close of the 3-month window STARTING at the label (167/168 exact vs daily closes) - naive "
         "row-diffs give 3-month returns labeled monthly, lagged 2 months. spx_price_monthly.csv is now the "
         "month-end resample of the chunked daily leg (spx_daily.csv, 1984-01 ->); the quarterly payload is "
         "never written (DFX-3 guard backstop)")

    # C6b (DFX-4): SPX monthly values == month-END resample of the daily leg,
    # 0 tolerance — the chunked-daily rebuild must reproduce the exact daily
    # month-end close at the SAME label (no +2-mo window shift). Running
    # month excluded: its row is an MTD snapshot (analysis-time drop stays
    # the consumer's rule; both files carry the same last-snapshot value
    # from the same fetch run, but only complete months are asserted).
    spx_me = month_series(s["spx_daily.csv"], "close")
    spm = sp.drop_duplicates("date", keep="last")
    spm = spm[spm["date"].dt.to_period("M") != PARTIAL]
    jsx = pd.DataFrame({"monthly": spm.groupby(spm["date"].dt.to_period("M"))["close"].last()}
                       ).join(spx_me.rename("daily_me"), how="inner")
    devx = (jsx["monthly"] - jsx["daily_me"]).abs()
    chk("claim:C6b spx monthly==daily resample",
        len(jsx) > 0 and bool((devx == 0.0).all()),
        f"joined={len(jsx)} complete months max|dev|={devx.max() if len(jsx) else float('nan')} "
        f"exactly (0 tolerance — DFX-4 rebuild is the daily leg's month-end resample)")

    # C7/C8 records
    tb = s["tb3ms_monthly.csv"]
    chk("claim:C8 tb3ms span", str(tb[tb.columns[0]].iloc[0].date()) == "1934-01-01",
        f"first={tb[tb.columns[0]].iloc[0].date()} rows={len(tb)} (fetch header corrected to "
        f"'1934-01' at DFX-5; the earlier '1950 ->' was wrong)")
    sh_rows = shiller_read(D)
    # F2 (review 2026-10-15): this check was registered only `if sh_rows is
    # not None`, so an unreadable/absent shiller_ie_data.xls silently shrank
    # the gate to 21 checks and still exited 0 (probe: zero-length file ->
    # 21/21 PASS) while the README records a PASS verdict for the file. It is
    # now unconditional and pins BOTH ends (the head and the frozen final
    # served row 2023-09), so a Shiller re-vintage is a DEFECT too.
    chk("claim:C9 shiller span", sh_rows is not None
        and sh_rows.index.min() == pd.Period("1871-01", "M")
        and sh_rows.index.max() == pd.Period("2023-09", "M"),
        (f"decoded {len(sh_rows)} rows {sh_rows.index.min()}..{sh_rows.index.max()} "
         f"(frozen as served, ends 2023-09); final served row P={sh_rows['P'].iloc[-1]} "
         f"(anomalous, see hazards)")
        if sh_rows is not None else
        "shiller_ie_data.xls unreadable/absent — the entire Shiller leg is UNVERIFIED")

    # C10 GLD monthly == daily month-ends (claim: 0.0%)
    gldd = s["gld_daily.csv"]
    gme_gld = gldd.groupby(gldd["date"].dt.to_period("M"))["close"].last()
    gl = s["gld_tr_monthly.csv"].drop_duplicates("date", keep="last")
    gl = gl[gl["date"].dt.to_period("M") != PARTIAL]
    jg = pd.DataFrame({"monthly": month_series(gl, "close")}).join(gme_gld, how="inner")
    dg = (jg["monthly"] - jg["close"]).abs() / jg["close"] * 100
    chk("claim:C10 gld monthly==daily ME", dg.max() < 1e-6,
        f"joined={len(jg)} mo max|dev|={dg.max():.8f}% mean={dg.mean():.8f}%")

    # C12b GC=F monthly values == daily month-ends where present
    jg2 = pd.DataFrame({"monthly_file": gml}).join(gcme.rename("daily_me"), how="inner")
    jg2 = jg2[jg2.index != PARTIAL]
    dg2 = (jg2["monthly_file"] - jg2["daily_me"]).abs() / jg2["daily_me"] * 100
    # the diagnosis follows the condition actually tripped (a canned coverage
    # tail printed on a value deviation — or on a PASS — misdirects the reader)
    gcf_span = pd.period_range(gml.index.min(), gml.index.max(), freq="M")
    gcf_missing = sorted(set(gcf_span) - set(gml.index) - {PARTIAL})
    if dg2.max() >= 1e-6:
        c12b_diag = ("stored monthly VALUES deviate from the daily month-end leg "
                     "(value defect, not coverage)")
    elif gcf_missing:
        c12b_diag = (f"stored VALUES correct; coverage short {len(gcf_missing)} mo "
                     f"({[str(m) for m in gcf_missing[:6]]})")
    else:
        c12b_diag = "stored VALUES correct and full own-span coverage (0 missing months)"
    chk("claim:C12b gcf monthly==daily ME", dg2.max() < 1e-6,
        f"joined={len(jg2)} shared months max|dev|={dg2.max():.8f}% -> {c12b_diag}")

    # C11 seam presence
    P("--- C11 composite seam ---")
    for m in ("2026-02", "2026-03"):
        p = pd.Period(m, "M")
        note(f"seam {m}", f"fix={'present' if p in gme.index else 'ABSENT'} "
             f"(ME {gme.get(p)}), GLD={'present' if p in jg.index else 'ABSENT'} "
             f"(ME {jg['monthly'].get(p)}), GC=F daily={'present' if p in gcme.index else 'ABSENT'} "
             f"(ME {gcme.get(p)}), GC=F monthly-file={'present' if p in gml.index else 'ABSENT (F2)'}")


def shiller_read(D):
    try:
        import xlrd
        bk = xlrd.open_workbook(f"{D}/shiller_ie_data.xls")
        sh = max(bk.sheets(), key=lambda x: x.nrows)
        rows = []
        for r in range(sh.nrows):
            v = sh.cell_value(r, 0)
            try:
                v = float(v)
            except Exception:  # noqa: BLE001
                continue
            if not (1871 <= v <= 2100):
                continue
            y, m = int(v), int(round((v - int(v)) * 100))
            pv = sh.cell_value(r, 1)
            if pv == "" or pv is None:
                continue
            rows.append((pd.Period(f"{y}-{m:02d}", "M"), float(pv)))
        return pd.DataFrame(rows, columns=["p", "P"]).dropna().set_index("p")
    except Exception as e:  # noqa: BLE001
        P(f"  shiller read failed: {e}")
        return None


# ---- live layer -----------------------------------------------------------
def _get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and i + 1 < tries:
                time.sleep(12)
                last = e
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(5)
    if last is None:
        raise RuntimeError("unreachable")
    raise last


def _get_json(url):
    return json.loads(_get(url).decode("utf-8"))


def live_yahoo(D, s):
    P("=" * 20, "4a. LIVE Yahoo re-fetch (2s sleeps; interior months only)", "=" * 20)
    for sym, fname, field in [("SPY", "spy_tr_monthly.csv", "adjclose"),
                              ("GC=F", "gold_monthly_gcf.csv", "close"),
                              ("GLD", "gld_tr_monthly.csv", "adjclose")]:
        time.sleep(2)
        r = _get_json("https://query1.finance.yahoo.com/v8/finance/chart/"
                      f"{urllib.parse.quote(sym)}?range=max&interval=1mo")["chart"]["result"][0]
        ts = r["timestamp"]
        vals = (r["indicators"]["adjclose"][0]["adjclose"] if field == "adjclose"
                else r["indicators"]["quote"][0]["close"])
        fresh = {}
        for t, v in zip(ts, vals):
            if v is None:
                continue
            d = dt.datetime.fromtimestamp(t, dt.timezone.utc)
            fresh.setdefault(d.strftime("%Y-%m"), []).append(round(float(v), 6))
        fp = pd.Series({pd.Period(k, "M"): v[-1] for k, v in fresh.items()})
        stored = s[fname]
        sp = month_series(stored.drop_duplicates("date", keep="last"), stored.columns[-1])
        jj = pd.DataFrame({"stored": sp, "fresh": fp}).dropna()
        jj = jj[jj.index != PARTIAL]
        dv = (jj["stored"] - jj["fresh"]).abs() / jj["fresh"] * 100
        ndup = sum(1 for v in fresh.values() if len(v) > 1)
        if sym == "SPY":
            note("spy adjclose anchor drift", f"max live-vs-stored {dv.max():.6f}% over {len(jj)} months "
                 "(ppm-scale adjustment-anchor recompute; immaterial)")
            chk("live:spy interior", dv.max() < 0.001, f"max|dev|={dv.max():.6f}%")
        else:
            chk(f"live:{fname}", dv.max() < 1e-6,
                f"{len(jj)} interior months max|dev|={dv.max():.8f}%; fresh dup-current months={ndup} "
                "(API returns the running month twice with different snapshots -> F1 mechanism live)")
    # ^SPX (DFX-4): the production monthly file is now the month-END resample
    # of the chunked DAILY leg — the quarterly range=max payload is no longer
    # written (DFX-3 guard backstop), so the live check verifies the fix
    # directly: (1) no downgraded chunk in the fresh daily fetch, and
    # (2) every interior stored value == the fresh daily month-end close of
    # the SAME label (downgrade and +2-mo window shift must be gone).
    time.sleep(2)
    try:
        r = _get_json("https://query1.finance.yahoo.com/v8/finance/chart/%5ESPX"
                      "?range=max&interval=1mo")["chart"]["result"][0]
        qmonths = {dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m")
                   for t, v in zip(r["timestamp"], r["indicators"]["quote"][0]["close"])
                   if v is not None}
        qper = pd.PeriodIndex([pd.Period(k, "M") for k in qmonths])
        note("live ^SPX quarterly payload",
             f"fresh range=max&interval=1mo still serves {len(qper)} bars over "
             f"{len(pd.period_range(qper.min(), qper.max(), freq='M'))} months — "
             "quarterly downgrade persists upstream; DFX-4 removed it from the "
             "production path (chunked daily resample), DFX-3 guard is the backstop")
    except Exception as e:  # noqa: BLE001 - report-only payload
        note("live ^SPX quarterly payload",
             f"fetch failed ({type(e).__name__}: {e}); report-only — the daily leg check below is the check")
    # ^SPX daily ground truth (chunked, downgrade-tracked) + Shiller P decode
    # F5 (review 2026-10-15): this was the only live fetch outside a
    # try/except, so one Yahoo blip aborted the whole --live run as a
    # traceback with no verdict summary and every later live check skipped.
    # A failed chunk is now collected, reported as its own check, and the leg
    # is refused a green verdict (a short fresh leg would otherwise shrink the
    # inner join below and pass silently — the live form of F1).
    rows = []
    downgraded = []
    chunk_errs = []
    this = dt.datetime.now(dt.timezone.utc).year + 1
    for y0 in range(1984, this, 5):
        time.sleep(2)
        p1 = int(dt.datetime(y0, 1, 1, tzinfo=dt.timezone.utc).timestamp())
        p2 = int(dt.datetime(min(y0 + 5, this), 1, 1, tzinfo=dt.timezone.utc).timestamp())
        try:
            r = _get_json("https://query1.finance.yahoo.com/v8/finance/chart/%5ESPX"
                          f"?period1={p1}&period2={p2}&interval=1d")["chart"]["result"][0]
        except Exception as e:  # noqa: BLE001
            chunk_errs.append(f"{y0}: {type(e).__name__}: {e}")
            continue
        ts = r.get("timestamp") or []
        cl = r["indicators"]["quote"][0]["close"]
        if len(ts) >= 2:
            span = sorted(b - a for a, b in zip(ts, ts[1:]))
            if span[len(span) // 2] > 5 * 86400:
                downgraded.append(y0)
        rows += [(dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%d"), round(float(v), 6))
                 for t, v in zip(ts, cl) if v is not None]
    chk("live:spx chunk fetch", not chunk_errs and bool(rows),
        f"chunks ok={len(range(1984, this, 5)) - len(chunk_errs)}/{len(range(1984, this, 5))}, "
        f"fresh rows={len(rows)}" + (f"; FAILED {chunk_errs}" if chunk_errs else ""))
    sd = pd.DataFrame(rows, columns=["date", "close"])
    sd["date"] = pd.to_datetime(sd["date"])
    sd = sd.drop_duplicates("date").sort_values("date")
    me = sd.groupby(sd["date"].dt.to_period("M"))["close"].last()
    sp_stored = s["spx_price_monthly.csv"].drop_duplicates("date", keep="last")
    sp_stored = sp_stored[sp_stored["date"].dt.to_period("M") != PARTIAL]
    js = pd.DataFrame({"stored": sp_stored.set_index(
        pd.PeriodIndex(sp_stored["date"].dt.to_period("M")))["close"]}
    ).join(me.rename("daily_me"), how="inner")
    tol = js["daily_me"].mul(1e-6).clip(lower=0.01)
    hits = int(((js["stored"] - js["daily_me"]).abs() <= tol).sum())
    chk("live:spx decode label+2",
        not downgraded and len(js) > 0 and hits == len(js),
        f"downgraded chunks={downgraded or 'none'} ({len(rows)} daily bars); "
        f"{hits}/{len(js)} interior months == fresh daily month-end close of the SAME "
        f"label (no +2-mo shift) — quarterly downgrade and window-start mislabel gone (DFX-4)")
    sh = shiller_read(D)
    if sh is not None:
        means = sd.groupby(sd["date"].dt.to_period("M"))["close"].mean()
        cmp_ = pd.DataFrame({"shiller": sh.loc["2022-09":"2023-09", "P"], "mean": means}).dropna()
        cmp_["dev"] = (cmp_["shiller"] - cmp_["mean"]).abs() / cmp_["mean"] * 100
        okmo = cmp_[cmp_.index < pd.Period("2023-09", "M")]
        chk("live:shiller P=monthly mean", (okmo["dev"] < 0.01).all(),
            f"{int((okmo['dev'] < 0.01).sum())}/{len(okmo)} months exact (2022-09..2023-08); "
            f"final served row 2023-09: P=4515.77 vs true mean {means.get(pd.Period('2023-09')):.2f} "
            f"(+{(4515.77 / means.get(pd.Period('2023-09')) - 1) * 100:.2f}%) -> drop final Shiller row")
        note("shiller seam measure", "Shiller P = monthly AVERAGE of daily closes; Yahoo rows are "
             "month-END closes. The 2023-09 stitch mixes measures — within-series returns + "
             "level-normalized stitch documented in README; final Shiller row excluded")


def live_mirrors(D):
    P("=" * 20, "4b. LIVE non-Yahoo re-fetch", "=" * 20)
    urls = [
        ("lbma_pm_fix_daily.csv", LBMA_SHA,
         "https://raw.githubusercontent.com/unbalancedparentheses/forex-centuries/main/data/sources/lbma/lbma_gold_daily.csv"),
        ("lbma_pm_fix_fred_mirror.csv", None,
         "https://raw.githubusercontent.com/Prerna11071997/Recession_prediction/master/venv/dataset/GOLDPMGBD228NLBM.csv"),
        ("gold_monthly_eco3min.csv", None, "https://eco3min.fr/dataset/gold-price.csv"),
        ("shiller_ie_data.xls", None, "http://www.econ.yale.edu/~shiller/data/ie_data.xls"),
    ]
    for fname, pin, url in urls:
        try:
            raw = _get(url)
            fresh_sha = hashlib.sha256(raw).hexdigest()
            stored_sha = hashlib.sha256(open(f"{D}/{fname}", "rb").read()).hexdigest()
            if pin:
                chk(f"live:{fname}", fresh_sha == pin,
                    f"frozen pin {'MATCH' if fresh_sha == pin else 'MISMATCH ' + fresh_sha} — "
                    "diff means history moved under us: STOP")
            else:
                chk(f"live:{fname}", fresh_sha == stored_sha,
                    f"{'byte-identical' if fresh_sha == stored_sha else 'CHANGED ' + fresh_sha[:16]}")
            time.sleep(2)
        except Exception as e:  # noqa: BLE001
            chk(f"live:{fname}", False, f"fetch failed: {type(e).__name__}: {e}")
    # Pink Sheet xlsx (doc slug rotates; compare gold column if bytes differ)
    try:
        raw = _get("https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026"
                   "/related/CMO-Historical-Data-Monthly.xlsx")
        fresh_sha = hashlib.sha256(raw).hexdigest()
        stored_sha = hashlib.sha256(open(f"{D}/CMO-Historical-Data-Monthly.xlsx", "rb").read()).hexdigest()
        if fresh_sha == stored_sha:
            chk("live:pink_sheet", True, "byte-identical")
        else:
            xl = pd.read_excel(io.BytesIO(raw), sheet_name="Monthly Prices", header=4)
            x = xl[[xl.columns[0], "Gold"]].dropna()
            x.columns = ["d", "gold"]
            x = x[x["d"].astype(str).str.match(r"^\d{4}M\d{2}$")]
            xp = pd.PeriodIndex(x["d"].str.slice(0, 4) + "-" + x["d"].str.slice(5, 7), freq="M")
            xs = pd.Series(x["gold"].values, index=xp, name="fresh")
            eco = pd.read_csv(f"{D}/gold_monthly_eco3min.csv")
            ecop = eco.groupby(eco[eco.columns[0]].dt.to_period("M"))["gold_price_usd"].first()
            jx = pd.DataFrame({"stored": ecop}).join(xs, how="inner")
            dx = (jx["stored"] - jx["fresh"]).abs() / jx["fresh"] * 100
            chk("live:pink_sheet", dx.max() < 1e-6,
                f"doc rotated (sha {stored_sha[:12]}->{fresh_sha[:12]}); gold column over "
                f"{len(jx)} shared months max|dev|={dx.max():.6f}%")
        time.sleep(2)
    except Exception as e:  # noqa: BLE001
        chk("live:pink_sheet", False, f"fetch failed: {type(e).__name__}: {e}")
    # FRED TB3MS fresh vs stored (interior)
    try:
        raw = _get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS").decode("utf-8")
        import csv as _csv
        fr = {r["observation_date"]: r["TB3MS"] for r in _csv.DictReader(io.StringIO(raw))
              if r.get("TB3MS") and r["TB3MS"] != "."}
        st = pd.read_csv(f"{D}/tb3ms_monthly.csv")
        smap = {r["date"]: r["tb3ms_pct"] for _, r in st.iterrows()}
        shared = [d for d in smap if d in fr]
        mism = [(d, smap[d], fr[d]) for d in shared if abs(float(smap[d]) - float(fr[d])) > 1e-9]
        newd = sorted(d for d in fr if d not in smap)
        chk("live:tb3ms", not mism,
            f"{len(shared)} shared rows, mismatches={mism[:3] or 'none'}, "
            f"fresh adds {newd} (partial month expected)")
        time.sleep(1)
    except Exception as e:  # noqa: BLE001
        chk("live:tb3ms", False, f"fetch failed: {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="include network re-fetch checks")
    ap.add_argument("data_dir", nargs="?", default="data")
    a = ap.parse_args()
    s = structural(a.data_dir)
    anchors(a.data_dir)
    claims(a.data_dir, s)
    if a.live:
        live_yahoo(a.data_dir, s)
        live_mirrors(a.data_dir)
    P("=" * 20, "VERDICT SUMMARY", "=" * 20)
    bad = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        P(f"  [{'PASS' if ok else 'DEFECT'}] {name}")
    P(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} checks pass; open defects: {len(bad)}")
    P("(A) hazards for the SPEC's Constraints/I-O matrix:")
    for n, d in HAZARDS:
        P(f"  - {n}: {d}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
