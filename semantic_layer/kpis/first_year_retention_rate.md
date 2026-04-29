---
kpi_id: first_year_retention_rate
domain: student_outcomes
source_survey: null
metric_type: administrative_record_rate
status: partial
last_reviewed: 2026-04-27
owner: oirp-chat (portfolio project)
---

# First-Year Retention Rate

## Definition

The percentage of first-year undergraduate students who **return to Carleton
the following fall** (one-year retention) or **two falls later** (two-year
retention), based on registration records.

This is a **behavioural metric drawn from the registration system**, not a
survey self-report. It is one of Carleton's most-cited institutional
performance indicators and is referenced as a financial-sustainability driver
in Carleton's annual operating budget reports.

> **Critical disambiguation.** "Retention rate" is used loosely in casual
> conversation but has *several* precise definitions at OIRP, which produce
> different numbers. The agent must clarify which variant the user wants
> before quoting a value, or surface multiple variants. See **Variants**
> below.

## Variants

OIRP has historically reported **at least four** distinct retention/progression
metrics, each with a different denominator or numerator. They are not
interchangeable.

| Variant | Cohort definition | Numerator | Denominator | Typical use |
| --- | --- | --- | --- | --- |
| **Retention (FTFY, 1-year)** | New full-time first-year (FTFY) students | Still registered at Carleton 1 year later, any program/year-level | FTFY entering cohort | Most common public-facing figure; closest to the IPEDS / U.S.-style retention rate |
| **Retention (FTFY, 2-year)** | New full-time first-year students | Still registered at Carleton 2 years later, any program/year-level | FTFY entering cohort | Companion 2-year variant |
| **Retention (all first-year, 1-year or 2-year)** | All first-year students (new + returning) | Still registered at Carleton 1 or 2 years later | All first-year students at start | A broader figure; tends to look lower than the FTFY variant because the denominator includes students already repeating first year |
| **Progression rate** | Same as retention cohort | Promoted to **second-year level** (or third-year level for 2-year progression) | Same | A stricter measure than retention — students who stayed at Carleton but didn't accumulate enough credits to advance year-level are *retained* but did not *progress* |

A fifth related metric — **graduation rate** — is a separately defined MTCU
performance indicator (see `glossary.md`); it is not a retention rate but is
often discussed alongside.

## Calculation

```
retention_rate_FTFY_1yr[cohort_year]
  = (students from cohort_year FTFY entering class still registered at Carleton in fall of cohort_year + 1)
    / (size of cohort_year FTFY entering class)
```

```
progression_rate_FTFY_1yr[cohort_year]
  = (students from cohort_year FTFY entering class who reached second-year level by fall of cohort_year + 1)
    / (size of cohort_year FTFY entering class)
```

Both numerator and denominator come from registration records as of the
relevant fall snapshot date. Allowable cohort adjustments (e.g., students who
deferred entry, withdrew due to documented medical reasons) follow OIRP's
standard methodology, which has been stable but is not re-derived in this
file — defer to OIRP's published methodology if a user asks for the exact
exclusion rules.

## Synonyms

- "retention" / "retention rate"
- "first-year retention"
- "fall-to-fall retention"
- "first-to-second-year retention"
- "persistence rate" / "first-year persistence"
- "returning students" (NB: also a separate cohort term — see Disambiguation)
- "stayed at Carleton" / "came back"
- "year 1 to year 2" / "1-to-2"
- "attrition" (the *complement* — see below)

**"Returning students" is overloaded.** It can mean (a) students who returned
for year 2, i.e., were retained, **or** (b) the OIRP cohort term for
non-first-time first-year students (students repeating first year). When in
doubt, ask the user which they mean.

**"Attrition" is 100 − retention.** OIRP has historically reported attrition
in some years (e.g., the legacy Performance Indicators series) and retention
in others. If a user asks about attrition, convert the verified retention
value rather than treating it as a separate metric.

## Source Documents

OIRP retention data is published across multiple sources, each with different
vintages and granularity:

| Source | Coverage | Notes |
| --- | --- | --- |
| **CUDO Section E** (`oirp.carleton.ca/cudo/`, current) | Annual, recent years | Common University Data Ontario reporting. Fall *N* CUDO normally publishes year-1 retention for the fall *N − 2* entering cohort. |
| **Departmental Measures / Academic Planning Indicators** | Multi-year, by faculty | Internal-facing planning documents; some may require Carleton authentication. |
| **OIRP Databook — Student Statistics** (`oirp.carleton.ca/databook/`) | Long history | Multi-year tables including admissions, enrolment, and graduation flows. |
| **Performance Indicators legacy series** (`oirp.carleton.ca/pi-2000/`, `pi-2001/`, etc.) | 1990s–early 2000s | Historical context only; values published here are **not** current. Useful for long-trend framing. |
| **Carleton Operating Budget Reports** (annual) | Qualitative references | Cite "strong retention rates" as a financial driver but rarely give specific numbers. |
| **Students and Enrolment Annual Report** | Annual | Qualitative characterizations (e.g., "two-year retention remains amongst historic highs" — 2023-24 Annual Report). |

