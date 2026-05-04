---
kpi_id: would_choose_same_institution
domain: student_engagement
source_survey: NSSE
metric_type: simple_percentage
status: verified
last_reviewed: 2026-04-27
owner: oirp-chat (portfolio project)
---

# Would Choose Same Institution Again (NSSE)

## Definition

The percentage of NSSE respondents who, when asked *"If you could start over
again, would you choose the same institution?"*, answered either **"Definitely
Yes"** or **"Probably Yes"** on a four-point scale (Definitely Yes / Probably
Yes / Probably No / Definitely No). Reported separately for **first-year** and
**final-year** undergraduate respondents.

This is one of NSSE's two headline overall-satisfaction questions. The other is
`overall_experience_rating` (see Related KPIs). The two are closely related but
measure different constructs: this question captures **retrospective
endorsement** ("would I do it again"), while overall experience captures
**evaluative satisfaction** ("how was it"). They typically move together but
not always.

## Calculation

```
would_choose_same_institution_yes_pct
  = (count of "Definitely Yes" responses + count of "Probably Yes" responses)
    / (total respondents to the question)
```

Institutional results are **gender-weighted** by NSSE before publication, to
correct for known female response bias. Both Carleton and Ontario consortium
figures in OIRP summaries are weighted; do not attempt to re-weight or combine
with unweighted samples.

## Synonyms

- "would choose Carleton again"
- "would they pick the same school"
- "would students re-enrol"
- "institutional loyalty" (NSSE-grounded)
- "would do it again" / "start over"
- "definitely or probably yes"
- "student endorsement"

**Disambiguation.** This is **not** the same as a Net Promoter Score, an alumni
giving rate, or a re-enrolment rate. It is a hypothetical retrospective
question on the NSSE instrument. If a user asks about NPS, alumni surveys, or
actual transfer behaviour, this metric is not the answer — clarify with them.

## Source Documents

| Survey Year | Source File              | Location                                 |
| ----------- | ------------------------ | ---------------------------------------- |
| 2023        | `nsse_2023_summary.pdf`  | "Overall Experience", Figure 4, p. 6     |
| 2020        | `nsse_2020_summary.pdf`  | "Overall Experience" section             |
| 2017        | `nsse_2017_summary.pdf`  | "Overall Experience" section             |
| 2014        | `nsse_2014_summary.pdf`  | "Overall Experience" section             |
| 2011        | `nsse_2011_summary.pdf`  | "Overall Experience" section             |

(2020/2017/2014/2011 page references to be filled in as PDFs are ingested.)

## Verified Values

```json
[
  {
    "year": 2023,
    "cohort": "first_year",
    "comparison_group": "carleton",
    "value_pct": 82,
    "metric_variant": "definitely_or_probably_yes",
    "source": {
      "file": "nsse_2023_summary.pdf",
      "page": 6,
      "figure": "Figure 4",
      "quote_anchor": "Eighty-two percent of first-year respondents"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-27"
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "comparison_group": "carleton",
    "value_pct": 81,
    "metric_variant": "definitely_or_probably_yes",
    "source": {
      "file": "nsse_2023_summary.pdf",
      "page": 6,
      "figure": "Figure 4",
      "quote_anchor": "81 percent of final-year respondents reported that they would choose Carleton again"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-27"
  },
  {
    "year": 2023,
    "cohort": "first_year",
    "comparison_group": "ontario_consortium_excl_carleton",
    "value_pct": 81,
    "metric_variant": "definitely_or_probably_yes",
    "derivation_note": "Derived from Figure 4 stacked bar: 'Definitely Yes' 31% + 'Probably Yes' 50% = 81% for Rest of Ontario first-year.",
    "source": {
      "file": "nsse_2023_summary.pdf",
      "page": 7,
      "figure": "Figure 4",
      "quote_anchor": "Rest of Ontario 31% 50% 16% 4%"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-27"
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "comparison_group": "ontario_consortium_excl_carleton",
    "value_pct": 77,
    "metric_variant": "definitely_or_probably_yes",
    "derivation_note": "Derived from Figure 4 stacked bar: 'Definitely Yes' 30% + 'Probably Yes' 47% = 77% for Rest of Ontario final-year.",
    "source": {
      "file": "nsse_2023_summary.pdf",
      "page": 7,
      "figure": "Figure 4",
      "quote_anchor": "Rest of Ontario 30% 47% 17% 6%"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-27"
  }
]
```

