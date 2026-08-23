Verified in code: `money_gap` (opponents.py:52-59) measures to the *last paid* seat (gap-to-6th), the Sunday route already computes `passes` and per-rival `thresholds` (app.py:408-433) that the template never renders, and sunday.html:11 has no default-selected event. The screenshot confirms the event-name suffix bug ("BMW Championship- $20M"), the green-chrome nav, the `$` mystery pill, and the four equal tiles. Findings hold. Final master spec follows.

---

# SUNDAY BROADCAST — FINAL MASTER SPEC
## Money Maker Engine v3 · single implementation pass · supersedes all prior drafts

---

## 0. DIRECTOR'S RULINGS (deltas from the winning draft — the body below already incorporates them)

**Grafts accepted:**
1. **TERMINAL gold discipline (amends the draft's own tokens).** Gold appears ONLY as: the money-line macro (rule/tab/tag), paid-position marks (gold ticks, gold-wash paid zones, payout chips), the top-6 band in the rank-trajectory pane, majors, and the wordmark underline. Consequences: `--ring` becomes ink-based; locked-pick chips become neutral; `accent-color` becomes `var(--ink)`; Pick-board row selection becomes ink-edged, not gold. Resolves the judges' "gold slightly diluted" demerit; protects the 2-second read.
2. **TERMINAL rank-trajectory pane** → Dashboard rail card 1 gains a second pane: rank-by-week inside a gold-washed top-6 band.
3. **TERMINAL whisker in the ticker** → `P(money) 89% ±1` travels everywhere.
4. **TERMINAL defense alarm calibration** → Sunday defense meters neutral; critical glyph+label only at P>40%.
5. **TERMINAL palette policy as standing rule** → critical is never a chart mark, only glyph+label; ship recorded validator numbers as a comment appendix in style.css.
6. **TERMINAL `d` density toggle** layered on Broadcast's auto-stepping (auto is default; `d` forces all-compact).
7. **TERMINAL liveness memory** → Sunday poll countdown + persistent changed-row edge tick.
8. **TERMINAL ghost-skeleton empty states captioned as promises** → every empty state names the payoff.
9. **TERMINAL 12px invisible hit rects** behind money-strip ticks.
10. **CLUBHOUSE Sunday phone-first** → one type step larger, single column <720px.
11. **CLUBHOUSE sentence-form rows for ALL within-reach threats** (not top 3).
12. **CLUBHOUSE segment trophy footers** → `Segment 2 — $2,183,470 · finished 3rd · paid $250` with gold `paid` chip.
13. **CLUBHOUSE one-time chart annotation** (`crossed the line — Travelers`) in Inter italic — ceremony without the serif.

**Grafts rejected (dilute the identity or conflict with a praised strength):**
- Fraunces/serif anything, and the sentence-phrased hero. The labeled-stat hero is Broadcast's praised 2-second hierarchy; serif is off-identity and an opsz trap.
- Gold `::selection` — violates ruling 1. Selection = `--ink` background / `--page` text (a broadcast "cut").
- TERMINAL decision-heat sort on Race threats — Race keeps **money-line impact** as primary sort (judges scored it "most product-aligned"); |P−50| is the tiebreak there. Decision heat is primary ONLY on Sunday rival cards.
- TERMINAL mono-for-all-numerals; CLUBHOUSE dropping BENCH/rank-trajectory — n/a, kept.

**Ambiguities resolved (each was a high-severity craft finding):** SVG text-stretch policy (§5.1), sweat-strip hover mechanization (§5.2), ticker no-sim fallback (§3.2), hero baseline alignment (§5.3), Sunday default-event algorithm (§6).

---

## 1. IDENTITY — FINAL TOKENS

Concept: the telecast of Jay's own money race. Three primitives everywhere — the **tower** (dense GAP/INT leaderboards), the **lower-third** (the gold Money Line macro), the **score bug** (persistent ticker). Chrome quiet and neutral; color rationed like airtime: green = dollars only, gold = the money line/paid only, status = alarms only.

```css
:root {                              /* DARK (default) */
  color-scheme: dark;
  --page: #0a0d0b;  --surface: #121613;  --raised: #171c18;  --inset: #0d100e;
  --ink: #f2f5f1;  --ink-2: #b6bfb8;  --muted: #7f8a82;
  --grid: #1e2420;  --baseline: #333c35;  --border: rgba(255,255,255,.06);
  --ring: rgba(242,245,241,.55);          /* RULING 1: focus is ink, not gold */
  --money: #199e70;  --money-ink: #4fd39e;
  --money-wash: rgba(25,158,112,.13);  --money-wash-2: rgba(25,158,112,.22);
  --gold: #eda100;  --gold-ink: #f0b73f;
  --gold-wash: rgba(237,161,0,.09);  --gold-wash-2: rgba(237,161,0,.16);
  --good: #0ca30c;  --warning: #fab219;  --serious: #ec835a;
  --critical: #d03b3b;  --critical-wash: rgba(208,59,59,.12);
  --shadow: 0 1px 0 rgba(255,255,255,.04) inset, 0 1px 2px rgba(0,0,0,.5);
}
:root[data-theme="light"] {          /* "pressroom daylight" — warm paper */
  color-scheme: light;
  --page: #f2f1ec;  --surface: #fbfaf6;  --raised: #ffffff;  --inset: #eceae3;
  --ink: #131512;  --ink-2: #494f4a;  --muted: #6f7871;
  --grid: #e2e0d8;  --baseline: #b9bcb2;  --border: rgba(19,21,18,.10);
  --ring: rgba(19,21,18,.50);
  --money: #1baf7a;  --money-ink: #0e7a53;
  --money-wash: rgba(27,175,122,.14);  --money-wash-2: rgba(27,175,122,.24);
  --gold: #b57800;  --gold-ink: #8a6200;
  --gold-wash: rgba(181,120,0,.10);  --gold-wash-2: rgba(181,120,0,.18);
  --good: #0ca30c;  --warning: #fab219;  --serious: #ec835a;
  --critical: #d03b3b;  --critical-wash: rgba(208,59,59,.10);
  --shadow: 0 1px 2px rgba(20,24,21,.08);
}
::selection { background: var(--ink); color: var(--page); }
:where(input,select,textarea,progress) { accent-color: var(--ink); }
```

**Gold whitelist (enforce by grep in review):** `--gold*` tokens may be referenced only by: `.money-line*` (macro), `.tick-paid`/`.zone-paid` (strip/chart paid marks), `.chip-payout`, `.chip-major`, `.band-top6` (rank pane), `.brand u` (wordmark underline), `.edge-line` (3px left bar on line-straddling rows), the ticker's cushion dot. Anything else referencing gold is a defect.

**Palette validation (do, and record):** run `node scripts/validate_palette.js "#199e70,#eda100" --mode dark --surface "#121613"` and `"#1baf7a,#b57800" --mode light --surface "#fbfaf6"`; paste the reported ΔE/contrast numbers as a comment block at the top of style.css, followed by the standing rules: *critical is never a chart mark (glyph+label only); critical never appears in a chart adjacent to gold; money bars are always direct-labeled in light mode.* Resolves the CVD critical/gold finding permanently.

**Texture:** radius 4px cards / 3px chips / 2px in-cell bars. 1px `--border` hairlines. Section heads get the scorecard double rule: `border-top: 1px solid var(--baseline); box-shadow: 0 2px 0 -1px var(--grid);`. **No gradients in chrome** — delete `--page-glow`, the brand gradient box, tile strips, gradient bar fills. Atmosphere: `body::before` fixed pseudo-element = solid `--page` + 8%-alpha radial corner vignette + 1.5%-opacity `feTurbulence` noise data-URI tile (fixes tall-page banding both themes). Shadows: `--shadow` only; planes separate by border+color, not blur.

---

## 2. TYPE SYSTEM — FINAL

All OFL, vendored woff2, `font-display: swap`, no CDN. New files: `barlow-condensed-600.woff2`, `barlow-condensed-700.woff2`, `plex-mono-500.woff2`, `plex-mono-600.woff2` (Inter variable already vendored).

| Voice | Face | Use |
|---|---|---|
| Chrome | Inter var | body 14/1.5, labels, meta, table text |
| Display | Barlow Condensed 600/700 | titles, hero ranks, section heads, money-line tags, chips — always caps, letter-spacing .03em |
| Money | IBM Plex Mono 500/600 | **every dollar figure and probability in the app**, ticker, axis labels |

Scale (final px): hero rank 64 Barlow 700 · hero money 44 Plex 600 · Sunday hero statement 34 Barlow 700 · screen title 26 Barlow 600 caps · why-panel head 20 Barlow 600 · tile value 24 Plex 600 · rival-card P 28 Plex 600 · compare-tray ΔP 20 Plex 600 · body 14 Inter 400 · table text 13 Inter / 13 Plex 500 numerics right-aligned · ticker 12 Plex · chart labels 10–11 Plex · tile label 12.5 Inter 500 sentence case `--ink-2` · **micro-caps 11 Inter 600 letterspaced at exactly ONE level: table headers.** (Resolves the flattened-hierarchy finding.)

**Odometer filter** `money_od`: renders `$13,694,339` as `<span class="od"><span class="od-dim">$13,</span>694,339</span>` — leading magnitude group `--muted`, significant digits `--ink`. Hero + tile figures only; tables stay flat. **`|money` filter fixed once:** negative renders `−$677,592` (U+2212 before $), used everywhere. (Resolves minus-formatting finding.)

---

## 3. SIGNATURE ELEMENTS

### 3.1 The Money Line (macro `money_line(label, delta_text, tone)`)
One Jinja macro + one CSS block; tones `table-row | chart-rule | inline`, rendered identically: full-width 2px `--gold` rule; sitting on it left, a gold-wash tab (3px radius, 20px tall) reading `MONEY LINE · TOP 6 PAID` in Barlow 600 11px caps `--gold-ink`; right, live distance in Plex 12px `--ink`: `you are +$1,056,719 above`.

Appears: standings divider after rank 6 (after rank 3 on segment boards), masthead money strip, every finish-distribution cutoff, season-race chart endpoint tag, sweat strip, and under the wordmark — brand is `MONEY MAKER '26` Barlow 700 caps with a 3px gold underline. The line *is* the logo.

**Semantics (BLOCKING).** "Above the line" = distance to the **first unpaid seat** (rank paid+1), named: `+$1,056,719 over 7th (Jason White)`. Rank gaps are separately labeled (`−$477,140 to 4th (LeMaire)`). Implementation: add `money_cushion(standings, mgr, paid)` beside `money_gap` in `/home/user/moneymaker/src/moneymaker/opponents.py` (keep `money_gap` — posture logic at opponents.py:62-76 correctly uses gap-to-last-paid); switch the web context at app.py:109 to the cushion. **Pin regression tests:** cushion = +$1,056,719 (13,694,339 − 12,637,620, White 7th); v2's $677,592 (gap to 6th, Aadal) must no longer appear as "cushion". (Resolves the highest-severity correctness finding.)

### 3.2 The score bug (global ticker)
Under the 51px sticky topbar on every screen: 28px line, `--inset` bg, hairline bottom, Plex 12 `--ink-2`, no card:
`OVR 5/86 · ●+$1,056,719 above the line · SEG 4: 2nd · BMW CHAMPIONSHIP locks THU 7:45A · P(money) 89% ±1` — gold dot before the cushion only; whisker always attached to P.
**Fallback (resolved ambiguity):** rank/cushion/seg/lock come from standings + schedule in `_base_ctx` (always available). If no cached sim, the P slot renders `P(money) —` with `title="run a projection on Race Outlook"`; the ticker never blocks or delays render.

### 3.3 Nav
Text tabs, not pills: Inter 600 13.5 `--ink-2`; active = `--ink` + 2px `--ink` underline. Rename: **Dashboard · Pick · Race Outlook · Season Map · Sunday Sweat · History**. `hx-boost="true"`, keys `1–6`.

---

## 4. SCREENS — in implementation order (build top to bottom of this section)

Grid: max-width 1440px, 20px gutters, 12-col. Sticky stack: topbar 51 + ticker 28 → table headers stick at `top:79px`.

### PHASE A — Foundation (prerequisite to everything)
Tokens/type/atmosphere (§1–2), `money_line` macro + `money_cushion` + `|money`/`money_od` filters, ticker, nav, chips/buttons/tiles (§5), event-name normalization at ingest (strip `- $20M` style suffixes app-wide — visible bug in v2), keyboard layer, reduced-motion block. Files: `web/static/style.css`, `templates/base.html`, `app.py` `_base_ctx`, `opponents.py`, ingest.

### PHASE B — DASHBOARD, "the broadcast open" (moment 4: the 2-second answer)
Top→bottom: masthead hero → money strip → tower (8 col) + rail (4 col).

**Masthead hero** (full-width `--surface` band, replaces the four tiles):
- Left: `5TH` Barlow 700 64, beneath `OF 86 · OVERALL` Barlow 600 16 caps `--muted`, ▲/▼ vs last settled week beside the rank.
- Center (dominant): label `Above the money line` Inter 12.5; `+$1,056,719` Plex 600 44 odometer-styled with a 2px gold underline (money-line semantics — whitelisted); sub-line `over 7th (Jason White) · −$477,140 to 4th (LeMaire)` Plex 12 `--ink-2`.
- Right, demoted inline: `1 event left · max add $3.6M (winner's share) · P(money) 89% ±1` Plex 12. "Purse on the table" tile is dead.
- Alignment: all three cells `line-height:1`, flex row `align-items:last baseline` (§5.3).

**Money strip** (inline SVG geometry + HTML text overlay per §5.1; 100%×64): single $-axis, domain [P10 total, leader]; every manager a 1.5×18 tick `--muted` 35%; the six paid 2×24 `--gold`; **you** 3×32 `--money` with `YOU · $13.69M` Plex 11 above; money-line boundary = vertical 2px gold rule wearing the tab. Axis-end direct labels (`$11.8M`, `$18.5M`). Every tick backed by a 12px-wide transparent hit rect; hover tooltip `Art Santana · 8th · $12,626,827 · −$390k to the line`.

**Standings tower**: columns `#` · `Δ` (▲2/▼1/—) · `MANAGER` · `TOTAL` · `GAP` (signed $ to the money line) · `INT` (to the manager directly ahead) · **LADDER** (diverging 6px in-cell bar anchored at the line value, clipped ±$2M with `→` overflow arrow; above = `--money` extending right, below = `--baseline` extending left, rounded data end) · payout chip on paid rows (`$4,000`…`$400` gold-wash — replaces the `$` mystery pill). Money-line macro as a full row after rank 6 (rank 3 + `$750/$400/$250` on segment tabs). Sticky header at 79px; **your row sticks both directions** (bottom:0 below viewport / top:107px above). Density: rows 1–20 at 34px, 21+ auto-compress to 28px/12.5; `d` toggles `body.dense` forcing all-compact. GAP labels always on you ±2 rows, others on hover; hover wash only on rows that link (rival → History profile).

**Rail:**
1. **Season position** card, two panes: (a) cumulative-$ sparkline 110px — your `--money` 2px line vs #6 cumulative 1.5px `--baseline`, `--money-wash` between while above, endpoint dot `$13.69M`; (b) **rank trajectory** 70px — overall rank by week, y inverted 1..12 clipped, gold-washed band rows 1–6, endpoint labeled `5TH`.
2. **Segment race** mini-tower: Seg 4 top 5 + you, GAP treatment, line after rank 3, payout chips.
3. **Next event**: `BMW CHAMPIONSHIP · $20M · no cut · field 50` Barlow caps; `LOCKS THU 7:45 AM · in 2d 14h` Plex; pick state: `you hold M. Thorbjornsen 🔒` neutral `--inset` chip (RULING 1 — not gold) or `NOT PICKED` `--warning` chip + icon.

### PHASE C — PICK, "the decision desk" (moment 1: Tuesday, 5 minutes)
**Event header** (`--surface`, 64px): `BMW CHAMPIONSHIP` Barlow 700 26 · `$20,000,000 · no cut · 50 players · preds Aug 22` Plex 12 · right: lock countdown + **trap ritual** — three timestamped checks (`WDs ✓ 9:12a · amateurs ✓ Mon · LIV/playoff ✓ Mon`), any unverified = `--warning` chip. Posture toggle + event select here; **HTMX swaps the board only** (`hx-get` + `hx-push-url`, server branches on `HX-Request`) so scroll/selection survive posture flips.

**Board**: `#` · `☐` compare · `GOLFER` · `WIN` · `TOP 5` · **EV** (Plex 600, the only bold column) · **EV BAR** (64px `--inset` track; $0-anchored flat `--money` 6px bar, rounded end; 1.5×10 `--ink-2` tick at FLOOR; **header prints the shared scale: `EV BAR · scale $447k`**) · `LEAGUE%` (+`LEV` badge when EV-rank ≪ usage-rank) · `SCORE` only when posture ≠ neutral, shown as `Δ vs EV` · overlap micro-chips (`LeMaire · Snyder`) on rows a money-line rival has locked, hover `gap frozen`. CUT column suppressed on no-cut events; FLAGS renders only when ≥1 flag exists (`--critical` chip + icon — now meaningful). **Selection ≠ hover** (RULING 1): selected row = `--raised` bg + 3px inset `--ink` left bar + `aria-selected`; hover = faint wash on `.clickable` only. Rows `tabindex="0"`; Enter opens why-panel; ArrowUp/Down roves with `hx-sync="replace"`.

**Inspector rail (why-panel)**: head — golfer Barlow 600 20, meta, trap flags inline, `locked by 2 rivals: LeMaire (4th), Snyder (1st)`, sequencer scarcity (`if not now: fits only TOUR Champ`). **Payout ladder**: bar = EV contribution (P × pays) on a shared $0 scale, P and Pays as Plex text (`$3.6M`, `$780k`; `Pays ≈ bucket midpoint` footnote); labels `white-space:nowrap`, bar in fixed 72px cell, td padding 5px 7px — no overflow at 360px. **Buckets that land you in board money get gold-washed rows** (paid semantics — whitelisted). Beneath: 8px 100%-stacked strip of EV share by bucket, single-hue money ramp ordered by finish, 2px gaps. `min-height:430px`; ghost-skeleton empty state captioned `pick a golfer — the payout ladder lands here`; `hx-swap="innerHTML transition:true"`. Rival reads below, ranked by threat: `chalk 78% · 3 elite left · protecting` + locked-golfer chip.

**Compare tray** (the lock instrument): checking 2–3 golfers slides up a sticky bottom tray that runs the race sim conditioned on each (cached rival plans; results cached per golfer+posture) and shows side-by-side `ΔP(in the money)` (Plex 600 20, signed, ▲`--money-ink`/▼`--serious`) and `Δ expected league $`, each with a **`LOCK THIS PICK` button** — primary `--ink` button, never green. New `POST /api/lock` endpoint writes the pick; tray confirms with the neutral locked chip and the ticker updates.

### PHASE D — SUNDAY SWEAT, the signature screen (moment 2)
**Opens dealt, never a form.** Default event (BLOCKING, replaces the browser-default-first-option bug in sunday.html:11): *the event with locked picks for Jay and zero settled earnings whose lock date ≤ today; if none, the most recent event with preds; select pre-set server-side.* Source controls (live vs CSV; file input styled, shown only when its radio is checked) collapse into a `source` disclosure. Live: `hx-trigger="every 60s"`, head shows `positions as of 2:41 PM · next poll 0:47` (countdown, 1s JS tick), changed cells pulse `.flash-up/.flash-down` (1s wash + ▲/▼ glyph, diffed via `data-prev`), and a **2px `--ink` left-edge tick persists on changed rows until the next change** — returning to the tab shows what moved.

**Phone-first (RULING 10):** this screen runs one type step larger (body 15, tables 14, hero P 48); fully single-column under 720px; dark assumed.

Layout:
1. **Score bug hero**: `RIGHT NOW YOU FINISH 5TH OVERALL · $1,000` Barlow 700 34; beside it **P(in the money tonight)** Plex 600 44 (48 on phone) **with whisker forced on** (`89% ±1`); expected final rank; expected league $. Sub-resolution ladder: `<0.1%`, structural zero `— no path`, P(1st) slot below 0.5% reads `no realistic path to 1st` in `--muted`.
2. **You hold**: golfer cards `M. THORBJORNSEN · T12 · −8 · thru 6 · projecting ≈ $310,000` (position Barlow, money Plex).
3. **Sweat strip** (THE chart; SVG per §5.1, ~1100×220): x = your golfer's finish tonight; columns = P of each finish, flat `--money`, rounded tops; **gold-washed band over the finishes that keep/put you in the money**, money-line macro at its edge; one vertical 1.5px `--ink` marker per catchable rival at their pass threshold, flag-labeled (`LIVOTE · solo 9 · 68.6%`). Marker hover mechanics per §5.2; tooltip composes the bet slip: `pass Livote if Thorbjornsen finishes 9th or better · ≈ $628,875 · 68.6% ±0.6`.
4. **ATTACK — rival cards**, sorted by decision heat (|P−50| ascending): `PASS LEMAIRE — needs solo-7th (~$655,000) · P(you pass) 34% · worth +$700 on the prize ladder`; P Plex 600 28 dominant; neutral-ink meter bar, direct-labeled; their golfer + live position. Out-of-reach rivals collapse to one footer line.
5. **DEFENSE — rivals behind** (BLOCKING: render the computed-but-unrendered data at app.py:408-433 — `passes` + `thresholds`): their golfer · live position · finish he needs · **P(they pass you)**; meters neutral gray, **critical glyph+label only above 40%** (RULING 4). Rows that would knock you below the line carry the gold 3px edge bar.
6. Compact fallback tables below a disclosure.

Pre-preds empty state: ghosted last artifact with a `STALE — last Sunday's card` stamp, captioned `deal the card — finish odds and pass thresholds land here`.

### PHASE E — RACE OUTLOOK, "the projection desk"
Opens on an answer: renders cached sim or fires a 20k run on load; knobs (trials/sensitivity/point-picks) inside an `Advanced` disclosure; one `Re-run` button; caption `n=20,000 · rival picks: fitted choice model`.

**Hero tiles** (3): P(in the money) Plex 600 32 with whisker `89% ±1` (band on by default) · `Expected league prize ≈ $1,240` · P(1st) with the §D.1 rendering ladder. Each carries Δ vs previous run (▲/▼ + value).

**Finish distribution** (shared partial, reused nowhere-else-styled; SVG ~560×200): x = board finish 1..12 + `13th+` collapsed; flat `--money` 22px columns, 2px gaps, rounded tops; gold-washed paid band + money-line macro at the cutoff, direct label `in the money 65.6%` (reconciles with tile 1); selective labels (mode + cutoff neighbors); hover `Solo 5th — 26.2% · pays ≈ $655,000`; crosshair `P(6th or better) = 65.6%`.

**The catch list**, two panes `AHEAD — can you catch them?` / `BEHIND — can they catch you?`; sorted by **money-line impact, |P−50| tiebreak** (RULING: rejected full decision-heat graft here); uncatchables (P≥99%) collapse to `out of reach: Sherman, White, CK +9 more`. Redundant P-bars die. Each row: manager · their golfer chip (link-icon + `correlated — gap frozen` when it's yours) · P Plex · GAP on one shared diverging $-axis (you = zero; neutral `--baseline` fill, never green; ±$2M clip + overflow arrows; 1.5px `--ink-2` tick at their expected post-event position, header tooltip `their likely add this week`). Line-straddling rows: gold 3px left bar. **Every within-reach row carries the sentence** (RULING 11): `You pass Livote with 9th or better — 68.6%`; the bar is decoration, the sentence is the decision.

### PHASE F — SEASON MAP (moment 3: January)
**Timeline SVG** (~full-width×180): one lane per segment; events as circles scaled by purse (8–20px); majors gold-ringed with `×2` badge; settled = `--money` fill when earned>$0, hollow `--baseline` when $0 (scars visible); locked = neutral filled with lock glyph (RULING 1 — not gold); planned (solver) = dashed `--money` ring; `YOU ARE HERE` marker, auto-`scrollIntoView`. Beneath: the **cumulative river** — banked-$ line vs #6 cumulative, 60px compressed. **Hoard strip**: top unused golfers as chips ranked by world rank.

**Table**: drop SEG column; STATUS chips exception-only (`locked` 🔒 neutral, `next up`, `planned`; settled rows get nothing — the wall of `settled` chips dies); EARNED gets a $0-anchored magnitude bar behind the figure on a season-shared scale ($0 muted); add DATE and **BEST AVAIL EV** benchmark columns (RULING/BENCH). **Segment sections close with trophy footers** (RULING 12, double-rule treatment): `Segment 2 — $2,183,470 · finished 3rd · paid $250`, gold `paid $250` chip where Jay finished top 3.

### PHASE G — HISTORY, "the season film"
1. **Season race chart** (SVG ~1200×320): x = events 1–35, y = cumulative $; your `--money` 2px line, endpoint dot + `$13,694,339`; #6 cumulative gray with gold endpoint tag; `--money-wash` between while above; 1st place as second `--baseline` line, direct-labeled (≤3 series, direct labels as legend); segment boundaries hairline verticals; majors gold axis ticks; $0 weeks hollow markers; **one annotation** (RULING 13): `crossed the line — Travelers` in Inter italic 12 `--ink-2` with a gold tick at that week. Crosshair: `event · pick · earned · cushion after`.
2. **Pick-efficiency dumbbells**: per event, best-available EV (hollow `--ink-2` dot) vs realized (`--money` dot), 1.5px connector, one $ axis; aggregate `your edge by event type`.
3. **Rival profiles**: default-collapsed to the 12 managers around your rank (`show all 86`); CHALK/CHASE/CORR/MARGIN/HOARD as **dot strips** (8px dot on hairline 0–100 track, league-median tick, value as text; hover `Chase 70% — league median 20%`); dead hoards = neutral count chips (`dead: 3 — Rahm, Cantlay, +1`); red only for alarms about *your* position; self excluded from the list.

### PHASE H — Polish
Sim theater, count-ups, staggers, view transitions (§5.4); print sheet (Pick prints board+why-panel as one card for the group chat); run + record the palette validator; the gold-grep audit; regression tests (§6).

---

## 5. COMPONENT & MECHANICS SPECS

### 5.1 SVG text policy (resolves the preserveAspectRatio finding)
Two chart classes:
- **Full-bleed strips** (money strip, cumulative river): SVG contains **geometry only**, `width:100%; height:<fixed>px`, `preserveAspectRatio="none"` — ticks/rules may stretch harmlessly. **All text (YOU label, axis ends, macro tab) is absolutely-positioned HTML** over the SVG, positioned by the same server-computed percentages.
- **Proportional charts** (distribution, sweat strip, season race, timeline): fixed viewBox, `preserveAspectRatio="xMidYMid meet"`, `max-width:100%`; SVG text scales uniformly. Container gets `min-width` (720px sweat/season, 480px distribution) + `overflow-x:auto` so small screens scroll the chart, never the page.

### 5.2 Sweat-strip marker hover (resolves the unmechanized-interaction finding)
Each finish column is `<rect class="col" data-finish="N">`; each rival marker `<g class="pass-marker" data-finish="9" data-rival="Livote" data-pays="628875" data-p="68.6" data-w="0.6">` containing the visible 1.5px line + a full-height 12px transparent hit rect. One delegated `pointerenter/pointerleave` handler on the chart (~15 lines): on enter, add `.hl` to every `.col` with `data-finish <= marker's data-finish`, dim the rest via a root class, and populate the shared tooltip from the marker's data-* attributes; on leave, clear. Same handler pattern serves money-strip tick tooltips.

### 5.3 Hero baseline alignment (resolves the condensed-vs-mono finding)
Hero cells: label above value; value elements all `line-height:1`; the flex row uses `align-items:last baseline` so Barlow 64 rank, Plex 44 money, and Plex 12 meta share one baseline. `.hero-rank{transform:translateY(.02em)}` nudge permitted after screenshot check; no other optical hacks.

### 5.4 Shared components
- **Bug tile**: `--surface`, 4px radius, hairline, no strip/gradient; label Inter 12.5 `--ink-2`; value Plex 600 24 odometer; optional Δ (▲/▼+value) and whisker (`±1` `--muted`).
- **Tables**: headers 11 Inter 600 caps `--muted` sticky at 79px with `--surface` bg; row rules 1px `--grid`; 34px/28px heights; chevron `›` in last cell of clickable rows; every table crossing a paid boundary renders the macro row.
- **Chips**: 3px radius, 11 Inter 600, exception-only. Gold-wash = payout amounts + majors ONLY. Neutral `--inset` + glyph = locked/correlated/informational counts. `--warning` = action needed. `--critical` + icon = real alarms only (amateur held, WD, dead hoard *of yours*).
- **Buttons**: primary `--ink` bg / `--page` text / Barlow 600 caps 13; secondary hairline `--ink-2` outline. No green, no gold. Focus: `--ring` outline following element shape (`:focus-visible` drops any border-radius override).
- **Movement**: ▲ `--money-ink` / ▼ `--serious`, always glyph + value, never color alone.
- **Sim theater**: `hx-disabled-elt="find button"` + `hx-sync="this:drop"`; button morphs to `DEALING 300,000 SUNDAYS` with `::after` animated dots (remove the literal `…`); results wrapper on `htmx-request`: `opacity:.45; filter:saturate(.5); aria-busy=true`; first run shows skeleton bones at 35%. On land: 450ms rAF count-up (tabular figures), threat rows stagger `calc(var(--i)*16ms)` capped at 15, columns grow via `@starting-style`. All inside a global `prefers-reduced-motion: reduce` `.01ms` override.
- **HTMX/nav**: `hx-boost`, `htmx.config.globalViewTransitions=true`, 150ms cross-fade, `transition:true` on partial swaps. Radio tab groups = visually-hidden-but-focusable inputs (`clip-path:inset(50%)`, never `hidden`), `:has(input:checked)` active style, `:has(input:focus-visible)` ring.
- **Keyboard** (~40 lines): `1–6` screens, `j/k`+Enter rows/inspect, `/` event select, `t` theme (with `aria-pressed`, glyph swap, 200ms scoped transition), `d` density, `Esc` clears panel.
- **Empty states**: every one is a ghost skeleton captioned as a promise (`deal the card — finish odds and pass thresholds land here`), never a bare form or blank card.

---

## 6. ENGINEERING CORRECTNESS — BLOCKING, WITH TESTS

| Fix | Where | Test pins |
|---|---|---|
| Cushion = first **unpaid** seat | new `money_cushion` in opponents.py; app.py:109 switches to it | `+$1,056,719` / `7th (Jason White)`; segment analog to 4th seat |
| Sunday defense rendered | app.py:408-433 `passes`+`thresholds` → template §D.5 | LeMaire threshold `solo-7` ≈ `$655,000` appears |
| Sunday default event | route resolves live event server-side (§D), never first-option browser default (sunday.html:11) | BMW selected on load given fixtures |
| Minus formatting | `|money` filter | `−$677,592` (U+2212) |
| Event names | ingest normalization | no `- $20M` suffix anywhere |
| Sub-resolution P | shared `p_label` helper | `<0.1%` / `— no path` / `no realistic path to 1st` |
| Whisker on Sunday hero + ticker | §D.1, §3.2 | `±` present in both |
| Gold whitelist | §1 grep audit | zero non-whitelisted `--gold` references |

---

## 7. CUT LIST (delete, don't restyle)
Green gradient brand box, button gradients, tile top-strips, `--page-glow`; green chrome anywhere (nav, links, active, selection, buttons, focus); the four equal tiles and the "purse on the table" stat; pill nav and 16px radii; big soft shadows; EV/SCORE duplicate column, CUT on no-cut events, empty FLAGS, SEG on Season Map, the `settled` chip wall, the `$` mystery pill; P-bars in threats; raw sim knobs as primary UI; bare `Run simulation` empty states; red dead-hoard pill walls; Jay as his own rival; `0.0%` heroes; the Sunday form-first layout and unstyled file input; micro-caps beyond table headers; whole-column bolding; hover on non-interactive rows.

---

## 8. FILES

`/home/user/moneymaker/src/moneymaker/web/static/style.css` (tokens, components, validator appendix comment) · `/home/user/moneymaker/src/moneymaker/web/templates/*.html` + `templates/partials/` (money_line macro, finish-distribution partial, sunday_card rebuild) · `/home/user/moneymaker/src/moneymaker/web/app.py` (cushion switch at :109, Sunday live-event resolution + defense context at :380-440, HX-Request branches, `/api/lock`, compare endpoint, SVG-builder helpers) · `/home/user/moneymaker/src/moneymaker/opponents.py` (`money_cushion`) · ingest (name normalization) · new static: `barlow-condensed-600/700.woff2`, `plex-mono-500/600.woff2` · tests pinning §6.

---

## 9. DEFINITION OF EXCEPTIONAL — the build ships only when all 10 pass

1. **2-second test:** cold Dashboard load answers rank (`5TH OF 86` at display scale, ▲/▼), cushion (`+$1,056,719 over 7th (Jason White)`), and `P(money) 89% ±1` above the fold, no scroll, both themes.
2. **One line, one meaning:** the money-line macro renders identically on all six surfaces, and the gold-grep audit finds zero uses outside the §1 whitelist — no gold focus, selection, or locked chips.
3. **Tuesday ≤ 3 interactions:** open Pick → check two golfers → tray shows conditioned ΔP(money) side-by-side → `LOCK THIS PICK` commits; scroll and selection survive a posture flip mid-flow.
4. **Sunday opens dealt on the right event** with the outcome sentence first, P with forced whisker, the sweat strip's gold band + rival markers with working beyond-highlight hover, and the **defense side rendered**; fully single-column and one type step larger under 720px.
5. **One money voice:** every dollar figure and probability app-wide is Plex Mono; negatives use U+2212; odometer styling on heroes/tiles only; tables right-aligned and flat.
6. **86 rows stay scannable:** self-row visible from any scroll position (both sticky directions), macro row after rank 6, auto density stepping at row 21 + `d` override, hover only where a row links, the 7th–9th $57k bunching visibly identical in the LADDER column.
7. **Chart discipline holds everywhere:** single axes, direct value labels (EV-bar scale printed in its header), no dual axes, whiskers on every headline P including the ticker, `<0.1%`/`— no path` ladder, critical never a chart mark, page never scrolls horizontally (charts scroll in their own containers).
8. **Both themes from one token set** with the validator's recorded numbers shipped in style.css; light-mode money bars all direct-labeled; the noise+vignette shows no banding on the 86-row page in either theme.
9. **Motion is theater, never jank:** dealing-Sundays state, 450ms count-ups, capped staggers, 150ms view transitions — all fully disabled under `prefers-reduced-motion`, and no layout shift from count-ups (tabular figures).
10. **The screenshot test:** any screen, cropped anywhere with the wordmark hidden, is identifiable as this product by gold line + condensed caps + mono money voice — and the Pick print sheet produces a one-card artifact worth posting to the 86-man group chat.