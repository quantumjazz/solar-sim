# Sources

> Every formula, parameter family, and modelling choice in this project is derived
> from public sources. This document is the bibliography. It is **mandatory reading
> before adding to the spec**: if you cannot cite the basis for a parameter or
> formula here, do not add it.
>
> Conventions:
> - **Public-domain** sources are preferred where they exist (US government
>   publications, EU institutional reports, classical academic papers).
> - **Standard textbooks** are cited for established models. Their *ideas and
>   methods* are not copyrightable; their *specific text and exposition* is.
>   We use the ideas, not the prose.
> - **Industry data** (IEA, NREL, JRC, IRENA, BloombergNEF surveys) gives
>   real-world parameter ranges. We round and adapt for game-design; we do not
>   claim our numbers represent any specific company.

---

## §1 — Demand and market response (used in `01-sales.md`)

### Multinomial attraction model

The market-share allocation by attractiveness ratio is a standard result in
quantitative marketing. The canonical references:

- **Bell, D., Keeney, R., Little, J. D. C.** (1975). *A Market Share Theorem.*
  *Journal of Marketing Research*, 12(2): 136–141.
- **Cooper, L. G., Nakanishi, M.** (1988). *Market-Share Analysis: Evaluating
  Competitive Marketing Effectiveness.* Kluwer Academic.
- **Hanssens, D. M., Parsons, L. J., Schultz, R. L.** (2001). *Market Response
  Models: Econometric and Time Series Analysis* (2nd ed.). Kluwer Academic.

### Price-elasticity defaults

Industrial / B2B price elasticities for durable equipment typically range
0.4–1.0 at the category level (less elastic than consumer goods); brand-level
price elasticities are 2.0–4.0 (more elastic, because of cross-substitution).
References:

- **Bijmolt, T. H. A., van Heerde, H. J., Pieters, R. G. M.** (2005). *New
  Empirical Generalizations on the Determinants of Price Elasticity.*
  *Journal of Marketing Research*, 42(2): 141–156.
- **Tellis, G. J.** (1988). *The Price Elasticity of Selective Demand: A
  Meta-Analysis of Econometric Models of Sales.* *Journal of Marketing
  Research*, 25(4): 331–341.

### Advertising response

Diminishing-returns advertising-sales curves (the saturation / exponential
form) and long-term ad effects:

- **Little, J. D. C.** (1979). *Aggregate Advertising Models: The State of the
  Art.* *Operations Research*, 27(4): 629–667.
- **Dubé, J.-P., Hitsch, G. J., Manchanda, P.** (2005). *An Empirical Model
  of Advertising Dynamics.* *Quantitative Marketing and Economics*, 3:
  107–144.

---

## §2 — Sales-force effort persistence (used in `01-sales.md`)

Long-run carryover and sales-force productivity:

- **Mantrala, M. K., Sinha, P., Zoltners, A. A.** (1992). *Impact of
  Resource Allocation Rules on Marketing Investment-Level Decisions and
  Profitability.* *Journal of Marketing Research*, 29(2): 162–175.
- **Albers, S., Mantrala, M. K., Sridhar, S.** (2010). *Personal Selling
  Elasticities: A Meta-Analysis.* *Journal of Marketing Research*, 47(5):
  840–853.

---

## §3 — Cost accounting and financial statements (used in `06-accounting.md`)

### Standard managerial-accounting structure

- **Drury, C.** (2018). *Management and Cost Accounting* (10th ed.). Cengage.
- **Horngren, C. T., Datar, S. M., Rajan, M. V.** (2015). *Cost Accounting:
  A Managerial Emphasis* (15th ed.). Pearson.
- **Bhimani, A., Horngren, C. T., Datar, S. M., Rajan, M. V.** (2019).
  *Management and Cost Accounting* (7th ed.). Pearson.
- **Coenenberg, A. G., Haller, A., Schultze, W.** (2018). *Jahresabschluss
  und Jahresabschlussanalyse* (25th ed.). Schäffer-Poeschel. *(German;
  authoritative on HGB §266 balance-sheet structure.)*

### Contribution-margin tiering (stepwise/multi-level)

The multi-step contribution margin (CM I → IV) framework is the standard
*Mehrstufige Deckungsbeitragsrechnung* taught in German business schools:

- **Kilger, W., Pampel, J., Vikas, K.** (2012). *Flexible Plankostenrechnung
  und Deckungsbeitragsrechnung* (13th ed.). Gabler.

