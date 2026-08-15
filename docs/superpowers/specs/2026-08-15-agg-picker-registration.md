# Request: conditional aggregator registration (or picker exclusion)

**Date:** 2026-08-15
**Filed from:** `hitapps_analytics` (`web_app`), consumer of `st-aggrid` 2.3.0
**Predecessors:** `2026-08-11-stratio-followups-small.md` (P2), now partly closed
**Priority:** low — needs no consumer change to ship, blocks nothing

## What happens today

`parseGridOptions` registers `stRatio`, `stRatioOfRatios` and `stWeightedAvg`
on every grid, whether or not any column declares one. All three therefore
appear in the columns tool panel's aggregation picker on any Enterprise grid
with a `sideBar`.

P2 asked for this to be decided and the fork decided it — for `stRatio`, which
now degrades to a plain `Σvalues` when a column carries no `context["stRatio"]`.
That is the right answer and it closes the question for that aggregator.

It does not generalise. There is no sum analogue for a ratio of ratios or for a
weighted average, which is why 2.3.0 has those two return an empty cell instead
— documented and deliberate. So the same picker click that is now harmless on
`stRatio` blanks a column's group values under either of its two siblings, and
the fallback remedy cannot be extended to them.

## Why it matters to this consumer

`hitapps_analytics` runs 16 grid builders with a `sideBar`. Seven value columns
across `cohort`, `cohort_comparison`, `iap_dash` and `ab_tests` set an `aggFunc`
without an `allowedAggFuncs` allow-list, so a user can reach those two
aggregators on them. Before the 2.3.0 pin the picker offered zero hazardous
entries on those grids; after it, two.

`allowedAggFuncs` is a complete protection and those columns will get it as the
grids are migrated. This request is about the default, not about that migration:
a consumer should not have to enumerate an allow-list on every value column of
every grid to avoid offering an aggregator that cannot work there.

## Two candidate remedies

1. **Register only what is declared.** At `parseGridOptions`, walk `columnDefs`
   (the same depth-first walk `validate_ratio_columns` already performs,
   including `children`) and register an aggregator only if some colDef carries
   its context key or names it in `aggFunc`. Cheapest to reason about; the
   picker then shows an aggregator exactly where at least one column could use
   it. Note this changes behaviour for a grid that adds a declaration at runtime
   only — which is already the case for the null-ordering comparator, so the
   asymmetry is not new.
2. **Register all three, exclude the undeclared ones from the picker.** Keeps
   registration unconditional (so a runtime `aggFunc` assignment still resolves)
   and only filters what the tool panel offers. More surface, but no behaviour
   change for anything already working.

No preference from this side — either removes the hazard. Recommending (1) only
because it is a smaller change and matches what the picker is for.

## Done when

On a grid whose `columnDefs` declare none of the three, the aggregation picker
offers none of the three; a grid that declares one still offers it and still
aggregates correctly; and the `sum`-fallback behaviour documented for `stRatio`
is unchanged for columns that do declare it.
