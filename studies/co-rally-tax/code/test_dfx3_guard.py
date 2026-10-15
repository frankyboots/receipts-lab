#!/usr/bin/env python3
"""test_dfx3_guard.py — DFX-3 unit tests: per-file monthly coverage guard.

The fetch script writes a monthly-named file after every Yahoo monthly job.
DFX-3 adds a guard that detects, PER FILE, that such a file does not cover
its OWN [first_date, PARTIAL] period range at a genuine monthly density, and
aborts the fetch before the file is written. The recorded instance (F3): a
Yahoo range=max monthly request silently DOWNGRADED ^SPX to quarter-end bars
(169 rows over a 503-month span) stored under a monthly name. Thresholds are
per DECISIONS DFX-3: any gap > 2 consecutive months, OR coverage < 80% of the
file's own span.

Covers the SPEC matrix rows:
  - "Quarterly-downgraded payload (<=1 row per 3 months) arrives for a
    monthly-named file" -> guard aborts non-zero; nothing partial lands in
    data/.
  - "File's own period range vs row count after fix" -> guard trips on a
    threshold breach (gap > 2 consecutive months or coverage < 80% of own
    span); complete ETF/futures monthly files pass.
Plus the empty-file guard DFX-2 deferred to this cap.

Deterministic, network-free (synthetic payloads only; the network layer `get`
is monkeypatched to return canned bytes). stdlib unittest; run with:

    ~/receipts-lab/.venv/bin/python code/test_dfx3_guard.py
"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import fetch_gold_spx_bills as fetch


def ts(year, month, day=15):
    """Epoch of a UTC timestamp inside the given month (payload order is
    chronological, as Yahoo serves it)."""
    return int(dt.datetime(year, month, day, tzinfo=dt.timezone.utc).timestamp())


def months_between(y0, m0, y1, m1):
    """Inclusive chronological list of (year, month) tuples."""
    out = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def row_list(ym_list, base=100.0, step=1.0):
    """Final-file rows '(YYYY-MM-01, value)' for a list of (year, month)."""
    return [(f"{y:04d}-{m:02d}-01", round(base + i * step, 2))
            for i, (y, m) in enumerate(ym_list)]


def ts_values(ym_list, base=100.0, step=1.0):
    """(timestamp, value) pairs for a list of (year, month), in order."""
    return [(ts(y, m), round(base + i * step, 2)) for i, (y, m) in enumerate(ym_list)]


def make_payload(ym_list, base=100.0, step=1.0):
    """Raw bytes as `get` would hand back from Yahoo, carrying BOTH the
    `quote.close` and `adjclose.adjclose` arrays so either field works."""
    ts_list = [ts(y, m) for y, m in ym_list]
    vals = [round(base + i * step, 2) for i in range(len(ym_list))]
    indicators = {
        "adjclose": [{"adjclose": vals}],
        "quote": [{"close": vals}],
    }
    payload = json.dumps({"chart": {"result": [
        {"timestamp": ts_list, "indicators": indicators}
    ]}})
    return payload.encode("utf-8")


# --- canned (year, month) shapes ------------------------------------------
def quarterly_ym():
    """Quarter-end months only (Mar/Jun/Sep/Dec) over a long span — the shape
    of a Yahoo range=max monthly request silently downgraded to quarter-end
    bars (F3: ~169 rows over a ~503-month span); ~33% of the span is present."""
    return [(y, m) for y in range(1985, 2025) for m in (3, 6, 9, 12)]


def complete_ym():
    """Every month of a 24-month span — a sound monthly payload."""
    return months_between(2024, 1, 2025, 12)


def gap3_ym():
    """18-month span with a 3-month hole (2024-04/05/06 absent): coverage
    15/18 = 83% (>= 80%, so the coverage rule does NOT trip) but a gap of 3
    consecutive missing months (> 2) DOES trip."""
    return [ym for ym in months_between(2024, 1, 2025, 6)
            if ym not in ((2024, 4), (2024, 5), (2024, 6))]


def gap2_ym():
    """12-month span with a 2-month hole (2024-05/06 absent): coverage 10/12
    = 83% (>= 80%) and max gap = 2 (NOT > 2) -> the guard PASSES."""
    return [ym for ym in months_between(2024, 1, 2024, 12)
            if ym not in ((2024, 5), (2024, 6))]


class GuardPureFunctionTest(unittest.TestCase):
    """check_monthly_coverage(rows, symbol, fname): the per-file coverage
    guard on the final rows, judged on the file's OWN span."""

    def test_empty_file_trips(self):
        # A monthly-named file with no rows covers nothing (empty-file
        # guarding deferred from DFX-2 to this cap).
        with self.assertRaises(fetch.MonthlyCoverageGuardAbort) as cm:
            fetch.check_monthly_coverage([], "SYM", "x.csv")
        self.assertEqual(cm.exception.span_months, 0)
        self.assertIn("empty", cm.exception.reason)

    def test_complete_file_passes(self):
        # Every month of the span present -> 100% coverage, no gap -> sound.
        self.assertIsNone(fetch.check_monthly_coverage(
            row_list(complete_ym()), "GLD", "gld_tr_monthly.csv"))

    def test_single_month_file_passes(self):
        # Degenerate but sound: a file spanning one month and containing it.
        self.assertIsNone(fetch.check_monthly_coverage(
            [("2025-06-01", 1.0)], "SYM", "x.csv"))

    def test_quarterly_payload_trips_on_coverage(self):
        # Quarter-end bars over a long span: ~33% coverage < 80% -> trips on
        # the coverage rule. The gap rule alone would NOT catch a clean
        # quarter cadence (max run of missing months is only 2).
        ym = quarterly_ym()
        with self.assertRaises(fetch.MonthlyCoverageGuardAbort) as cm:
            fetch.check_monthly_coverage(row_list(ym), "^SPX", "spx_price_monthly.csv")
        self.assertIn("coverage", cm.exception.reason)
        self.assertEqual(cm.exception.max_gap, 2)
        self.assertEqual(cm.exception.present, len(ym))
        self.assertEqual(cm.exception.span_months,
                         len(fetch._span_months("1985-03", "2024-12")))

    def test_gap_of_three_consecutive_months_trips_on_gap(self):
        # Coverage 83% would pass, but a 3-month hole (> 2) trips on the gap
        # rule — proving the OR of the two thresholds.
        with self.assertRaises(fetch.MonthlyCoverageGuardAbort) as cm:
            fetch.check_monthly_coverage(row_list(gap3_ym()),
                                        "GC=F", "gold_monthly_gcf.csv")
        self.assertEqual(cm.exception.max_gap, 3)
        self.assertIn("gap of 3", cm.exception.reason)
        self.assertEqual(cm.exception.present, 15)
        self.assertEqual(cm.exception.span_months, 18)

    def test_gap_of_two_consecutive_months_passes(self):
        # Exactly 2 consecutive missing months is NOT > 2, and coverage
        # 10/12 = 83% is NOT < 80% -> the guard passes (threshold boundary).
        self.assertIsNone(fetch.check_monthly_coverage(
            row_list(gap2_ym()), "SYM", "x.csv"))

    def test_short_span_single_hole_trips_on_coverage(self):
        # The DFX-2 `daily_fname=None` shape: 2025-01 + 2025-03 (2025-02
        # missing). Coverage 2/3 = 67% < 80% -> trips on coverage.
        rows = [("2025-01-01", 100.0), ("2025-03-01", 102.0)]
        with self.assertRaises(fetch.MonthlyCoverageGuardAbort) as cm:
            fetch.check_monthly_coverage(rows, "GC=F", "spx_price_monthly.csv")
        self.assertIn("coverage", cm.exception.reason)


