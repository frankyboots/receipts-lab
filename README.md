# receipts-lab

Executable research code for the [research-wiki](https://github.com/receiptsandregimes/research-wiki)
— the public record behind [Receipts & Regimes](https://youtube.com/@receiptsandregimes).

The wiki holds the record (claims, questions, protocols, verdicts). This repo
holds the code that produces the numbers. Neither is complete without the
other: **every number in the wiki traces to a study here, pinned by commit
hash.**

## Layout

```
studies/<wiki-study-slug>/   # one directory per wiki study page
    README.md                # protocol summary + link back to the wiki page
    code/                    # the code path that produced the verdict numbers
```

Study directory names MUST equal the wiki slug (`studies/<slug>` in the wiki →
`studies/<slug>/` here) so a viewer can go video → wiki page → code in two
clicks.

## Rules of the lab (inherited from the wiki's money rule)

1. **No number without a reproducible path.** Every published figure comes
   from committed code with stated universe, period, costs, slippage, and
   engine. README template carries the disclosure block — fill it or don't
   publish the number.
2. **Data stays out of git.** `data/` is gitignored; fetch scripts ARE
   committed, with the data source and download date stated, so anyone can
   rebuild the universe.
3. **No signal-peeking.** Positions form on prior month-end data, executed
   the following period. State it explicitly per study.
4. **Pinned verdicts.** When a study verdict lands, the wiki study page is
   updated with the result, the verdict stamp (SUPPORTED / REFUTED / MIXED),
   and this repo's **commit hash** that produced it. Verdicts never get
   quietly amended — revisions are new dated entries.
5. **Failures air in prime time.** REFUTED studies get the same README
   treatment as SUPPORTED ones.

## Branches & hash stability

Study work happens on `study/<wiki-slug>` branches — seeded there, built
there, reviewed there. `main` is the published record: append-only, updated
only by `git merge --ff-only study/<slug>` once a study passes review (plus
rare meta-doc commits like this one). Never rebase, amend, or force-push
`main`; a post-merge mistake is corrected by a forward `git revert`, never
by rewriting history, because verdict pins in the wiki reference these
hashes forever. GitHub branch protection backs this: force-pushes and
deletions of `main` are denied.

## Not investment advice

Educational research code. Backtests are hypothetical. Nothing here is a
recommendation to buy or sell anything.

MIT — see LICENSE.
