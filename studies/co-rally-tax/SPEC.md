---
study: co-rally-tax
wiki: https://github.com/receiptsandregimes/research-wiki/blob/main/studies/co-rally-tax.md
baseline_commit: 8e20ffce5157f94d7885707f822d9864e174ba61   # set by the FIRST implementation run (HEAD before any code; build session 2026-10-15); never overwritten
companions:
  - https://github.com/receiptsandregimes/research-wiki/blob/main/studies/co-rally-tax.md   # protocol authority; read alongside SPEC.md
---

> **Canonical code contract.** Derived from DECISIONS.md + wiki protocol — never
> hand-edited; re-derive via the spec skill. Implementation reads this file and
> the wiki protocol; nothing else is a source of truth for what to build.

# Data-fix code spec: co-rally-tax DFX-1..5 (fetch-path remediation)

## Why

The 2026-10-15 data-validation gate FAILED (`README.md` §"Data validation
2026-10-15"; battery `code/verify_data.py` exit 1, receipts-lab commit af0d4bd):
4 open (F) defect classes F1–F4, all in the shared fetch script
`code/fetch_gold_spx_bills.py` (pre-fix sha256
`854664c08e4ec0138b8db924e85bfe707e11572e726a2c6de57eb811e41b06c0`). Two blocks
the study path directly: `gold_monthly_gcf` is missing the composite seam
months (2026-02, 2026-03) exactly where the frozen-fix→GLD-TR splice needs it,
and `spx_price_monthly` is unusable as stored (quarter-end bars under a monthly
name, values = window-START closes). This is the spec skill's §8 pressure-valve
exception: remediation is coding work, so it runs under a spec. Success
unblocks the gate: `verify_data.py` green ⇒ the STUDY SPEC may be rendered
(the study protocol itself is unchanged; the wiki study page is untouched).

## Capabilities

- **DFX-1**
  - **intent:** the system can write monthly Yahoo files with exactly one row
    per month, even when Yahoo returns the running month twice with different
    intraday snapshots (reproduced live: GC=F 4107.9 vs 4166.3)
  - **success:** re-fetched `gld_tr_monthly.csv`, `gold_monthly_gcf.csv`,
    `spy_tr_monthly.csv` each contain exactly one row per month — battery
    per-file dup scan `struct:*` PASS on all three (currently DEFECT)
- **DFX-2**
  - **intent:** the system can emit a monthly file with no missing months by
    backfilling payload gaps from the same symbol's complete daily leg, and can
    refuse loudly when even the daily leg lacks a month
  - **success:** re-fetched `gold_monthly_gcf.csv` covers every month of its
    own span (314/314, incl. 2026-02 and 2026-03) — the existing battery
    per-file coverage check `struct:*` PASSES (no new check needed);
    battery `claim:C12b gcf monthly==daily ME` stays PASS at 0.00000000%; a
    synthetic unit test (month missing from both legs) raises and exits
    non-zero
- **DFX-3**
  - **intent:** the system can detect, per file, that a "monthly" file does not
    cover its own monthly period range, and abort the fetch instead of writing
    it (quarter-end bars stored under a monthly name is the recorded instance:
    169 rows over a 503-month span)
  - **success:** synthetic quarterly payload for a monthly-named file trips the
    guard and exits non-zero (unit test); complete ETF/futures monthly files
    pass the same guard (unit test); guard runs inside the fetch script after
    every monthly-file write; thresholds per DECISIONS DFX-3 — any gap >2
    consecutive months OR coverage <80% of the file's own span
- **DFX-4**
  - **intent:** the system can produce `spx_price_monthly.csv` as true
    month-END closes, immune to Yahoo's silent quarterly downgrade and its
    +2-month window-START mislabeling (bars = close of the 3-month window
    STARTING at the label; 167/168 verified vs dailies)
  - **success:** re-fetched `spx_price_monthly.csv` covers every month of its
    span; battery `claim:C6 spx monthly density` PASS; new battery check: SPX
    monthly values == month-end resample of the daily leg, 0 tolerance
- **DFX-5**
  - **intent:** the system can prove the remediation landed — re-fetch all
    study data with the fixed script, re-run the validation battery to green,
    and re-record the validation section with re-derived numbers
  - **success:** `code/verify_data.py` (offline) exits 0 on re-fetched `data/`
    with all pre-existing passing checks intact; README §"Data validation"
    updated to the PASS record; fetch-header corrections applied (TB3MS span
    "1950 →"→"1934-01", basis count 260→304); README Engine line corrected to
    Python 3.11.16 (pandas 3.0.6 / xlrd 2.0.2 / openpyxl 3.1.5 unchanged)

## Constraints

- Data path ONLY: fetch-script fixes, guards, re-fetch, re-validation. No
  analysis caps, no signal logic, no composite construction, no verdict
  plumbing — those await the STUDY SPEC, which stays prohibited until this
  spec's final cap passes.
- Battery monotonicity: DFX may ADD checks to `verify_data.py`, never delete
  or weaken the 15 currently-passing checks; (A) hazard notes stay
  report-only.
- The running month's row is an MTD snapshot: after DFX-1 it is written once
  (last snapshot wins) and stays in the file; analysis-time drop remains the
  consumer's rule. DFX does not drop it at fetch time.
- Shared-script family rule: the 3 sibling studies share this fetch script
  (identical pre-fix sha `854664c0…`, `data/` empty) and must NOT fetch until
  DFX lands; their data arrives under their own seed+validation runs pinning
  the post-DFX sha. Fetch-script edits COMPLETE at DFX-5 — the post-DFX sha is
  the family's new shared pin.
- Guard/backfill unit tests are deterministic and network-free: synthetic
  payloads only, stdlib `unittest`, run with `~/receipts-lab/.venv/bin/python`
  (3.11.16). The battery's `--live` section stays optional, offline default.
- A month missing from BOTH the monthly payload and the daily leg aborts the
  fetch loudly — never a hole, never an interpolated guess (synthetic unit
  test).
- Pinned mechanism (DECISIONS DFX-4): SPX monthly bars come from a chunked
  DAILY ^SPX fetch + month-end resample — the daily leg verified complete
  2026-10-15 (10,780 rows, no downgrades); the Yahoo `range=max` quarterly
  payload must never be written to the monthly file.
- A quarterly-downgraded payload arriving for a monthly-named file trips the
  DFX-3 abort (synthetic fixture demonstration; production path removes the
  downgrade source via DFX-4).
- FRED `.` placeholders in `tb3ms_monthly` stay as served (upstream property,
  coerced at read; `claim:C8` passes) — no DFX change.

## Non-goals

- No sibling re-fetch under this spec; no Shiller final-row (2023-09) handling
  change (data stays as served; exclusion is analysis-time, hazard recorded);
  no changes to the 8 passing files (lbma frozen fix, fred mirror, eco3min,
  xlsx, shiller, tb3ms, GLD/GC=F daily legs); no paid data sources; no gold
  composite construction; no study signal or verdict code.

## Success signal

- `code/verify_data.py` exits 0 (offline) on the re-fetched `data/` — the
  gate's green state that unblocks the STUDY SPEC — plus the README PASS
  record and the post-DFX fetch-script sha256 pinned as the family's shared
  reference (decision line in DECISIONS.md, referenced by sibling seeds).

## I/O & Edge-Case Matrix

<frozen-after-approval>

| boundary | expected behavior | covered-by |
|---|---|---|
| Yahoo monthly payload returns the running month twice (intraday snapshots differ) | exactly one row per month; LAST occurrence wins | DFX-1 unit test (synthetic dup payload); battery `struct:*` dup scan |
| Monthly payload lacks a valid close for a month (GC=F holidays/suspensions) | month-end backfilled from the complete daily leg, byte-equal to the daily month-end | DFX-2 unit test; battery `claim:C12b` + new no-missing-months check |
| Month missing from BOTH monthly payload and daily leg | fetch aborts loudly, non-zero exit, no partial/holed file written | DFX-2 unit test (synthetic both-legs-gap) |
| Quarterly-downgraded payload (≤1 row per 3 months) arrives for a monthly-named file | guard aborts non-zero before write; nothing partial lands in `data/` | DFX-3 fixture test; battery `claim:C6` on production data |
| ^SPX monthly bars built from chunked dailies | value = month-END close; label month == bar month exactly | new battery check spx==daily-resample; `live:spx decode label+2` (downgrade + shift must be gone) |
| File's own period range vs row count after fix | guard trips on threshold breach (gap >2 consecutive months or coverage <80% of own span); post-fix files pass with every month of [first_date, PARTIAL] present | DFX-3 fixture test; battery `struct:*` per-file coverage |
| FRED CSV contains `.` placeholder rows | kept as served; coerced at read; never silently rewritten | battery `claim:C8 tb3ms span` (existing, stays green) |
| Running month's partial (MTD) row | written exactly once post-dedupe; remains flagged MTD for analysis-time drop | DFX-1 unit test; (A) hazard note stays report-only |
| Sibling dirs (`data/` empty, shared script) | no fetch anywhere until DFX-5 lands; post-DFX sha pinned for all 4 | family constraint; sibling seeds cite the DECISIONS pin |

</frozen-after-approval>

## Assumptions

- Yahoo ETF/futures monthly payloads remain complete going forward (GLD/SPY
  monthlies had no missing months; DFX-3 catches regressions rather than
  repairing them).
- The 46 missing GC=F months reconstruct exactly from the daily leg (evidence:
  0.00000000% ME identity over 267 shared months); any exception trips the
  DFX-2 loud abort.
- FRED outage windows (2026-10-15: edge dark from this host ~05:17 UTC
  onward — HTTP/2 err 2, then 120s timeouts, 0 bytes) are transient; stored
  copies remain valid; battery `--live` re-attempts.

## Build order

1. **DFX-1** — depends on: none — done-checkpoint: unit test (dup synthetic
   payload → single row, last wins) passes; re-fetch of the 3 affected monthly
   files shows one row per month; battery `struct:*` dup scans PASS.
2. **DFX-2** — depends on: DFX-1 — done-checkpoint: unit tests (backfill from
   daily; both-legs-gap abort) pass; `gold_monthly_gcf.csv` complete 314/314
   after re-fetch; `claim:C12b` 0.00000000% unchanged.
3. **DFX-3** — depends on: none (lands with DFX-2 for coherence) —
   done-checkpoint: fixture tests (quarterly payload aborts; complete file
   passes) pass; guard active after every monthly-file write.
4. **DFX-4** — depends on: DFX-3 — done-checkpoint: `spx_price_monthly.csv`
   rebuilt from chunked dailies; new spx==daily-resample battery check PASS;
   `claim:C6` PASS.
5. **DFX-5** — depends on: DFX-1..4 — done-checkpoint: `verify_data.py`
   offline exit 0 on re-fetched `data/`; README PASS record written with
   re-derived numbers; fetch-header + Engine corrections applied; post-DFX
   fetch-script sha256 recorded in DECISIONS.md as the family pin.