class FetchYahooGuardWiringTest(unittest.TestCase):
    """End-to-end through fetch_yahoo() on synthetic payloads (network layer
    monkeypatched): a quarterly payload aborts BEFORE the file is written
    (nothing partial lands in data/); complete ETF/futures monthlies pass and
    are written; a 3-month hole aborts on the gap rule."""

    def _yahoo(self, payload, symbol, fname, field, data_dir, **kwargs):
        with mock.patch.object(fetch, "get", return_value=payload), \
                mock.patch("time.sleep", lambda s=None: None):
            return fetch.fetch_yahoo(symbol, fname, field, data_dir, **kwargs)

    def test_quarterly_payload_aborts_before_write_no_partial_file(self):
        # The recorded F3 instance: a monthly-named file fed quarter-end bars.
        # The guard trips BEFORE write_csv, so no partial file lands in data/.
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "spx_price_monthly.csv")
            with self.assertRaises(fetch.MonthlyCoverageGuardAbort) as cm:
                self._yahoo(make_payload(quarterly_ym()),
                            "^SPX", "spx_price_monthly.csv", "close", tmp)
            self.assertIn("coverage", cm.exception.reason)
            self.assertFalse(os.path.exists(target),
                             "abort must happen BEFORE the file is written")

    def test_complete_etf_monthly_passes_and_writes(self):
        # GLD (ETF) total-return monthly: a complete payload passes the guard
        # and the file is written with one row per month.
        with tempfile.TemporaryDirectory() as tmp:
            n = self._yahoo(make_payload(complete_ym()),
                            "GLD", "gld_tr_monthly.csv", "adjclose", tmp)
            self.assertEqual(n, 24, "one row per month of the span")
            target = os.path.join(tmp, "gld_tr_monthly.csv")
            with open(target) as f:
                lines = f.read().splitlines()
            self.assertEqual(lines[0], "date,close")
            self.assertEqual(len(lines), 25, "header + 24 rows")
            self.assertEqual(lines[1], "2024-01-01,100.0")
            self.assertEqual(lines[2], "2024-02-01,101.0")

    def test_complete_futures_monthly_passes_without_daily_leg(self):
        # GC=F monthly, daily_fname=None (no backfill wired): a complete
        # payload passes the guard and is written.
        with tempfile.TemporaryDirectory() as tmp:
            n = self._yahoo(make_payload(complete_ym()),
                            "GC=F", "gold_monthly_gcf.csv", "close", tmp)
            self.assertEqual(n, 24)
            self.assertTrue(os.path.exists(
                os.path.join(tmp, "gold_monthly_gcf.csv")))

    def test_gap_of_three_months_aborts_via_fetch_yahoo(self):
        # Coverage 83% would pass the coverage rule, but a 3-month hole trips
        # the gap rule — aborts before write through the real fetch path.
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "gold_monthly_gcf.csv")
            with self.assertRaises(fetch.MonthlyCoverageGuardAbort) as cm:
                self._yahoo(make_payload(gap3_ym()),
                            "GC=F", "gold_monthly_gcf.csv", "close", tmp)
            self.assertEqual(cm.exception.max_gap, 3)
            self.assertFalse(os.path.exists(target))

    def test_gap_of_two_months_writes(self):
        # Exactly-2-month hole + 83% coverage -> the guard passes and the
        # file is written (thresholds are strictly >2 / <80%).
        with tempfile.TemporaryDirectory() as tmp:
            n = self._yahoo(make_payload(gap2_ym()),
                            "GC=F", "gold_monthly_gcf.csv", "close", tmp)
            self.assertEqual(n, 10)
            self.assertTrue(os.path.exists(
                os.path.join(tmp, "gold_monthly_gcf.csv")))