### Statement articulation (P&L → BS → CF)

- **Penman, S. H.** (2013). *Financial Statement Analysis and Security
  Valuation* (5th ed.). McGraw-Hill.
- **IFRS Foundation.** *IAS 7 — Statement of Cash Flows.* (Public regulatory
  text.)
- **HGB §266** (Handelsgesetzbuch, German Commercial Code) — public legal
  text, balance-sheet structure for medium-large companies.

### Inventory: moving average

A canonical inventory-valuation method documented in every cost-accounting
textbook cited above. We use moving average because it is what most ERP
systems use in practice and it gives stable per-unit values that students can
understand.

---

## §4 — Production: capacity, depreciation, learning curve (used in `03-production.md`)

### Learning curve / experience curve

- **Wright, T. P.** (1936). *Factors Affecting the Cost of Airplanes.*
  *Journal of the Aeronautical Sciences*, 3(4): 122–128. *(Public domain;
  the original.)*
- **Henderson, B. D.** (1968). *The Experience Curve.* Boston Consulting
  Group perspective. (Public domain via age and BCG redistribution.)
- **Argote, L., Epple, D.** (1990). *Learning Curves in Manufacturing.*
  *Science*, 247: 920–924.

Wright's law: per-unit cost (or labour requirement) declines by a fixed
percentage with every doubling of cumulative output. Industry-typical learning
rates: 75–90 % for assembly operations.

### Straight-line depreciation, residual values

A standard accounting practice; refer to Drury 2018 ch. 9, or any
intermediate accounting textbook.

---

## §5 — Workforce, motivation, productivity (used in `04-hr.md`)

### Productivity decomposition

Productivity as a product of motivation, competence, adaptation, and process
optimisation is a synthesis of several public lines of research:

- **Heskett, J. L., Sasser, W. E., Schlesinger, L. A.** (1997). *The
  Service Profit Chain: How Leading Companies Link Profit and Growth to
  Loyalty, Satisfaction, and Value.* Free Press.
- **Locke, E. A., Latham, G. P.** (2002). *Building a Practically Useful
  Theory of Goal Setting and Task Motivation: A 35-Year Odyssey.*
  *American Psychologist*, 57(9): 705–717.
- **Hackman, J. R., Oldham, G. R.** (1976). *Motivation through the
  Design of Work.* *Organizational Behavior and Human Performance*, 16:
  250–279.

### Absenteeism drivers

- **Steers, R. M., Rhodes, S. R.** (1978). *Major Influences on Employee
  Attendance: A Process Model.* *Journal of Applied Psychology*, 63(4):
  391–407.
- **Harrison, D. A., Martocchio, J. J.** (1998). *Time for Absenteeism:
  A 20-Year Review of Origins, Offshoots, and Outcomes.* *Journal of
  Management*, 24(3): 305–350.

---

## §6 — Finance, rating, share price (used in `05-finance.md`)

### Credit rating

Multi-factor scoring of company creditworthiness from financial ratios:

- **Altman, E. I.** (1968). *Financial Ratios, Discriminant Analysis and
  the Prediction of Corporate Bankruptcy.* *Journal of Finance*, 23(4):
  589–609. *(The Z-Score paper.)*
- **Moody's Investors Service.** *Rating Methodology: Industrial
  Manufacturing* (public methodology paper; multiple updates).
- **S&P Global Ratings.** *Corporate Methodology* (public methodology paper).

### Share price drivers (decomposable simple model)

We use a simple weighted-sum model rather than a discounted-cash-flow valuation
because (a) it is more controllable for teaching, and (b) it makes the
dependencies between management decisions and share price legible to students.

References for the qualitative drivers:

- **Lev, B.** (2001). *Intangibles: Management, Measurement, and Reporting.*
  Brookings Institution Press. *(On the relationship between intangibles —
  brand, R&D, customer satisfaction — and firm value.)*
- **Eccles, R. G., Krzus, M. P.** (2010). *One Report: Integrated Reporting
  for a Sustainable Strategy.* Wiley. *(On non-financial drivers of valuation.)*

---

## §7 — Solar PV industry data (used in `scenarios/solar-v1/`)

All numerical parameters in the solar-v1 scenario are *adapted from public
industry data*. Specific values are not lifted verbatim — we round and
round-trip them through plausibility tests so the simulation produces realistic
play patterns. Sources used:

### Industry costs, prices, and capacity

