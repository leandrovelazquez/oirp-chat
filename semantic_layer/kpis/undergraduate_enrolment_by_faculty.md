---
kpi_id: undergraduate_enrolment_by_faculty
domain: enrolment
source_survey: null
metric_type: headcount_with_dimensions
status: partial
last_reviewed: 2026-04-27
owner: oirp-chat (portfolio project)
---

# Undergraduate Enrolment by Faculty

## Definition

The number of undergraduate students registered at Carleton in a given fall
term, broken down by **academic faculty** of program registration. This is a
behavioural metric drawn from the registration system (OIRP Databook / Data
Cubes), not a survey self-report.

Carleton's five undergraduate-degree-granting faculties:

| Code | Faculty                              |
| ---- | ------------------------------------ |
| FASS | Faculty of Arts and Social Sciences  |
| FPA  | Faculty of Public Affairs            |
| Sprott | Sprott School of Business          |
| Science | Faculty of Science                |
| FED  | Faculty of Engineering and Design    |

> **Critical disambiguation.** "Enrolment" is one of the most overloaded
> terms in institutional research. Before quoting a number, the agent must
> establish which **counting base** the user wants. See **Variants** below.

## Variants

| Variant | What it counts | When to use |
| --- | --- | --- |
| **Headcount, full-time** | Distinct students registered as full-time in the fall snapshot | Most common public-facing figure; the default if not specified |
| **Headcount, all (full-time + part-time)** | All registered students | When users ask about total student body size |
| **FTE (full-time equivalent)** | Course-load-weighted count (part-time students count as a fraction) | Used in funding calculations and Ontario MTCU/MCU reporting; differs noticeably from headcount |
| **New first-year intake** | Students newly entering year 1 in a given fall | Used for cohort and admissions-yield analysis |
| **Continuing enrolment** | Students returning from a previous Carleton year | Complement of new intake |
| **Domestic vs international** | Cross-cuts all of the above | A salient operational dimension since the 2024 federal international-student cap |

A *single* headline number — "Carleton has X undergraduates" — is almost
always one of these variants in disguise. When in doubt, ask the user which
they want, or report multiple variants side by side.

## Calculation

```
undergraduate_enrolment[year, faculty, variant]
  = COUNT( students registered at Carleton in undergraduate program
            in fall N
            with home faculty = faculty
            satisfying variant-specific filter (FT / all / FTE-weighted) )
```

Snapshot is taken on or near **November 1** of the fall term, which is the
standard Ontario reporting date. FTE weights follow MCU (formerly MTCU)
conventions; this file does not redefine them — defer to OIRP's published
methodology if a user asks for the exact weighting rules.

## Synonyms

- "enrolment" / "enrollment" (Canadian/American spellings; both are used)
- "headcount"
- "student numbers" / "how many students"
- "student body size"
- "registered students"
- "FTE" / "full-time equivalent" (specific variant — see above)
- "intake" / "first-year intake" (specific variant — see above)

**Disambiguation.**

- "Course enrolment" is a *different* metric (number of course registrations,
  with one student counted multiple times across courses). Not this KPI.
- "Program enrolment" can mean either student count by program or
  application/admission counts. Clarify with the user.
- "Class size" is a different concept entirely (students per course section).
- *Faculty* in this file always means an academic faculty (FASS, FPA, etc.) —
  **not** academic staff/professors. "How many students per faculty" is a
  ratio, not an enrolment figure.

## Source Documents

| Source | Coverage | Notes |
| --- | --- | --- |
| **OIRP Databook — Student Enrolment** (`oirp.carleton.ca/databook/`) | Multi-year tables by faculty, level, and FT/PT status | Primary source for verified headcount values. |
| **OIRP Data Cubes / Perspectives** | Interactive cross-tabulation | Allows breakdowns by faculty × department × degree × FT/PT × domestic/international. Some access may require Carleton authentication. |
| **CUDO Section B / Section E** | Annual standardized inter-institutional figures | Use when comparing Carleton to other Ontario universities. |
| **Carleton Operating Budget Reports** (annual, public) | Trend characterizations and cohort-vs-peak comparisons | Cite-able for qualitative context; specific faculty breakdowns rarely included. |
| **Students and Enrolment Annual Report** | Annual qualitative highlights | Useful for year-over-year directional context. |
| **NSSE Summaries** | Faculty distribution of *survey respondents* | Indirect reference only; describes respondent mix, which OIRP states is *similar to* but not identical to the actual first-year/final-year student distribution. |

