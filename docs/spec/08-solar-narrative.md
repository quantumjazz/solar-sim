# 08 — Solar-v1 Narrative Guide

> **Scope.** The story arc for the `solar-v1` scenario pack: the company,
> the product family, the markets, the period-by-period theme. Anyone
> writing narrative for `narrative/period-*.md` should read this first.

---

## 1. The company

Each cohort renames the company at the start of the game (it's part of the
team-formation exercise — Task 1 in the pedagogy layer). The narrative
template uses the placeholder `<COMPANY>`. Engine reports also
auto-substitute the cohort's chosen name.

The default placeholder name in templates is "Helios PV". Anything starting
with a real-sounding solar manufacturer's name — Trina, JinkoSolar, First
Solar, Hanwha Q CELLS, SunPower, REC, Meyer Burger, etc. — is **forbidden**.
Use clearly fictional names.

### 1.1 Company size and positioning at period 0

The company is **mid-sized**: roughly 1 200 employees, ~130 mEUR revenue,
manufacturing residential PV modules domestically. It is competitive but
not dominant in market 1. It has *no* export presence at game start. Its
sustainability and value-analysis credentials are at industry average. Its
production lines are aging.

This positioning is intentional: it leaves room for the team to grow
(open the export market, launch a new generation, develop a budget line,
modernise lines) and to fail (let the lines age out without reinvestment).

### 1.2 The previous board's exit

A short news clipping — adaptable to each cohort, two paragraphs maximum —
sets up the dismissal of the prior board for "insufficient long-term
strategy", and welcomes the new board. It avoids any specific allegations
that would be defamatory in a real company (no embezzlement, no
mismanagement details).

---

## 2. The product family

| Product           | Generation | Plays                                                          |
|-------------------|------------|----------------------------------------------------------------|
| `panel_gen1`      | I          | Available from period 0 — the inherited workhorse              |
| `panel_gen2`      | II         | Pre-launch development possible from period 2; launch from period 4 |
| `storage_box`     | new line   | Pre-launch development from period 3; launch from period 5     |
| `balcony_solar`   | mid-market | Available from period 5 — entry-level, lower price point        |

### 2.1 `panel_gen1` — Residential PV Panel (Gen 1)

A polycrystalline 320 W residential module. Average efficiency, mature
manufacturing process. The thing the company sells today.

In the narrative voice: "the workhorse that built the company".

### 2.2 `panel_gen2` — High-Efficiency Mono-PERC Panel (Gen 2)

A successor product. Higher-efficiency mono-PERC technology, slightly lower
manufacturing cost than gen1, better sales per unit.

Available for R&D development from period 2 (`available_from_period: 2`),
launchable from period 4 (`launchable_from_period: 4`). Pre-launch indices
at unlock: efficiency 85, sustainability 45, value-analysis 90 — well below
gen1's, so the team must invest R&D over periods 2–3 to make it competitive.

**Generation handover — coexistence.** `panel_gen2` `replaces` `panel_gen1`,
but the two coexist as separate products with separate market potentials.
The scenario's period events ramp the gen1 market *down* and the gen2
market *up* across periods 4–9. There is no forced scrapping of gen1
inventory: a team sells down its remaining gen1 stock into the shrinking
gen1 market while it ramps gen2, and chooses when to stop producing gen1.

A team that launches gen2 with weak indices is not hit with an explicit
penalty — the attraction model simply gives a low-index product a low
product score and therefore a low share. Developing gen2 enough *before*
launching is rewarded by the model itself.

The narrative emphasises: this is a *generational handover*. The pressure
to switch comes from the market — the gen1 segment is fading.

### 2.3 `storage_box` — Residential Battery Storage System

A different product category. Larger BOM cost (different supply tier),
production capacity 2.0 per line unit (so a battery occupies twice the
line time of a panel), production capacity per person = 18 units/period
(more complex assembly).

Market dynamics: smaller market than panels, growing fast, less price-
sensitive (β_price = 1.8 in markets that sell storage), efficiency-and-
brand-driven.

Launch threshold: efficiency ≥ 100, sustainability ≥ 100. Lower thresholds
than gen2 because batteries are a new category, not a generational
replacement.

### 2.4 `balcony_solar` — Plug-in Balcony Solar Kit

A mid-market product. Smaller modules + microinverter, sold direct to
consumers, no installer required. 800 W kit, much lower price point
(~€500/unit), lower per-unit margin, much higher unit volume.

The launch event in period 5 also unlocks an *external production* option:
the company can source up to a quota from a contract manufacturer at a
premium per unit but with no internal capacity commitment.

---

## 3. The markets

### 3.1 `market_1` — Domestic (EUR)

