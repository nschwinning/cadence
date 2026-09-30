# Design spec — Session-detail KPI tiles (drawdown & trade quality)

Scope: layout/visual spec for the six new KPI tiles on `PaperTradingSessionPage.tsx`
(`KpiRow`, ~L557-644) only. Reuses `StatTile`, existing Tailwind tokens, and the
page's existing `pnlClass` / `formatCurrency` / `formatPercent` helpers. No new
deps, no new tokens. Session-detail page only (not the comparison list).

---

## 1. Grouping & IA — TWO labeled groups, not one flat 14-tile grid

**Decision: split the KPI area into two visually-labeled subsections.**

- Group A — **"Performance"**: the existing 8 tiles (Current value, Realised P&L,
  Unrealised P&L, Transaction fees, Total return, Sharpe ratio, Benchmark return,
  Excess return). Unchanged.
- Group B — **"Risk & trade quality"** (NEW): the six new tiles.

**Why not one flat grid of 14:** At 14 tiles a single grid becomes an
undifferentiated wall — the user can no longer scan to "how am I doing" (value/
return) vs. "how risky / how good are my trades" (drawdown/win rate). The two sets
answer different questions and the six new ones share a distinct semantic basis
(daily NAV series + closed positions) and distinct null-conditions. A labeled
break also gives the null placeholders context ("No closed positions yet" reads
naturally under a "Risk & trade quality" header). It costs one heading and matches
a pattern already on this page (the `Panel` sections "Runs"/"Events" each use an
`<h2 class="text-lg font-semibold text-slate-900">`).

**Heading treatment** (reuse the page's existing heading recipe, do NOT wrap in a
bordered `Panel` card — these are bare tile grids): a lightweight section label
above each grid:

```
<h3 class="text-sm font-semibold uppercase tracking-wide text-slate-500">
```

Use `text-sm` (not the `text-lg` panel title) so the group labels sit quietly
above the grids rather than competing with the `Runs`/`Events` panel titles below.
Give each group `role="group"` + `aria-labelledby` pointing at its heading id (see
§6). Vertical rhythm between the two groups: `gap-6` (the page section already uses
`flex flex-col gap-6`), or wrap both groups in one `<div class="flex flex-col
gap-6">` inside the existing section.

Structural mockup:

```
Performance                                  (h3, slate-500 uppercase)
┌───────────┬───────────┬───────────┬───────────┐
│ Current   │ Realised  │ Unrealised│ Txn fees  │   lg: 4 cols
│ value     │ P&L       │ P&L       │           │
├───────────┼───────────┼───────────┼───────────┤
│ Total     │ Sharpe    │ Benchmark │ Excess    │
│ return    │ ratio     │ return    │ return    │
└───────────┴───────────┴───────────┴───────────┘

Risk & trade quality                         (h3, slate-500 uppercase)
┌──────────────┬──────────────┬──────────────┐
│ Max drawdown │ Win rate     │ Average win  │   lg: 3 cols
├──────────────┼──────────────┼──────────────┤
│ Average loss │ Best trade   │ Worst trade  │
└──────────────┴──────────────┴──────────────┘
```

---

## 2. Ordering within Group B

Fixed order, left-to-right / top-to-bottom:

1. **Maximum drawdown** — downside-risk headline; leads the group.
2. **Win rate** — the single "are my trades working" summary.
3. **Average win**
4. **Average loss**
5. **Best trade**
6. **Worst trade**

Rationale: risk first, then the summary rate, then the two matched pairs
(average win/loss, then extreme best/worst). Averages before extremes because a
mean is the more representative figure; the extremes are the tails. On the common
2-column (sm) breakpoint this pairs win↔loss and best↔worst on the same row, which
reinforces the compare-the-pair reading.

---

## 3. Grid & responsive behavior

**Group A (existing 8):** keep exactly as today —
`grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4`.

**Group B (new 6):** `grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3`.

- `grid-cols-1` (mobile): one column, full-width tiles.
- `sm:grid-cols-2`: 3 rows of 2 — win/loss and best/worst pair per row.
- `lg:grid-cols-3`: 2 clean rows of 3, no orphan tile.

6 divides evenly by both 2 and 3, so there is never a ragged last row. Use the
same `gap-4` as Group A for a consistent gutter. (Deliberately do **not** push
Group B to 4 columns — 6 tiles at 4-wide leaves a 2-tile orphan row; 3-wide is the
clean fit and keeps each tile wide enough for a `-$1,234.56` value at the tile's
`text-3xl`.)

---

## 4. Per-tile formatting, sign & color

Color uses ONLY the page's existing `pnlClass(value)` →
`text-emerald-700` (>0) / `text-red-700` (<0) / `text-slate-700` (0), and the
StatTile default value color `text-slate-900`. Currency via `formatCurrency`
(renders `-$1,234.50` for negatives). Percent via `formatPercent` (fraction →
`12.34%`).