## Verified Values

The state of this file is **`partial`**. Absolute headcount and FTE values by
faculty for recent years require manual extraction from OIRP Databook tables
that were not directly accessible at the time of last review. The agent
should respect this state — see **Confidence Tier Guidance**.

### Proportional faculty mix (first-year + final-year, 2023, NSSE-derived)

Carleton's NSSE 2023 summary publishes a faculty breakdown of survey
respondents and explicitly states this distribution is *similar to* the
actual faculty distribution of first-year and final-year undergraduates. This
is **not** a substitute for OIRP's actual enrolment data, but is a defensible
rough indicator of relative faculty size for those two cohorts.

```json
[
  {
    "year": 2023,
    "scope": "first_year_plus_final_year_NSSE_respondents",
    "respondent_counts_by_faculty": {
      "FASS": 525,
      "FPA": 461,
      "Sprott": 123,
      "Science": 417,
      "FED": 504,
      "total": 2030
    },
    "respondent_proportions_by_faculty_pct": {
      "FASS": 25.9,
      "FPA": 22.7,
      "Sprott": 6.1,
      "Science": 20.5,
      "FED": 24.8
    },
    "source": {
      "file": "nsse_2023_summary.pdf",
      "page": 4,
      "table": "Table 1",
      "quote_anchor": "The distribution of respondents across faculties is similar to the faculty distribution of first and final-year students at Carleton."
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-27",
    "agent_guidance": "Useful for qualitative statements like 'FASS and FED are roughly Carleton's two largest undergraduate faculties, each around a quarter of first/final-year respondents; Sprott is the smallest at roughly 6%.' Do **not** present as actual enrolment headcounts."
  }
]
```

### Year-over-year and long-term anchors (qualitative)

```json
[
  {
    "scope": "new_full_time_first_year_undergraduate",
    "period": "fall_2023",
    "characterization": "Down 3.6% in full-time new undergraduate first-year students for the fall 2023 term (as of November 1).",
    "source": {
      "file": "Students and Enrolment 2023-2024 Annual Report",
      "url": "https://carleton.ca/students-enrolment/wp-content/uploads/sites/36/2024/10/Students-and-Enrolment-2023-2024-Annual-Report-WEB.pdf"
    },
    "verified_on": "2026-04-27",
    "agent_guidance": "Report the directional change as quoted; do not derive an absolute headcount from this percentage."
  },
  {
    "scope": "new_domestic_first_year_undergraduate",
    "period": "fall_2023_vs_peak",
    "characterization": "Fall 2023 new domestic first-year cohort was at 87% of the peak intake year (2017).",
    "source": {
      "file": "Carleton 2024-25 Operating Budget Report",
      "url": "https://carleton.ca/financialservices/wp-content/uploads/24-25-Operating-Budget-Report.pdf"
    },
    "verified_on": "2026-04-27"
  },
  {
    "scope": "new_international_first_year_undergraduate",
    "period": "fall_2023_vs_peak",
    "characterization": "Fall 2023 new international first-year cohort stood at 61% of the comparable peak year (2018).",
    "source": {
      "file": "Carleton 2024-25 Operating Budget Report",
      "url": "https://carleton.ca/financialservices/wp-content/uploads/24-25-Operating-Budget-Report.pdf"
    },
    "verified_on": "2026-04-27"
  },
  {
    "scope": "international_undergraduate_intake",
    "period": "2024_25_vs_2018_peak",
    "characterization": "By 2024-25, undergraduate international student intake had dropped 72% from the 2018 peak of more than 800 students.",
    "source": {
      "file": "Carleton 2025-26 Operating Budget Report",
      "url": "https://carleton.ca/financialservices/wp-content/uploads/250513-2025-26-Operating-Budget-Report.pdf"
    },
    "verified_on": "2026-04-27"
  },
  {
    "scope": "international_undergraduate_intake",
    "period": "2024_25_vs_fall_2020",
    "characterization": "Compared to fall 2020, undergraduate international intake had dropped 70% as of 2024-25.",
    "source": {
      "file": "Carleton 2025-26 Operating Budget Report",
      "url": "https://carleton.ca/financialservices/wp-content/uploads/250513-2025-26-Operating-Budget-Report.pdf"
    },
    "verified_on": "2026-04-27"
  },
  {
    "scope": "international_undergraduate_intake",
    "period": "2025_26_outlook",
    "characterization": "An additional ~50% decline in international undergraduate intake was projected for 2025-26 against 2024-25 levels, driven by the federal international student cap and visa-processing delays.",
    "source": {
      "file": "Carleton 2025-26 Operating Budget Report",
      "url": "https://carleton.ca/financialservices/wp-content/uploads/250513-2025-26-Operating-Budget-Report.pdf"
    },
    "verified_on": "2026-04-27",
    "agent_guidance": "Frame as a Carleton-published projection, not an observed value."
  }
]
```