### Response Distribution Detail (2023, Carleton)

For users who ask about the full distribution rather than just the
yes-aggregate:

```json
[
  {
    "year": 2023,
    "cohort": "first_year",
    "comparison_group": "carleton",
    "distribution": {
      "definitely_yes_pct": 31,
      "probably_yes_pct": 51,
      "probably_no_pct": 16,
      "definitely_no_pct": 2
    },
    "source": { "file": "nsse_2023_summary.pdf", "page": 6, "figure": "Figure 4" }
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "comparison_group": "carleton",
    "distribution": {
      "definitely_yes_pct": 30,
      "probably_yes_pct": 51,
      "probably_no_pct": 15,
      "definitely_no_pct": 4
    },
    "source": { "file": "nsse_2023_summary.pdf", "page": 6, "figure": "Figure 4" }
  },
  {
    "year": 2023,
    "cohort": "first_year",
    "comparison_group": "ontario_consortium_excl_carleton",
    "distribution": {
      "definitely_yes_pct": 31,
      "probably_yes_pct": 50,
      "probably_no_pct": 16,
      "definitely_no_pct": 4
    },
    "source": { "file": "nsse_2023_summary.pdf", "page": 7, "figure": "Figure 4" },
    "note": "Distribution sum (31+50+16+4 = 101%) reflects rounding in the source stacked bar chart; the yes-aggregate companion record (81%) derived from Definitely Yes + Probably Yes is the authoritative summary value."
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "comparison_group": "ontario_consortium_excl_carleton",
    "distribution": {
      "definitely_yes_pct": 30,
      "probably_yes_pct": 47,
      "probably_no_pct": 17,
      "definitely_no_pct": 6
    },
    "source": { "file": "nsse_2023_summary.pdf", "page": 7, "figure": "Figure 4" }
  }
]
```

> **Note for the agent.** Both Carleton and rest-of-Ontario consortium values
> for 2023 are now verified — both as yes-aggregates and as full four-point
> distributions. Carleton-vs-Ontario differences in 2023 were not
> statistically significant for either cohort. Where a distribution sums to
> 101% (Ontario first-year), this is a rounding artifact in the source figure;
> the yes-aggregate value derived from Definitely Yes + Probably Yes is the
> authoritative summary.

## Comparison Context

NSSE results are reported alongside the average for the **rest of the Ontario
consortium** (consortium total *excluding* Carleton). In 2023, 19 Ontario
universities participated.

For this metric in 2023:

- **First-year:** Carleton's result was similar to the rest of Ontario; the
  difference was **not statistically significant**.
- **Final-year:** Carleton's result was similar to the rest of Ontario; the
  difference was **not statistically significant**.

## Caveats and Methodological Notes

**Response rate.** The 2023 NSSE response rate was **21%** (2,030 of ~9,700
invited students), with 1,090 first-year and 940 final-year respondents. Lower
than 2020. See `methodology_notes.md` for general NSSE response-rate context.

**Response bias.** Carleton respondents skew female (56% first-year, 61%
final-year in 2023). NSSE applies gender weighting; published figures reflect
this weighting.

**Statistical significance.** OIRP reports differences as "statistically
significant" only at p < .05. Differences between 2020 and 2023 for both
cohorts on this metric were **not statistically significant**.