## Verified Values

The state of this file is **`partial`**. Recent specific year-by-year values
require manual extraction from CUDO Section E and Departmental Measures
sources that were not fully accessible at the time of last review. The agent
should respect this state — see **Confidence Tier Guidance** below.

### What we have verified

```json
[
  {
    "cohort_year": 2000,
    "variant": "retention_FTFY_1yr",
    "value_pct": 85.1,
    "derivation_note": "Reported as 14.9% one-year attrition for the new full-time first-year 2000 cohort; retention = 100 − attrition.",
    "source": {
      "file": "pi-2001 retention page (legacy)",
      "url": "https://oirp.carleton.ca/pi-2001/html/retention.htm",
      "quote_anchor": "the proportion who are no longer at Carleton a year later has been steadily dropping and currently stands at 14.9%"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-27"
  },
  {
    "cohort_year": 2000,
    "variant": "progression_FTFY_1yr",
    "value_pct": 68.9,
    "source": {
      "file": "pi-2001 retention page (legacy)",
      "url": "https://oirp.carleton.ca/pi-2001/html/retention.htm",
      "quote_anchor": "Of the 2000 entering cohort of new full-time first year students, 68.9% progressed to second year level"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-27"
  },
  {
    "cohort_year": 1999,
    "variant": "retention_FTFY_2yr",
    "value_pct": 71.7,
    "derivation_note": "Reported as 28.3% two-year attrition for the new full-time first-year 1999 cohort; retention = 100 − attrition.",
    "source": {
      "file": "pi-2001 retention page (legacy)",
      "url": "https://oirp.carleton.ca/pi-2001/html/retention.htm",
      "quote_anchor": "the proportion who are no longer at Carleton two years later has also been declining and now stands at 28.3%"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-27"
  },
  {
    "cohort_year": 1999,
    "variant": "retention_all_first_year_2yr",
    "value_pct": 67.0,
    "derivation_note": "Reported as 33.0% two-year attrition counting new and returning first-year students; retention = 100 − attrition.",
    "source": {
      "file": "pi-2001 retention page (legacy)",
      "url": "https://oirp.carleton.ca/pi-2001/html/retention.htm",
      "quote_anchor": "33.0% counting new and returning students"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-27"
  }
]
```

### Qualitative anchors (recent)

For recent years, the following qualitative characterizations are confirmed
from Carleton-published sources and may be reported by the agent:

```json
[
  {
    "scope": "two_year_retention",
    "period": "fall_2023_cohort_outcome",
    "characterization": "Two-year retention rate remains amongst historic highs.",
    "source": {
      "file": "Students and Enrolment 2023-2024 Annual Report",
      "url": "https://carleton.ca/students-enrolment/wp-content/uploads/sites/36/2024/10/Students-and-Enrolment-2023-2024-Annual-Report-WEB.pdf"
    },
    "verified_on": "2026-04-27",
    "agent_guidance": "Report as a qualitative finding only; do not fabricate a specific percentage."
  },
  {
    "scope": "retention_general",
    "period": "2024-25_planning",
    "characterization": "Strong retention rates cited as a main driver of Carleton's financial sustainability.",
    "source": {
      "file": "Carleton 2024-25 Operating Budget Report",
      "url": "https://carleton.ca/financialservices/wp-content/uploads/24-25-Operating-Budget-Report.pdf"
    },
    "verified_on": "2026-04-27",
    "agent_guidance": "Useful for context; not a specific numerical value."
  }
]
```

### What is not yet extracted

The following are **known to exist** in OIRP-published sources but have not
been manually extracted into this file. The agent should refer the user to the
relevant source rather than invent a number.

- Year-by-year retention rates for any cohort year between 2001 and present.
- Faculty-level retention rates (e.g., FASS, FED, FPA, Sprott, Science).
- Domestic vs international cohort retention.
- Retention by entrance average band.
- Full vs part-time cohort retention.

> **Strict rule for the agent.** When asked for a specific recent retention
> percentage that is not in the verified values block above, do **not**
> generate a number. Instead, respond with:
>
> > *"That specific value isn't in my verified store yet. OIRP publishes
> > recent retention rates in CUDO Section E and the Departmental Measures
> > set; the most recent qualitative reference I have is from Carleton's
> > 2023-24 Students and Enrolment Annual Report, which describes Carleton's
> > two-year retention as 'amongst historic highs.' Want me to point you at
> > the source pages?"*

## Comparison Context

Carleton retention is most meaningfully compared against:

- **Other Ontario universities** via CUDO Section E (every Ontario institution
  reports the same standardized retention metric). When a user asks "how does
  Carleton compare," CUDO is the right comparator, not U.S. data.
- **Carleton's own historical trajectory.** Retention is a slow-moving metric;
  trend over 5–10 years is more interpretable than a single-year change.

