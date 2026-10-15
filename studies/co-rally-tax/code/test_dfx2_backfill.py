#!/usr/bin/env python3
"""test_dfx2_backfill.py — DFX-2 unit tests: None-close backfill from the
daily leg + loud abort when both legs lack a month.

Deterministic, network-free (synthetic payloads only; the network layer
`get` is monkeypatched to return canned bytes; daily legs are real temp
CSVs, not fetched). stdlib unittest; run with:

    ~/receipts-lab/.venv/bin/python code/test_dfx2_backfill.py

Covers the SPEC matrix rows:
  - "Monthly payload lacks a valid close for a month (GC=F
    holidays/suspensions)" -> month-end backfilled from the complete daily
    leg, byte-equal to the daily month-end.
  - "Month missing from BOTH monthly payload and daily leg" -> fetch aborts
    loudly (MonthlyCoverageAbort, non-zero exit via main()), no
    partial/holed file written.
"""
import datetime as dt
import json
import os
import tempfile
import unittest
from unittest import mock

import fetch_gold_spx_bills as fetch


def ts(year, month, day=15):
    """Epoch of a UTC timestamp inside the given month (payload order is
    chronological, as Yahoo serves it)."""
    return int(dt.datetime(year, month, day, tzinfo=dt.timezone.utc).timestamp())


def make_payload(months_ts_values, field="close"):
    """months_ts_values: list of (timestamp, value-or-None), in payload
    order. Returns raw bytes as `get` would hand back from Yahoo."""
    ts_list = [t for t, _ in months_ts_values]
    vals = [v for _, v in months_ts_values]
    if field == "adjclose":
        indicators = {"adjclose": [{"adjclose": vals}]}
    else:
        indicators = {"quote": [{"close": vals}]}
    payload = json.dumps({"chart": {"result": [
        {"timestamp": ts_list, "indicators": indicators}
    ]}})
    return payload.encode("utf-8")


class MonthEndMapTest(unittest.TestCase):
    """DFX-2 helper: {YYYY-MM: close of the last daily day in the month}."""

    def test_last_calendar_day_wins_per_month(self):
        rows = [
            ("2025-03-05", 10.0),
            ("2025-03-31", 12.5),
            ("2025-03-10", 11.0),  # out-of-order row: max date must win
            ("2025-02-28", 9.0),
        ]
        self.assertEqual(fetch.month_end_map(rows),
                         {"2025-02": 9.0, "2025-03": 12.5})

    def test_raw_strings_pass_through_untouched(self):
        # Byte-equal backfill requires the raw stored string to survive.
        rows = [("2025-04-30", "5247.900391")]
        self.assertIs(fetch.month_end_map(rows)["2025-04"], "5247.900391")