| # | Label | Type | Value expr (non-null) | Color | Hint |
|---|-------|------|------------------------|-------|------|
| 1 | `Maximum drawdown` | percent | `d === 0 ? '0.00%' : `−${formatPercent(d)}`` | `d > 0 → text-red-700`, else default slate-900 | `Peak-to-trough, daily NAV` |
| 2 | `Win rate` | percent | `formatPercent(w)` | default slate-900 (neutral — not a P&L) | `of closed positions` |
| 3 | `Average win` | currency | `<PnlValue value={avgWin} />` | green via pnlClass (value > 0) | `per winning position` |
| 4 | `Average loss` | currency | `<PnlValue value={avgLoss} />` | red via pnlClass (value < 0) | `per losing position` |
| 5 | `Best trade` | currency | `<PnlValue value={best} />` | sign-colored via pnlClass | `largest realised gain` |
| 6 | `Worst trade` | currency | `<PnlValue value={worst} />` | sign-colored via pnlClass | `largest realised loss` |

Key sign rules so nothing misleads:

- **Maximum drawdown** arrives as a non-negative fraction (magnitude of a
  decline). Rendering `12.34%` alone reads like a *gain*. Prefix an explicit minus
  (`−12.34%`, real minus `−` or `-`) so the sign carries "this is a decline",
  and color it `text-red-700` when non-zero. A flat `0.00%` (no decline ever)
  stays neutral slate-900 with no minus. The minus + the word "drawdown" carry the
  meaning without relying on color (§6).
- **Average loss / Worst trade** are signed raw P&L (already negative). Use
  `PnlValue` / `formatCurrency` unchanged — the leading `-$` shows the sign; do NOT
  take an absolute value.
- **Best trade / Worst trade** can both be negative in a losing session (max/min
  of realised P&L). `PnlValue` colors by actual sign, so a "Best trade" of
  `-$3.00` correctly shows red — which is honest, not a bug. Don't force green on
  Best or red on Worst.
- **Win rate** is a neutral ratio, not a gain/loss — leave it default slate-900
  (no green/red), same as how the page treats non-P&L figures.

Reuse the existing `PnlValue` component (defined at ~L547) for tiles 3-6.

---

## 5. Empty / absent (null) state

Match the existing null-Sharpe tile exactly (~L573-574, L630-634): the tile's
**value** becomes the plain string `'Not yet available'` (renders in StatTile's
default `text-slate-900` bold — a neutral, uncolored placeholder), and the **hint**
explains why. No `pnlClass`, no minus, no `$`/`%` on a null.

Per-metric hint when absent (each is independently nullable):

| Tile | Absent when | Absent hint |
|------|-------------|-------------|
| Maximum drawdown | no value snapshots | `Needs a value snapshot` |
| Win rate | no closed positions | `No closed positions yet` |
| Average win | no winning positions | `No winning positions yet` |
| Average loss | no losing positions | `No losing positions yet` |
| Best trade | no closed positions | `No closed positions yet` |
| Worst trade | no closed positions | `No closed positions yet` |

Recipe per tile (mirrors the Sharpe pattern):

```
<StatTile
  label="Win rate"
  value={data.win_rate === null ? 'Not yet available' : formatPercent(data.win_rate)}
  hint={data.win_rate === null ? 'No closed positions yet' : 'of closed positions'}
/>
```

Because the four trade metrics share the "no closed positions" root cause, in the
common empty session all four show the same neutral placeholder — that's expected
and reads consistently under the "Risk & trade quality" heading.

---

## 6. Accessibility

- **Contrast (all existing tokens, all pass WCAG AA on white `#fff`):**
  `text-emerald-700` (#047857 ≈ 4.75:1), `text-red-700` (#b91c1c ≈ 5.9:1),
  `text-slate-900` (≈ 17:1), label/placeholder `text-slate-500` (#64748b ≈ 4.6:1).
  Tile values are `text-3xl font-bold` (large text, ≥3:1 threshold) so all clear
  AA comfortably; the `text-slate-500` labels/hints clear AA for normal text too.
  No new colors introduced, so no new contrast risk.
- **No color-only signaling:** every sign is also conveyed textually — drawdown
  carries a leading `−` and the word "drawdown"; loss/worst carry `-$`; win/loss
  and best/worst are disambiguated by their labels ("Average win" vs "Average
  loss"). A user who can't distinguish red/green still reads the correct sign from
  the glyph and the label.
- **Semantic structure:** each group is a `role="group"` with
  `aria-labelledby={headingId}`; the group label is a real heading
  (`<h3 id=...>`), keeping the two groups in the document heading outline and
  navigable by assistive tech. StatTile's `<p>` label + `<p>` value pairing is
  unchanged (reused as-is).
- **Placeholder is not a dead-end:** `'Not yet available'` + an explanatory hint
  tells screen-reader and sighted users *why* the metric is blank, rather than a
  bare `—`.
- **Focus/interaction:** tiles are non-interactive (display only) — no focus
  handling needed; nothing here changes tab order.

---

## Handoff notes for the frontend-developer

- Add the six nullable fields to `PaperTradingSessionKpis` in `types/api.ts`
  (percent fields as fractions, currency fields as raw numbers) per proposal.md.
- Split the current single `<div class="grid …">` in `KpiRow` into two headed
  grids as in §1/§3; move nothing about the existing 8 tiles except wrapping them
  under the "Performance" heading (optional — you may leave Group A unlabeled if
  product prefers, but then label Group B only; the two-group split is the
  recommendation).
- Reuse `StatTile`, `PnlValue`, `pnlClass`, `formatCurrency`, `formatPercent`;
  add no new component and no new Tailwind token.
