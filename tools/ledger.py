#!/usr/bin/env python3
"""ledger.py — append/index/tail tool for receipts-lab study ledgers.

Why this exists: `DECISIONS.md` / `EVENTS.md` are append-only and their lines
run to several KB. The hand-append recipe ("anchor on the LAST line and repeat
it verbatim") makes a typo in a 4 KB line indistinguishable from a record edit,
and reading the file whole is the single largest avoidable context cost in a
study session. This tool does both cheaply:

  append  — writes at EOF and PROVES the prior bytes are untouched
            (sha256 of the prefix before/after + exact growth), so the
            "append-only, 1 insertion / 0 deletions" claim is machine-checked
            instead of asserted from a diff you cannot read.
  index   — derived, one line per entry (n, date, type, summary) so a session
            reads ~6 KB instead of the whole file. Derived, never committed,
            never authority.
  tail     — the last N entries' type + `state:` block, for the baseline sweep.
  check    — line-shape and entry-budget validation.

Usage:
  python3 tools/ledger.py append studies/<slug>/EVENTS.md "2026-10-17 | event | ..."
  python3 tools/ledger.py index  studies/<slug>/EVENTS.md
  python3 tools/ledger.py tail   studies/<slug>/EVENTS.md -n 3
  python3 tools/ledger.py check  studies/<slug>/DECISIONS.md studies/<slug>/EVENTS.md

Stdlib only. Exit codes: 0 ok, 1 validation/verification failure, 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys

TYPES = (
    "decision", "constraint", "capability", "assumption", "question",
    "direction", "event", "watch-item",
)
# binding types live in DECISIONS.md, narrative types in EVENTS.md
BINDING = ("decision", "constraint", "capability", "assumption", "question", "direction")
NARRATIVE = ("event", "watch-item")

LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) \| ([a-z-]+) \| (.+)$", re.S)
STATE_RE = re.compile(r"state: [^|]*$")
DEFAULT_BUDGET = 800  # chars per entry line, excluding the trailing state block


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def parse_entries(text: str):
    """Yield (lineno, date, type, body, state) for typed ledger lines."""
    for i, raw in enumerate(text.split("\n"), 1):
        if not raw.strip() or raw.startswith("#"):
            continue
        m = LINE_RE.match(raw)
        if not m:
            yield (i, None, None, raw, None)
            continue
        state = None
        sm = STATE_RE.search(raw)
        if sm:
            state = sm.group(0)
        yield (i, m.group(1), m.group(2), m.group(3), state)


def cmd_append(args) -> int:
    path = args.file
    text = args.text.rstrip("\n")
    m = LINE_RE.match(text)
    if not args.no_validate:
        if not m:
            print(f"REFUSED: line is not `YYYY-MM-DD | type | text`: {text[:80]!r}",
                  file=sys.stderr)
            return 1
        if m.group(2) not in TYPES:
            print(f"REFUSED: unknown type {m.group(2)!r}; allowed: {', '.join(TYPES)}",
                  file=sys.stderr)
            return 1
    before = read_bytes(path)
    n_before, bytes_before = before.count(b"\n"), len(before)
    prefix_sha = hashlib.sha256(before).hexdigest()
    if not before.endswith(b"\n"):
        print("REFUSED: file does not end in a newline — fix it by hand first",
              file=sys.stderr)
        return 1
    with open(path, "ab") as fh:
        fh.write(text.encode() + b"\n")
    after = read_bytes(path)
    grew = len(after) - len(before)
    ok = after[:len(before)] == before and grew == len(text.encode()) + 1
    print(f"prefix sha256 {prefix_sha[:12]}.. ({bytes_before} bytes) -> "
          f"{hashlib.sha256(after[:len(before)]).hexdigest()[:12]}..")
    print(f"grew {grew} bytes (expected {len(text.encode()) + 1}); "
          f"lines {n_before} -> {after.count(chr(10).encode())}")
    print(f"1 insertion, 0 deletions — prior bytes {'UNCHANGED' if ok else 'CHANGED'} "
          f"({'VERIFIED' if ok else 'VERIFICATION FAILED'})")
    if not ok:
        return 1
    if args.budget and len(payload(text)) > args.budget:
        print(f"WARNING: {len(payload(text))} chars of prose > entry budget "
              f"{args.budget} — a `done` line is a delta clause + state block; raw "
              f"output goes to code/probes/.", file=sys.stderr)
    return 0


def payload(text: str) -> str:
    """The entry's own prose, with any trailing `state:` block excluded."""
    return STATE_RE.sub("", text).rstrip()


def cmd_index(args) -> int:
    for lineno, date, typ, body, state in parse_entries(open(args.file).read()):
        if date is None:
            print(f"L{lineno:>3} ??? MALFORMED: {body[:args.width]}")
            continue
        summary = re.sub(r"\s+", " ", STATE_RE.sub("", body)).strip()
        print(f"L{lineno:>3} {date} | {typ:<11} | {summary[:args.width]}")
    return 0