class BackfillMonthlyTest(unittest.TestCase):
    """Pure function: payload holes filled from daily month-ends; a month
    missing from BOTH legs raises MonthlyCoverageAbort."""

    def test_backfills_missing_month_from_daily_last_day(self):
        monthly = [
            ("2025-01-01", 100.0), ("2025-02-01", 101.0),
            # 2025-03 absent from the payload (None-close drop)
            ("2025-04-01", 103.0), ("2025-05-01", 104.0),
        ]
        daily = fetch.month_end_map([("2025-03-10", 102.0), ("2025-03-31", 102.5)])
        out = fetch.backfill_monthly(monthly, daily, "GC=F", "gold_monthly_gcf.csv")
        self.assertEqual(out, [
            ("2025-01-01", 100.0), ("2025-02-01", 101.0),
            ("2025-03-01", 102.5),  # backfilled: LAST daily day of the month
            ("2025-04-01", 103.0), ("2025-05-01", 104.0),
        ])

    def test_backfilled_value_is_exactly_the_daily_month_end(self):
        raw = "4186.700195"
        daily = fetch.month_end_map([("2026-09-30", raw)])
        out = fetch.backfill_monthly(
            [("2026-08-01", 1.0), ("2026-10-01", 2.0)], daily, "GC=F", "x.csv")
        self.assertIs(out[1][1], raw, "byte-equal to the daily month-end")

    def test_payload_present_month_wins_over_daily_leg(self):
        # Backfill fills holes only — it never overwrites payload values.
        out = fetch.backfill_monthly(
            [("2025-06-01", 55.5)], {"2025-06": 99.9}, "GC=F", "x.csv")
        self.assertEqual(out, [("2025-06-01", 55.5)])

    def test_mtd_running_month_retained_not_overwritten(self):
        # The running month's MTD snapshot stays in the file (analysis-time
        # drop is the consumer's rule); the daily leg does not replace it.
        out = fetch.backfill_monthly(
            [("2026-09-01", 1.0), ("2026-10-01", 4170.2)],
            {"2026-09": 0.5, "2026-10": 4199.9}, "GC=F", "x.csv")
        self.assertEqual(out, [("2026-09-01", 1.0), ("2026-10-01", 4170.2)])

    def test_multiple_consecutive_holes_all_backfilled(self):
        # The recorded F2 shape: a run of missing months (incl. the seam
        # months) all reconstructed from the daily leg.
        daily = fetch.month_end_map([
            ("2026-02-27", 5247.9), ("2026-03-31", 5150.0), ("2026-04-30", 5200.0)])
        out = fetch.backfill_monthly(
            [("2026-01-01", 1.0), ("2026-05-01", 2.0)], daily, "GC=F", "x.csv")
        self.assertEqual(out, [
            ("2026-01-01", 1.0), ("2026-02-01", 5247.9),
            ("2026-03-01", 5150.0), ("2026-04-01", 5200.0),
            ("2026-05-01", 2.0),
        ])

    def test_daily_months_outside_payload_span_ignored(self):
        # The file's span is the payload's span; the daily leg neither
        # extends it nor fills months outside it.
        monthly = [(f"2025-{m:02d}-01", 100.0 + m) for m in range(1, 7)]
        daily = fetch.month_end_map([("2024-12-31", 1.0), ("2025-07-31", 2.0)])
        out = fetch.backfill_monthly(monthly, daily, "GC=F", "x.csv")
        self.assertEqual(out, monthly, "no backfill, no span extension")

    def test_both_legs_gap_raises_loud_abort(self):
        # 2025-03 is in NEITHER leg: payload hole + daily leg gap.
        daily = fetch.month_end_map([("2025-02-28", 101.5), ("2025-04-30", 103.5)])
        monthly = [
            ("2025-01-01", 100.0), ("2025-02-01", 101.0),
            ("2025-04-01", 103.0),  # 2025-03 in neither leg
        ]
        with self.assertRaises(fetch.MonthlyCoverageAbort) as cm:
            fetch.backfill_monthly(monthly, daily, "GC=F", "gold_monthly_gcf.csv")
        self.assertEqual(cm.exception.missing, ["2025-03"])
        self.assertIn("2025-03", str(cm.exception))
        self.assertIn("BOTH", str(cm.exception))

    def test_hole_with_no_daily_leg_at_all_raises(self):
        # Empty daily_month_ends == daily leg absent/empty: every payload
        # hole is a both-legs-gap abort — never a silent hole.
        with self.assertRaises(fetch.MonthlyCoverageAbort):
            fetch.backfill_monthly(
                [("2025-01-01", 100.0), ("2025-03-01", 102.0)], {}, "GC=F", "x.csv")

    def test_empty_payload_has_no_span(self):
        # Empty payload -> nothing to cover; empty-file guarding belongs to
        # the DFX-3 per-file coverage guard, not this cap.
        self.assertEqual(fetch.backfill_monthly([], {"2025-01": 1.0}, "GC=F", "x.csv"), [])