Open from period 0. ~430 000 units/period total market potential for gen1
at scenario start; grows mid-single-digits per period during expansion
periods, contracts mid-single-digits during recession periods.

Channels available: retail, bulk-buyer offers, public tenders.

### 3.2 `market_2` — Export (USD)

Opens in **period 3** with a narrative note about a trade-association
announcement and the FX rate (1 EUR = 1.10 USD at start).

Initially much smaller than market 1 (~10 % of market 1 by unit volume at
opening), but grows fast — by period 7 it can be 60-80 % the size of
market 1.

Channels: retail only (no public tenders in market 2 in solar-v1).
Transport costs are roughly 3× market 1. Currency moves over the periods
add to the strategic complexity.

---

## 4. The period arc

Each period has a teaching theme. The narrative file should make this
explicit without lecturing.

| Period | Phase   | Theme                                                                    |
|--------|---------|--------------------------------------------------------------------------|
| 1      | Trial   | Business as usual — learn the controls                                   |
| 2      | Trial   | Cost-side discipline (suppliers raise prices, a tender appears)          |
| 3      | Trial   | Markets and successors (market 2 opens; gen2 development possible)       |
| 4      | Real    | Recession looms in market 1; gen2 launchable                             |
| 5      | Real    | Environmental rules tighten; balcony solar segment opens                 |
| 6      | Real    | Tax hike & a one-off remediation cost — the cash-flow crunch period      |
| 7      | Real    | Recovery in both markets; trade duties cut                                |
| 8      | Real    | Mixed signals; storage market accelerates                                |
| 9      | Real    | Final settlement — equity at end of 9 is the scored value                |

Trial periods feed straight into Task 3 (Lessons Learned) of the pedagogy
layer. Real-period themes feed Tasks 5a, 5b, and 6.

### 4.1 What every period file must include

- A one-line news headline at the top
- 1–2 paragraphs on the general economy
- 2–4 paragraphs of industry news (demand shifts, supplier news, regulatory
  changes, technology breakthroughs, tender or bulk-buyer offers)
- A `# What changes from period N-1 to period N` table summarising parameter
  deltas
- For periods that unlock a product, a callout box describing the new
  product and the launch requirements

### 4.2 What every period file must NOT include

- Verbatim copy from any commercial simulation manual
- Specific real-company names (manufacturers, financiers, etc.) — use
  generic descriptions like "a domestic trade association" or "a regional
  utility"
- Real-currency-pair FX quotes that could be construed as financial advice
- Inflammatory political content; the scenario should be playable by any
  classroom regardless of jurisdiction or political alignment

---

## 5. Voice and tone

Like a serious trade publication, not a marketing brochure. Think *PV
Magazine* or *Solar Power World* in style: factual, dry, future-facing.

- **Active voice.** "The Central Bank cuts the prime rate by 0.5 points."
- **Avoid hype.** "A potential breakthrough" not "a game-changing technology".
- **Use units.** "10 % growth" not "double-digit growth".
- **Numbers are estimates.** Use "approximately" or a range when appropriate
  — buyers and analysts are not certain about the future.
- **Avoid imperatives at the team.** Don't write "you should invest in
  Gen 2 now". Let teams decide. The narrative is information, not advice.

### 5.1 Sample sentence pair

Bad: "Investing in environmental technology is the smart move — your
competitors are already doing it!"

Good: "Three of the four largest domestic producers announced
end-of-pipe investments totalling €18 m in environmental abatement this
quarter, following the regulatory consultation paper published in March."

---

## 6. Public-domain sources for narrative facts

When writing period narrative, draw the macro and industry beats from
public reports — and **paraphrase, never quote**:

- IEA *PV Power Systems* (annual trends report)
- BloombergNEF *Solar Spot Price Survey* (for module spot prices over time)
- JRC *PV Status Report* (for technology and capacity trends)
- IRENA *Renewable Power Generation Costs* (for LCOE and capex trends)
- European Central Bank *Economic Bulletin* (macro)
- OECD *Economic Outlook* (macro)

These all carry historic data over decades; cherry-picking a "period" from
real history (e.g., 2010 for trial 1, 2011 for trial 2, etc.) is a fine
way to ground the scenario in plausible facts without claiming it
represents any actual present-day market.

---

## 7. Translation / localisation notes

If translating the narrative to German, Spanish, etc.:

- Currency stays as scenario-set (EUR for market 1, USD or similar for market 2).
- Wages and prices stay in the base currency; the player's UI handles display.
- Use German-style number formatting in German narrative (comma decimals,
  point thousand-separators); the engine doesn't care, but the narrative
  must be culturally consistent.
- Translate idioms, don't transliterate them.