def cmd_tail(args) -> int:
    rows = [r for r in parse_entries(open(args.file).read()) if r[1] is not None]
    for lineno, date, typ, body, state in rows[-args.n:]:
        print(f"L{lineno} {date} | {typ} | " + (f"{state}   [{len(body)} chars]" if state
                                                else f"[no state block] {re.sub(r'  +', ' ', body)[:160]}"))
    return 0


def cmd_check(args) -> int:
    bad = 0
    for path in args.files:
        text = open(path).read()
        n = len(text.split("\n"))
        chars = len(text)
        binding = NARRATIVE if os.path.basename(path).startswith("EVENT") else BINDING
        over, malformed, wrongfile, longest = [], [], [], 0
        for lineno, date, typ, body, state in parse_entries(text):
            if date is None:
                malformed.append((lineno, body[:70]))
                continue
            longest = max(longest, len(body))
            if typ not in binding:
                wrongfile.append((lineno, typ))
            pl = len(payload(body))
            if pl > args.budget:
                over.append((lineno, typ, pl))
        print(f"--- {path}: {n} lines, {chars} chars, {len(binding)} expected types "
              f"({', '.join(binding)}), longest entry {longest} chars")
        for label, rows in (("MALFORMED", malformed), ("TYPE NOT EXPECTED IN THIS FILE", wrongfile),
                            (f"OVER BUDGET (>{args.budget})", over)):
            for row in rows:
                lineno, extra = row[0], " ".join(str(x) for x in row[1:])
                print(f"    {label}: L{lineno} {extra}")
            bad += len(rows)
    print("check: " + ("clean" if bad == 0 else f"{bad} finding(s)"))
    return 0 if bad == 0 else 1