### What is not yet extracted

The following are **known to exist** in OIRP-published sources (Databook,
Data Cubes, CUDO Section B/E) but have not been manually extracted into this
file. The agent should refer the user to the relevant source rather than
invent a number.

- Absolute headcount values by faculty for any specific recent year
  (full-time, part-time, or all).
- FTE values by faculty.
- Domestic vs international headcounts by faculty.
- Multi-year time series of enrolment by faculty.
- Department-level (within-faculty) breakdowns.
- Year-of-study breakdowns within faculty.

> **Strict rule for the agent.** When asked for a specific recent
> headcount, FTE, or year-by-year-by-faculty value not present in the
> verified blocks above, do **not** generate a number. Instead, respond
> with:
>
> > *"I don't have that specific value verified yet. OIRP publishes
> > enrolment-by-faculty data in the OIRP Databook and the Data Cubes /
> > Perspectives tools (some access may require Carleton authentication).
> > For inter-institutional comparisons, CUDO Section B is the right
> > source. Want me to point you to those?"*

## Headline Findings (qualitative, 2023–2026 context)

The agent should reach for these as the canonical narrative when a user
asks about the broad shape of undergraduate enrolment at Carleton.

1. **Five undergraduate faculties.** FASS, FPA, Sprott, Science, FED.
2. **FASS and FED are roughly Carleton's two largest undergraduate
   faculties** by first-year + final-year cohort size, each around a quarter
   of those cohorts; Sprott is the smallest at roughly 6%. (Source: NSSE
   2023 respondent distribution, characterized by OIRP as similar to the
   actual student distribution.)
3. **First-year intake declined in 2023.** Carleton was down 3.6% in
   full-time new undergraduate first-year students for fall 2023.
4. **Domestic intake is below its peak.** Fall 2023 domestic first-year
   intake was at 87% of the 2017 peak.
5. **International intake has dropped sharply.** Fall 2023 international
   first-year intake was 61% of the 2018 peak; by 2024-25, undergraduate
   international intake overall had fallen 72% from the 2018 peak.
6. **Federal cap and visa delays are an active driver.** Carleton's 2025-26
   budget projected a further ~50% international undergraduate intake
   decline against 2024-25, citing the federal international student cap.

## Caveats and Methodological Notes

**Snapshot date.** Carleton's official enrolment counts are taken near
November 1 of the fall term. Numbers reported earlier in the term may be
preliminary; numbers from late spring/summer reports reflect the previous
fall snapshot.

**Faculty of registration vs faculty of teaching.** A student registered in
a FASS program may take many courses in FED, FPA, etc. This KPI counts
*program registration* (the student's home faculty), not where they take
their courses. "Course enrolment" or "credit hours by teaching faculty" is a
different metric.

**Cross-listed and combined-honours programs.** Some programs span faculties
(e.g., combined honours, interdisciplinary programs). OIRP applies a
consistent rule for assigning these to a primary faculty in the Databook;
the agent should not redo this assignment.

**Domestic/international classification.** Based on student visa/citizenship
status at registration. A student's status can change mid-degree (e.g.,
permanent residency granted), but the KPI typically uses the status as of
the snapshot date.

**Pandemic and policy context (2020–present).** Several factors complicate
year-over-year comparisons in this period: pandemic-related enrolment
disruptions in fall 2020, the federal international student cap announced in
January 2024, persistent visa-processing delays, and Ontario's domestic
tuition freeze. Trend characterizations should account for this context
rather than treating year-over-year change as purely organic.

