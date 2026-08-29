# `stRatio` follow-ups: the three small ones

**Date:** 2026-08-11
**Source:** the `hitapps_analytics` marketing pilot (branch `aggrid-36`).
**Status:** requests — none designed or scheduled.
**Sibling:** `2026-08-11-ratio-of-ratios-request.md` (P1, the large one).

The pilot migrated 217 ratio columns to `stRatio` and verified them in the
browser: no rendering, value or sorting differences against the deployed
dashboard, and saved views restore intact. These three items came out of that
work. None of them blocked it.

## P2 — decide the aggregation-picker side effect

Already recorded as "Known issue, undecided" in
`2026-08-10-declarative-ratio-aggregation-design.md`, repeated here because a
consumer has now hit the surrounding surface.

`stRatio` is registered from `parseGridOptions`, which every grid passes
through, so AG-Grid offers it in the columns tool panel's aggregation picker on
**every** Enterprise grid with a `sideBar` and a value column. Choosing it on a
column that carries no `context["stRatio"]` blanks that column's group values.

The pilot's own grid is immune — marketing sets `allowedAggFuncs=[agg]` on every
metric column — but that is the consumer compensating for a library default, and
the other ten grids in that service do not all constrain their columns.

Of the three remedies the design doc lists, **falling back to `sum` (or the
AG-Grid default) when no config is present** is the one that needs no consumer
change and turns a blanked column into a degraded-but-sane one. The
register-only-when-declared option was considered and rejected in the same doc
because a column can acquire `aggFunc: "stRatio"` at runtime via
`columns_state`.

## P3 — document export and clipboard semantics of an aggregated cell

The value an `stRatio` group cell holds is an `IAggFuncResult` object, not a
number. What lands in a CSV export or on the clipboard depends on
`useValueFormatterForExport`, and the fork does not say what to expect either
way.

This matters concretely: the pilot's grid sets
`useValueFormatterForExport=False` deliberately, so that exports carry
compute-ready raw values rather than display strings, and it participates in a
Google-Sheets round-trip built on `getDataAsCsv`. The retired JS aggregator
returned an object carrying `toString`; `stRatio` returns one carrying
`toNumber`. A consumer has no documented basis for predicting the export from
that change.

Ask: state the behaviour for both `useValueFormatterForExport` settings, and
cover it with a test so it stays true.

## P4 — re-export the ratio helpers from the package root

`validate_ratio_columns`, `AGG_FUNC_NAME` and `CONTEXT_KEY` live in
`st_aggrid/ratio.py` and are absent from `st_aggrid/__init__.py`. A consumer
that wants to validate its own grid options, or to avoid hard-coding the string
`"stRatio"`, has to import from what reads like a private module path — the
pilot's resolvability test does exactly that.

Caveat worth knowing before deciding this is sufficient: it does **not** help
every consumer. In `hitapps_analytics`, the module that builds the declaration
(`src/bi_core/charts/metric_spec.py`) sits on a data-source discovery walk that
must stay import-time `streamlit`-free, and `st_aggrid` pulls `streamlit`. That
module must hard-code the literal regardless of what the package exports. The
re-export helps test code and the grid-builder modules, which import
`st_aggrid` anyway.