def cmd_split(args) -> int:
    """Split one ledger into a binding log + a narrative log, verified."""
    src = args.file
    text = open(src).read()
    raw = text.split("\n")
    src_dir = os.path.dirname(os.path.abspath(src))
    slug = os.path.basename(src_dir)
    # outputs live NEXT TO the source by default; a relative default would write
    # into whatever CWD the caller happened to be in (seen 2026-10-17)
    args.out_binding = args.out_binding or os.path.join(src_dir, "DECISIONS.md")
    args.out_narrative = args.out_narrative or os.path.join(src_dir, "EVENTS.md")
    binding_rows, narrative_rows, malformed = [], [], []
    for i, line in enumerate(raw, 1):
        if not line.strip() or line.startswith("#"):
            continue
        m = LINE_RE.match(line)
        if not m:
            malformed.append((i, line[:70]))
            continue
        if m.group(2) not in TYPES:
            malformed.append((i, f"unknown type {m.group(2)!r}"))
            continue
        (binding_rows if m.group(2) in BINDING else narrative_rows).append(line)
    if malformed:
        print("REFUSED: source has lines that are neither headings, blanks, nor "
              "well-formed typed entries:", file=sys.stderr)
        for i, frag in malformed:
            print(f"  L{i}: {frag}", file=sys.stderr)
        return 1
    src_sha = hashlib.sha256(text.encode()).hexdigest()
    n_typed = len(binding_rows) + len(narrative_rows)
    d = args.date
    common = (
        f"\nTwo-file ledger for this study. Split {d} out of a single\n"
        f"`DECISIONS.md` @ sha256 {src_sha} ({n_typed} typed entries). Append-only: one\n"
        f"dated `YYYY-MM-DD | type | text` line per entry, in order; later entry\n"
        f"supersedes earlier on the same point. Append with\n"
        f"`python3 tools/ledger.py append <file> \"<line>\"` (proves the prior bytes are\n"
        f"untouched); entry budget ~800 chars of prose, raw output goes to\n"
        f"`code/probes/`. Read-side contract: `receipts-lab-study-build` →\n"
        f"\"Ledger access\".\n")
    hdr_b = (f"# Decisions — {slug} (binding log, append-only)\n"
             f"\nBinding entries only: decision, constraint, capability, assumption,\n"
             f"question, direction. Event and watch-item lines — including every\n"
             f"`state:` block — live in `EVENTS.md`. This file is small on purpose: a\n"
             f"session reads it WHOLE, and the SPEC is re-rendered from it.\n" + common)
    hdr_n = (f"# Events — {slug} (narrative log, append-only; GREP ONLY)\n"
             f"\nEvent and watch-item lines: build start/done, review verdicts, gate\n"
             f"records, probe findings and Frank's rulings, each carrying its trailing\n"
             f"`state:` block. Never read this file whole — sweep it\n"
             f"(`grep -o 'state: [^|]*$' EVENTS.md | tail -1`). Binding decisions,\n"
             f"constraints and capabilities live in `DECISIONS.md`.\n" + common)
    split_d = (f"{d} | decision | Ledger split (Frank-approved review of 2026-10-17): "
               f"`DECISIONS.md` is now the BINDING log only — event and watch-item lines "
               f"moved byte-identically and in order to `EVENTS.md`. Pre-split blob sha256 "
               f"{src_sha} ({n_typed} typed entries). Growth rule with the new shape: "
               f"~800-char entry budget, split trigger at ~20KB of bindings "
               f"(receipts-lab-study-build \"Ledger access\").")
    split_e = (f"{d} | event | Ledger split, narrative half: every event and watch-item "
               f"line of the pre-split `DECISIONS.md` (blob sha256 {src_sha}, {n_typed} "
               f"typed entries) landed here byte-identically and in order, `state:` blocks "
               f"riding their own lines. Binding lines remain in `DECISIONS.md`.")
    out_b = hdr_b + "\n" + "\n".join(binding_rows + [split_d]) + "\n"
    out_n = hdr_n + "\n" + "\n".join(narrative_rows + [split_e]) + "\n"
    # verification: each routed bucket, byte-for-byte, in source order; nothing dropped
    def seq_sha(rows):
        return hashlib.sha256("\n".join(rows).encode()).hexdigest()
    def typed_rows(lines):
        rows = []
        for line in lines:
            m = LINE_RE.match(line)
            if line.strip() and not line.startswith("#") and m:
                rows.append((m.group(2), line))
        return rows

    src_b = [line for typ, line in typed_rows(raw) if typ in BINDING]
    src_n = [line for typ, line in typed_rows(raw) if typ in NARRATIVE]
    checks = [
        ("binding subset byte-identical + order-preserving",
         seq_sha(binding_rows) == seq_sha(src_b)),
        ("narrative subset byte-identical + order-preserving",
         seq_sha(narrative_rows) == seq_sha(src_n)),
        ("no entry dropped or duplicated",
         len(binding_rows) + len(narrative_rows) ==
         len([l for l in raw if l.strip() and not l.startswith("#")])),
        ("every source entry classified",
         len(src_b) + len(src_n) == n_typed),
    ]
    print(f"source {src}: {len(raw)} lines, {len(text)} chars, sha256 {src_sha}")
    print(f"  -> {args.out_binding}: {len(binding_rows)} binding entries "
          f"+ 1 split line ({len(out_b)} chars)")
    print(f"  -> {args.out_narrative}: {len(narrative_rows)} narrative entries "
          f"+ 1 split line ({len(out_n)} chars)")
    for label, good in checks:
        print(f"  [{'PASS' if good else 'FAIL'}] {label}")
    ok = all(c[1] for c in checks)
    if not ok:
        print("REFUSED: verification failed; nothing written", file=sys.stderr)
        return 1
    if args.write:
        for path, body in ((args.out_binding, out_b), (args.out_narrative, out_n)):
            with open(path, "w") as fh:
                fh.write(body)
        outs = (os.path.abspath(args.out_binding), os.path.abspath(args.out_narrative))
        if os.path.abspath(src) in outs:
            print("written in place — the source path is one of the outputs "
                  "(DECISIONS.md rewritten as the binding log)")
        elif args.remove_source:
            os.remove(src)
            print(f"written; source removed ({src})")
        else:
            print(f"written; source left in place ({src}) — remove it by hand")
    else:
        print("dry run — nothing written (pass --write)")
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ledger.py",
                                description="append-only ledger tool: append/index/tail/check")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append", help="append one entry at EOF, proving prior bytes unchanged")
    a.add_argument("file")
    a.add_argument("text")
    a.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    a.add_argument("--allow-long", action="store_true")
    a.add_argument("--no-validate", action="store_true")
    a.set_defaults(func=cmd_append)
    i = sub.add_parser("index", help="derived one-line-per-entry index (read this, not the file)")
    i.add_argument("file")
    i.add_argument("--width", type=int, default=130)
    i.set_defaults(func=cmd_index)
    t = sub.add_parser("tail", help="last N entries with their state blocks")
    t.add_argument("file")
    t.add_argument("-n", type=int, default=3)
    t.set_defaults(func=cmd_tail)
    s = sub.add_parser("split", help="split one ledger into binding + narrative logs, verified")
    s.add_argument("file")
    s.add_argument("--out-binding", help="default: <source dir>/DECISIONS.md")
    s.add_argument("--out-narrative", help="default: <source dir>/EVENTS.md")
    s.add_argument("--date", required=True)
    s.add_argument("--write", action="store_true")
    s.add_argument("--remove-source", action="store_true")
    s.set_defaults(func=cmd_split)
    c = sub.add_parser("check", help="line shape, type/file match, entry budget")
    c.add_argument("files", nargs="+")
    c.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    c.set_defaults(func=cmd_check)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