- **International Renewable Energy Agency (IRENA).** *Renewable Power
  Generation Costs.* Annual report series (2014–present). Public domain.
  - LCOE, capex, opex for residential, commercial, and utility-scale PV.
- **International Energy Agency Photovoltaic Power Systems Programme (IEA
  PVPS).** *Trends in Photovoltaic Applications.* Annual report. Public.
- **Joint Research Centre (JRC), European Commission.** *PV Status Report.*
  Annual. Public.
- **Fraunhofer Institute for Solar Energy Systems (ISE).** *Photovoltaics
  Report.* Periodic public report.
- **VDMA.** *International Technology Roadmap for Photovoltaic (ITRPV).*
  Annual. Public industry consensus on materials, efficiencies, and
  cost trajectories.

### Wages and personnel costs

- **Eurostat.** Labour-cost-survey data for European manufacturing
  (NACE C26 — Computer, electronic and optical products; or C27 —
  Electrical equipment). Public domain.

### Macroeconomic backdrop for scenario events

- **European Central Bank.** *Economic Bulletin.* Public.
- **OECD.** *Economic Outlook.* Public.

---

## §8 — Pedagogy and assignment design (used in pedagogy layer)

### Strategy Map and Balanced Scorecard

- **Kaplan, R. S., Norton, D. P.** (1996). *The Balanced Scorecard:
  Translating Strategy into Action.* Harvard Business School Press.
- **Kaplan, R. S., Norton, D. P.** (2004). *Strategy Maps: Converting
  Intangible Assets into Tangible Outcomes.* Harvard Business School Press.

### BCG growth-share matrix (for the Hot-Chair-style analyses)

- **Henderson, B. D.** (1970). *The Product Portfolio.* BCG Perspectives,
  No. 66. Public.

### Product life-cycle analysis

- **Levitt, T.** (1965). *Exploit the Product Life Cycle.* *Harvard Business
  Review*, 43(6): 81–94.
- **Day, G. S.** (1981). *The Product Life Cycle: Analysis and Applications
  Issues.* *Journal of Marketing*, 45(4): 60–67.

### Forecast accuracy and planning-quality scoring

- **Hyndman, R. J., Athanasopoulos, G.** (2021). *Forecasting: Principles and
  Practice* (3rd ed.). OTexts, Melbourne. Free online at
  `https://otexts.com/fpp3/`. Chapter 5 ("The forecaster's toolbox") defines
  the symmetric mean absolute percentage error (sMAPE) used as the
  planning-quality KPI score in `09-pedagogy.md`.
- **Makridakis, S.** (1993). *Accuracy Measures: Theoretical and Practical
  Concerns.* *International Journal of Forecasting*, 9(4): 527–529. The
  paper that introduced sMAPE as a symmetric, bounded alternative to MAPE.

### Peer assessment in team-based learning

- **Topping, K. J.** (2009). *Peer Assessment.* *Theory Into Practice*, 48(1):
  20–27.
- **Fellenz, M. R.** (2006). *Toward Fairness in Assessing Student Groupwork:
  A Protocol for Peer Evaluation of Individual Contributions.* *Journal of
  Management Education*, 30(4): 570–591.

### General management simulation literature

- **Faria, A. J., Hutchinson, D., Wellington, W. J., Gold, S.** (2009).
  *Developments in Business Gaming: A Review of the Past 40 Years.*
  *Simulation & Gaming*, 40(4): 464–487.
- **Wolfe, J.** (1976). *The Effects and Effectiveness of Simulations in
  Business Policy Teaching Applications.* *Academy of Management Review*,
  1(2): 47–56.

---

## §9 — Not used (deliberately)

To make the IP discipline explicit: we do **not** use, cite, paraphrase, or
otherwise derive content from:

- Commercial business-simulation product manuals (TOPSIM, Capsim, Marketplace,
  Cesim, etc.) — these are proprietary expressions.
- Any specific competitor's published commercial parameter sets.
- Any unpublished course material from any specific instructor.

If a contributor accidentally introduces text or numbers derived from such a
source, the contribution must be removed and rewritten from a public source
listed above.

---

## §10 — How to add a source

When you add a new formula or parameter:

1. Locate a public source supporting it.
2. Add a citation here in the appropriate section.
3. Reference the section number (`sources §N`) inline in the spec doc.
4. If no public source exists, mark the choice as *original design* and
   justify in the spec — and ideally validate it against industry data
   during calibration.
