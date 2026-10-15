#!/usr/bin/env python3
"""test_dfx1_dedupe.py — DFX-1 unit tests: monthly-fetcher dedupe.

Deterministic, network-free (synthetic payloads only; the network layer
`get` is monkeypatched to return canned bytes). stdlib unittest; run with:

    ~/receipts-lab/.venv/bin/python code/test_dfx1_dedupe.py

Covers the SPEC matrix rows:
  - "Yahoo monthly payload returns the running month twice (intraday
    snapshots differ)" -> exactly one row per month; LAST occurrence wins.
  - "Running month's partial (MTD) row" -> written exactly once post-
    dedupe and RETAINED (analysis-time drop stays the consumer's rule).
"""
import datetime as dt
import io
import json
import unittest
from unittest import mock

import fetch_gold_spx_bills as fetch


def ts(year, month, day=15):
    """Epoch of a UTC timestamp inside the given month (payload order is
    chronological, as Yahoo serves it)."""
    return int(dt.datetime(year, month, day, tzinfo=dt.timezone.utc).timestamp())


def make_payload(months_ts_values, field="adjclose"):
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


class DedupeMonthlyTest(unittest.TestCase):
    """Pure function: exactly one row per month, last occurrence wins."""

    def test_dup_running_month_last_wins(self):
        # Reproduction of the live F1 mechanism: running month twice with
        # different intraday snapshots (GC=F 4107.9 vs 4166.3 live 2026-10-15).
        rows = [
            ("2026-08-01", 3310.1),
            ("2026-09-01", 4107.9),
            ("2026-09-01", 4166.3),  # duplicate: LAST must win
        ]
        self.assertEqual(fetch.dedupe_monthly(rows),
                         [("2026-08-01", 3310.1), ("2026-09-01", 4166.3)])

    def test_clean_payload_unchanged_in_order(self):
        rows = [("2000-09-01", 273.0), ("2000-10-01", 276.5), ("2000-11-01", 280.2)]
        self.assertEqual(fetch.dedupe_monthly(rows), rows)

    def test_mtd_running_month_row_is_kept(self):
        # The running month's partial snapshot must SURVIVE (exactly once);
        # DFX does not drop it at fetch time — consumer rule stays.
        rows = [("2025-12-01", 100.0), ("2026-10-01", 42.0), ("2026-10-01", 44.0)]
        out = fetch.dedupe_monthly(rows)
        self.assertEqual(out, [("2025-12-01", 100.0), ("2026-10-01", 44.0)])

    def test_empty_payload(self):
        self.assertEqual(fetch.dedupe_monthly([]), [])


class YahooMonthlyWiringTest(unittest.TestCase):
    """End-to-end through yahoo_monthly() on synthetic payloads: the
    production fetch path returns exactly one row per month, last wins,
    and the MTD row stays in the returned list."""

    def _yahoo(self, payload, field="adjclose"):
        with mock.patch.object(fetch, "get", return_value=payload), \
                mock.patch("time.sleep", lambda s=None: None):
            return fetch.yahoo_monthly("SYMB", field=field)

    def test_adjclose_dup_running_month_single_row_last_wins(self):
        payload = make_payload(
            [(ts(2025, 10), 300.0), (ts(2025, 11), 305.0), (ts(2025, 12), 310.0),
             (ts(2026, 1, 3), 4107.9), (ts(2026, 1, 20), 4166.3)],  # dup month
            field="adjclose")
        out = self._yahoo(payload, "adjclose")
        self.assertEqual(len(out), 4, "one row per month expected")
        self.assertEqual([k for k, _ in out],
                         ["2025-10-01", "2025-11-01", "2025-12-01", "2026-01-01"])
        self.assertEqual(dict(out)["2026-01-01"], 4166.3, "last snapshot wins")

    def test_quote_close_field_same_dedupe(self):
        payload = make_payload(
            [(ts(2026, 2), 10.0), (ts(2026, 3), 10.5), (ts(2026, 3), 10.9)],
            field="close")
        out = self._yahoo(payload, "close")
        self.assertEqual(out, [("2026-02-01", 10.0), ("2026-03-01", 10.9)])

    def test_none_and_junk_values_still_skipped_and_mtd_kept(self):
        payload = make_payload(
            [(ts(2026, 4), None), (ts(2026, 5), 12.0),
             (ts(2026, 6), None), (ts(2026, 7), 13.0)],
            field="adjclose")
        out = self._yahoo(payload, "adjclose")
        self.assertEqual(out, [("2026-05-01", 12.0), ("2026-07-01", 13.0)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