class MainExitCodeTest(unittest.TestCase):
    """SPEC success: a quarterly payload 'exits non-zero' (unit test). The
    guard's MonthlyCoverageGuardAbort is a plain Exception, so main() maps it
    to a failed job and exits 1. Review F4 (2026-10-15): this is NOT 'every
    other job stubbed' — 7 of the 13 jobs are mocked, and in this scenario
    four unstubbed jobs fail too (^SPX via the daily-chunk downgrade
    ValueError, SPY via the DFX-3 guard, GC=F and GLD via the DFX-2
    both-legs abort), so the assertion below proves 'exit != 0 and no spx
    monthly file was written', not the guard alone. fetch_yahoo_daily is
    stubbed here, so fetch_spx_monthly's own DFX-3 backstop has no
    main()-level test (its wiring test is FetchYahooGuardWiringTest)."""

    def test_main_exits_nonzero_when_quarterly_payload_reaches_monthly_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fetch, "fetch_fred_tb3ms", return_value=1), \
                 mock.patch.object(fetch, "fetch_yahoo_daily", return_value=1), \
                 mock.patch.object(fetch, "fetch_shiller", return_value=1), \
                 mock.patch.object(fetch, "fetch_lbma_mirror", return_value=1), \
                 mock.patch.object(fetch, "fetch_lbma_fred_mirror", return_value=1), \
                 mock.patch.object(fetch, "fetch_pink_sheet", return_value=1), \
                 mock.patch.object(fetch, "fetch_eco3min_gold", return_value=1), \
                 mock.patch.object(fetch, "get",
                                   return_value=make_payload(quarterly_ym())), \
                 mock.patch("time.sleep", lambda s=None: None):
                old_argv = sys.argv
                sys.argv = ["fetch_gold_spx_bills.py", "--outdir", tmp]
                try:
                    with self.assertRaises(SystemExit) as cm:
                        fetch.main()
                finally:
                    sys.argv = old_argv
            self.assertNotEqual(
                cm.exception.code, 0,
                "a quarterly ^SPX/SPY payload must make the fetch exit non-zero")
            self.assertFalse(os.path.exists(
                os.path.join(tmp, "spx_price_monthly.csv")),
                "no partial quarterly file may land in the out dir")


if __name__ == "__main__":
    unittest.main(verbosity=2)