The metric is **not** comparable to U.S. liberal-arts-college retention rates
without heavy caveats. (Be especially cautious if web search surfaces
"Carleton College" data — that's a separate institution in Minnesota, not
Carleton University in Ottawa. See `glossary.md`.)

## Caveats and Methodological Notes

**Carleton University vs Carleton College.** A frequent confusion. *Carleton
University* in Ottawa, Canada is the subject of this file. *Carleton College*
is a private liberal-arts college in Northfield, Minnesota. Their retention
rates are unrelated. If a user appears to be asking about the wrong
institution, clarify before answering.

**Cohort definition matters more than people expect.** Whether a 4-year
graduation rate is "high" depends entirely on which cohort it's drawn from
(new full-time first-year vs all-students; including or excluding transfers;
whether students who took a documented leave are counted). The same caution
applies to retention. When in doubt, defer to OIRP's published cohort
definition rather than reasoning from first principles.

**MTCU/Ministry definitions for graduation rate are regulatory.** Carleton's
graduation rate, when reported as a Ministry of Training, Colleges and
Universities (MTCU) performance indicator, follows a specific definition:
*"the proportion of students graduating who start their program as full-time
students and who graduate with a degree in any discipline at the same
university within seven years."* Do not paraphrase this loosely.

**Retention is a lagging indicator.** A retention rate published in 2026
typically describes a cohort that entered in 2024 or earlier. Recent retention
figures will reflect pre-pandemic and early-pandemic cohorts more than the
current student experience.

**Composition effects.** Retention rates rise and fall partly because of
changes in the *composition* of the entering cohort (entrance averages,
program mix, sex/gender mix, home region). Carleton's legacy Performance
Indicator series explicitly modeled this composition effect. Treat year-over-
year changes with that nuance, especially across periods of significant
admissions-policy change.

**Triannual/annual cadence varies by source.** CUDO publishes annually.
Departmental Measures may update at different cadences. A "2024 retention
rate" can mean different cohort years depending on the source.

## Confidence Tier Guidance

- **High confidence.**
  - The four legacy values for 1999 and 2000 cohorts in the verified-values
    block above → look up.
  - The qualitative recent characterizations (2023-24 Annual Report
    "amongst historic highs"; budget-report references to "strong retention
    rates") → look up and cite as qualitative.
  - The list of variants and what each means.

- **Medium confidence.**
  - General trend framing: "Carleton's first-year retention has been on a
    long-run upward trend since the 1990s, and recent characterizations from
    Carleton-published sources continue to describe it as among the
    institution's historic highs."
  - Distinguishing retention from progression from graduation when a user
    conflates them.

- **Low confidence — refuse to invent numbers.**
  - **Specific recent year retention percentages** not in the verified
    block. The correct response is to direct the user to CUDO Section E or
    Departmental Measures, *not* to estimate.
  - **Faculty-level retention values.** Not yet extracted; not in this file.
  - **International vs domestic retention.** Not yet extracted.
  - **Causal claims** about why retention has changed.
  - **Forecasts** of future retention.
  - **Cross-institutional comparisons with specific peer values** beyond
    CUDO; OIRP does not publish a peer-comparison set.

## Related KPIs

- *(Future KPI)* `seven_year_graduation_rate` — MTCU performance indicator;
  related but distinct from retention.
- *(Future KPI)* `progression_rate_to_year_2` — stricter milestone metric;
  related and partially overlapping in this file.
- *(Future KPI)* `entering_cohort_size_FTFY` — denominator for retention;
  changes over time, useful when interpreting absolute counts.
- *(Future KPI)* `entering_cohort_average_admission_grade` — composition
  driver of retention.
- `would_choose_same_institution` — *attitudinal* analogue from NSSE; do **not**
  conflate with behavioural retention. The two diverge in important ways.

## Glossary References

- **FTFY** — First-Time First-Year. New, full-time, first-year students
  entering in a given fall. The standard cohort for IPEDS/CUDO retention.
- **Cohort year** — The fall in which the entering class first registered.
  Year-1 retention for the 2022 cohort = fall 2023 still-enrolled rate.
- **Retention vs progression** — Retention measures *staying* at Carleton.
  Progression measures *advancing* to the next year level. Progression is
  always lower or equal.
- **MTCU** — Ontario Ministry of Training, Colleges and Universities (the
  regulator setting graduation-rate definitions). Now succeeded by the
  Ministry of Colleges and Universities; legacy "MTCU" terminology persists
  in OIRP documents.
- **CUDO** — Common University Data Ontario; standardized inter-institutional
  reporting framework managed by COU/CUPA.
- **Carleton University** — The institution in Ottawa, Ontario referenced
  throughout this file. **Not** Carleton College (Minnesota, USA).

## Change Log

| Date       | Change                                                                                                          | Reviewer |
| ---------- | --------------------------------------------------------------------------------------------------------------- | -------- |
| 2026-04-27 | Initial draft. Verified legacy 1999/2000 values from PI-2001 series. Recent values flagged as not yet extracted. | (you)    |