**Trend characterization (Carleton).** First-year respondents from both
Carleton and the rest of Ontario have shown a non-significant downward trend
on this question across recent administrations. For Carleton final-year
respondents, there was an uptick in 2020 that was maintained in 2023, though
that increase is not statistically significant.

**Final-year cohort composition.** "Final-year" at Carleton blends third-year
students in three-year programs (8% of 2023 final-year respondents) with
fourth-year students in four-year programs (92%). Not all Ontario consortium
institutions have three-year programs, so cohort definition differs slightly
across the comparison group.

**Construct caveat.** This is a hypothetical retrospective question, not a
behavioural measure. A respondent saying "Probably Yes" is not the same as
that respondent actually re-enrolling at the same institution if given a real
choice. Treat the metric as a satisfaction signal, not a retention predictor.

## Confidence Tier Guidance

- **High confidence.**
  - 2023 Carleton point values for first-year (82%) and final-year (81%) at
    the yes-aggregate level → look up.
  - 2023 Carleton four-point response distribution → look up.
  - The qualitative finding that Carleton-vs-Ontario differences were not
    statistically significant in 2023.

- **Medium confidence.**
  - Synthesizing this metric with `overall_experience_rating` to characterize
    Carleton's overall NSSE satisfaction profile.
  - Trend characterization across years using verified values once added.
  - Comparing the gap between "Definitely Yes" and "Probably Yes" responses
    as a signal of endorsement intensity.

- **Low confidence — refuse or hedge strongly.**
  - **Faculty-level breakdowns.** NSSE summaries do not publish this metric by
    Carleton faculty.
  - **Predicting actual re-enrolment behaviour.** This is a hypothetical
    question; do not present it as a behavioural retention forecast.
  - **Causal claims.** "Why did endorsement go up/down" — the source PDF does
    not answer this.
  - **Mixing with non-NSSE re-enrolment or transfer data** without explicit
    user direction.

## Related KPIs

- `overall_experience_rating` — companion NSSE overall-satisfaction question.
  These two are usually reported and interpreted together. A user asking
  about "satisfaction" without further specification often wants both.
- `quality_of_interactions_*` — the five relationship-quality items often
  cited as drivers of overall endorsement.
- `nsse_engagement_indicators` — the ten composite indicators; sometimes used
  to interpret why endorsement is higher or lower.
- `first_year_retention_rate` — actual behavioural retention. Conceptually
  related but a fundamentally different metric (behavioural vs attitudinal).
  Do not conflate.

## Glossary References

- **NSSE** — National Survey of Student Engagement.
- **Ontario consortium** — group of Ontario universities co-administering NSSE
  (19 institutions in 2023). "Rest of Ontario" = consortium *excluding*
  Carleton.
- **Comparison groups (verified-values field).** This file's
  `comparison_group` field uses two values: `carleton` (Carleton respondents
  only) and `ontario_consortium_excl_carleton` (rest-of-Ontario consortium
  average, excluding Carleton). Tool callers filtering by `comparison_group`
  must use these exact values.
- **First-year / Final-year** — see `overall_experience_rating.md` for full
  cohort definitions.
- **Yes-aggregate** — shorthand used in this file for the sum of "Definitely
  Yes" and "Probably Yes" response categories.

## Change Log

| Date       | Change                                          | Reviewer |
| ---------- | ----------------------------------------------- | -------- |
| 2026-04-27 | Initial draft from `nsse_2023_summary.pdf`      | (you)    |
| 2026-04-30 | Added rest-of-Ontario 2023 yes-aggregate values for first-year (81%) and final-year (77%), drafted by `scripts/draft_kpi_values.py` and verified by manual review against Figure 4. | (you) |
| 2026-04-30 | Added rest-of-Ontario 2023 full four-point distributions for first-year (31/50/16/4) and final-year (30/47/17/6) to the Response Distribution Detail block; flagged Ontario first-year 101% sum as rounding artifact (yes-aggregate authoritative). Updated stale "Note for the agent" callout. Added comparison_group glossary entry. | (you) |