class FetchYahooWiringTest(unittest.TestCase):
    """Production path fetch_yahoo(..., daily_fname=...) on synthetic
    payloads: backfill lands in the written file byte-equal to the daily
    leg; a both-legs-gap aborts BEFORE any file is written."""

    def _yahoo(self, payload, fname, data_dir, **kwargs):
        with mock.patch.object(fetch, "get", return_value=payload), \
                mock.patch("time.sleep", lambda s=None: None):
            return fetch.fetch_yahoo("GC=F", fname, "close", data_dir, **kwargs)

    @staticmethod
    def _daily_csv(tmp, fname, rows):
        with open(os.path.join(tmp, fname), "w", newline="") as f:
            f.write("date,close\n")
            for d, v in rows:
                f.write(f"{d},{v}\n")

    def test_targeted_refetch_backfills_and_writes_complete_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._daily_csv(tmp, "gold_daily_gcf.csv", [
                ("2025-03-10", "102.0"), ("2025-03-31", "5247.900391"),
                ("2026-02-27", "5247.900391"), ("2026-03-31", "5150.0"),
                ("2026-04-30", "5200.0"), ("2026-05-15", "4199.9")])
            # monthly payload: 2025-01 -> 2026-05 with holes at 2025-03,
            # 2026-02, 2026-03; the running month arrives twice with
            # different snapshots (DFX-1).
            payload = make_payload([
                (ts(2025, 1), 100.0), (ts(2025, 2), 101.0),
                (ts(2025, 4), 103.0), (ts(2025, 5), 104.0),
                (ts(2025, 6), 105.0), (ts(2025, 7), 106.0),
                (ts(2025, 8), 107.0), (ts(2025, 9), 108.0),
                (ts(2025, 10), 109.0), (ts(2025, 11), 110.0),
                (ts(2025, 12), 111.0),
                (ts(2026, 1), 5100.0), (ts(2026, 4), 5180.0),
                (ts(2026, 5, 15), 4107.9), (ts(2026, 5, 20), 4166.3)])
            n = self._yahoo(payload, "gold_monthly_gcf.csv", tmp,
                            daily_fname="gold_daily_gcf.csv")
            self.assertEqual(n, 17, "one row per month of the payload span")
            with open(os.path.join(tmp, "gold_monthly_gcf.csv")) as f:
                lines = f.read().splitlines()
            self.assertEqual(lines[0], "date,close")
            body = {k: v for k, v in (ln.split(",") for ln in lines[1:])}
            self.assertEqual(list(body),
                             [f"2025-{m:02d}-01" for m in range(1, 13)]
                             + [f"2026-{m:02d}-01" for m in range(1, 6)])
            # backfilled rows byte-equal to the stored daily month-ends
            self.assertEqual(body["2025-03-01"], "5247.900391")
            self.assertEqual(body["2026-02-01"], "5247.900391")
            self.assertEqual(body["2026-03-01"], "5150.0")
            # payload-present months untouched (incl. DFX-1 last-wins MTD)
            self.assertEqual(body["2025-01-01"], "100.0")
            self.assertEqual(body["2026-05-01"], "4166.3",
                             "last snapshot wins; MTD row retained once")

    def test_both_legs_gap_aborts_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._daily_csv(tmp, "gold_daily_gcf.csv",
                            [("2025-03-31", "102.5"), ("2026-04-30", "5200.0")])
            target = os.path.join(tmp, "gold_monthly_gcf.csv")
            # 2026-02 is in neither the payload nor the daily leg
            payload = make_payload([
                (ts(2026, 1), 5100.0), (ts(2026, 3), 5160.0),
                (ts(2026, 4), 5180.0)])
            with self.assertRaises(fetch.MonthlyCoverageAbort) as cm:
                self._yahoo(payload, "gold_monthly_gcf.csv", tmp,
                            daily_fname="gold_daily_gcf.csv")
            self.assertEqual(cm.exception.missing, ["2026-02"])
            self.assertFalse(os.path.exists(target),
                             "abort must happen BEFORE the file is written")

    def test_holey_payload_without_daily_leg_file_aborts(self):
        # No daily leg on disk: a payload hole is a both-legs-gap abort.
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "gold_monthly_gcf.csv")
            payload = make_payload([(ts(2025, 1), 100.0), (ts(2025, 3), 102.0)])
            with self.assertRaises(fetch.MonthlyCoverageAbort):
                self._yahoo(payload, "gold_monthly_gcf.csv", tmp,
                            daily_fname="gold_daily_gcf.csv")
            self.assertFalse(os.path.exists(target))

    def test_no_daily_leg_holed_payload_aborts_via_dfx3_guard(self):
        # daily_fname=None (symbols without a daily leg, e.g. ^SPX/SPY):
        # DFX-2 backfill/abort does not apply, but the DFX-3 per-file
        # coverage guard now catches this holed payload here — its 2025-02
        # hole leaves coverage 2/3 = 67% (< 80% of its own span) — so the
        # fetch aborts BEFORE the file is written and nothing lands in
        # data/. This supersedes the old DFX-2 "write payload as served"
        # behavior that this test previously asserted; the DFX-3 cap owns
        # the guard now (kept as the single-cap no-daily-leg regression).
        with tempfile.TemporaryDirectory() as tmp:
            payload = make_payload([(ts(2025, 1), 100.0), (ts(2025, 3), 102.0)])
            with self.assertRaises(fetch.MonthlyCoverageGuardAbort) as cm:
                self._yahoo(payload, "spx_price_monthly.csv", tmp)
            self.assertIn("coverage", cm.exception.reason)
            self.assertFalse(os.path.exists(
                os.path.join(tmp, "spx_price_monthly.csv")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