**FTE vs headcount.** A common error is to compare an FTE figure from one
source against a headcount from another. They will not agree, sometimes by
double-digit percentages. Always confirm the variant before comparing.

**NSSE respondent distribution is not enrolment.** The NSSE-derived
proportions in the verified-values block describe *survey respondents in
first and final year only*, not the full undergraduate enrolment. Mid-year
students, part-time students, and second/third-year students are not
represented. Use only as a rough relative indicator.

**Carleton University vs Carleton College.** As with the retention KPI,
results from web search may surface Carleton College (Northfield, Minnesota)
data. That is a different institution. See `glossary.md`.

## Confidence Tier Guidance

- **High confidence.**
  - The list of five undergraduate faculties.
  - The proportional faculty mix from NSSE 2023 (presented with the
    "first-year + final-year respondents" caveat).
  - The qualitative anchors above (3.6% fall-2023 decline; 87% of 2017 peak
    for domestic; 61% of 2018 peak for international; 72% drop since 2018
    peak by 2024-25; ~50% projected further decline for 2025-26).

- **Medium confidence.**
  - General narrative framing combining the five qualitative anchors into a
    coherent picture of Carleton's undergraduate enrolment trajectory
    2017–2026.
  - Identifying that international undergraduate enrolment is a current
    institutional financial-risk driver (cited as such in Carleton's
    operating budget reports).

- **Low confidence — refuse to invent numbers.**
  - **Specific absolute headcounts** by faculty for any year. Not in the
    verified store; direct user to Databook/Data Cubes.
  - **Specific FTE values** by faculty. Not in the verified store.
  - **Department-level breakdowns** within a faculty.
  - **Cross-institutional comparisons with specific peer values** beyond
    CUDO.
  - **Forecasts** beyond what Carleton's own budget reports project.
  - **Causal claims** about why a specific faculty has grown or shrunk.
  - **Inferring per-faculty international vs domestic splits** from the
    aggregate institutional figures.

## Related KPIs

- *(Future KPI)* `graduate_application_volume` — separate population
  (graduate, not undergraduate); different cap and admissions dynamics.
- *(Future KPI)* `undergraduate_enrolment_FTE` — same population, different
  counting base; will share most of this file's caveats.
- *(Future KPI)* `new_first_year_intake_by_faculty` — narrower cohort
  (new entrants only); the cohort the qualitative anchors above primarily
  describe.
- *(Future KPI)* `international_undergraduate_share` — the international
  proportion within undergraduate enrolment; a cross-cut of this KPI.
- `first_year_retention_rate` — denominator for retention is closely
  related to first-year intake measured here. The two KPIs share cohort
  conventions.

## Glossary References

- **FTE (Full-Time Equivalent)** — Course-load-weighted enrolment count.
  A part-time student taking half the standard course load counts as 0.5
  FTE. FTE differs from headcount and is used in MCU funding formulas.
- **Headcount** — Distinct-student count, regardless of course load. The
  default counting base unless otherwise specified.
- **Snapshot date** — November 1 (or the closest equivalent business day),
  the Ontario standard reference date for fall enrolment reporting.
- **MCU / MTCU** — Ontario Ministry of Colleges and Universities (formerly
  Ministry of Training, Colleges and Universities); sets reporting
  conventions for FTE and other metrics.
- **CUDO** — Common University Data Ontario; the standardized
  inter-institutional data set. Section B and Section E cover enrolment
  dimensions.
- **Faculty (academic)** — One of Carleton's five undergraduate-degree-
  granting faculties: FASS, FPA, Sprott, Science, FED. Distinct from
  *faculty (academic staff)*.
- **Federal international student cap** — Government of Canada policy
  introduced in January 2024 limiting study-permit issuance, with
  significant downstream effects on Carleton's international enrolment.

## Change Log

| Date       | Change                                                                                                       | Reviewer |
| ---------- | ------------------------------------------------------------------------------------------------------------ | -------- |
| 2026-04-27 | Initial draft. Verified NSSE-derived proportional mix and qualitative anchors from Annual Report and Operating Budgets. Absolute headcounts and FTE flagged as not yet extracted. | (you)    |
